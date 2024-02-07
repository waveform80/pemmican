import sys
import locale
import gettext
import webbrowser
from importlib import resources

import gi
gi.require_version('Gio', '2.0')
gi.require_version('GLib', '2.0')
from gi.repository import Gio, GLib
from dbus.mainloop.glib import DBusGMainLoop

from .power import reset_brownout, psu_max_current
from .notify import Notifications


try:
    locale.setlocale(locale.LC_ALL, '')
except locale.Error:
    locale.setlocale(locale.LC_ALL, 'C')
_ = gettext.gettext


class Application:
    def __init__(self):
        # Integrate dbus-python with GLib; the set_as_default parameter means
        # we don't have to pass around the NativeMainLoop object this returns
        # whenever connecting to a bus -- it'll be the default anyway
        DBusGMainLoop(set_as_default=True)
        # Yes, it's unconventional to use GApplication instead of
        # GtkApplication but we've no need of any GUI stuff here; we just want
        # to talk to DBus notifications (if necessary) and quit
        self.app = Gio.Application()
        self.app.set_application_id('com.canonical.pemmican.ResetGui')
        self.app.connect('activate', self.do_activate)
        self.pending = set()
        self.task_id = None

    def __call__(self, args=None):
        with resources.as_file(resources.files(__package__)) as pkg_path:
            locale_path = pkg_path / 'locale'
            gettext.bindtextdomain(__package__, str(locale_path))
            gettext.textdomain(__package__)

            self.title = _('Raspberry Pi PMIC Monitor')
            return self.app.run(sys.argv if args is None else args)

    def do_activate(self, user_data):
        self.task_id = GLib.idle_add(self.do_check)
        self.main_loop = GLib.MainLoop()
        self.main_loop.run()

    def do_check(self):
        # This is a one-shot task; we never want to run again
        if self.task_id is not None:
            GLib.source_remove(self.task_id)

        try:
            brownout = reset_brownout()
            max_current = psu_max_current()
        except OSError:
            # We're probably not on a Pi 5; just exit
            self.main_loop.quit()

        self.notifier = Notifications()
        self.notifier.on_closed = self.do_notification_closed
        self.notifier.on_action = self.do_notification_action
        if brownout:
            self.pending.add(self.notifier.notify(
                self.title,
                body=_(
                    'Reset due to low power; please check your power supply'),
                hints={'urgency': 2},
                actions=[
                    ('moreinfo', _('More information')),
                    ('suppress', _("Don't show again")),
                ]))
        if max_current < 6000:
            self.pending.add(self.notifier.notify(
                self.title,
                body=_(
                    'This power supply is not capable of supplying 5A; power '
                    'to peripherals will be restricted, and USB/NVMe boot '
                    'disabled'),
                hints={'urgency': 1},
                actions=[
                    ('moreinfo', _('More information')),
                    ('suppress', _("Don't show again")),
                ]))
        if not self.pending:
            self.main_loop.quit()

    def do_notification_closed(self, msg_id, reason):
        self.pending.discard(msg_id)
        if not self.pending:
            self.main_loop.quit()

    def do_notification_action(self, msg_id, action_key):
        if action_key in ('moreinfo', 'suppress'):
            try:
                self.pending.remove(msg_id)
            except KeyError:
                pass
            else:
                webbrowser.open_new_tab('https://rptl.io/rpi5-power-supply-info')


main = Application()

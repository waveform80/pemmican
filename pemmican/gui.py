import os
import sys
import html
import locale
import gettext
import webbrowser
from pathlib import Path
from importlib import resources

import gi
gi.require_version('Gio', '2.0')
gi.require_version('GLib', '2.0')
from gi.repository import Gio, GLib
from dbus.mainloop.glib import DBusGMainLoop
from pyudev import Context, Monitor
from pyudev.glib import MonitorObserver

from .power import reset_brownout, psu_max_current
from .notify import Notifications


try:
    locale.setlocale(locale.LC_ALL, '')
except locale.Error:
    locale.setlocale(locale.LC_ALL, 'C')
    _ = lambda s: s
else:
    _ = gettext.gettext


XDG_CONFIG_HOME = Path(os.environ.get(
    'XDG_CONFIG_HOME', os.path.expanduser('~/.config')))
XDG_CONFIG_DIRS = [
    Path(p)
    for p in os.environ.get(
        'XDG_CONFIG_DIRS', f'{XDG_CONFIG_HOME}:/etc/xdg').split(':')
]


class NotifierApplication:
    APP_ID = 'com.canonical.pemmican'

    def __init__(self):
        self.title = ''
        self.app = None
        self.main_loop = None
        self.notifier = None
        self._run_id = None

    def __call__(self, args=None):
        # Integrate dbus-python with GLib; the set_as_default parameter means
        # we don't have to pass around the NativeMainLoop object this returns
        # whenever connecting to a bus -- it'll be the default anyway
        DBusGMainLoop(set_as_default=True)
        # Yes, it's unconventional to use GApplication instead of
        # GtkApplication but we've no need of any GUI stuff here; we just want
        # to talk to DBus notifications (if necessary) and quit
        self.app = Gio.Application()
        self.app.set_application_id(self.APP_ID)
        self.app.connect('activate', self.do_activate)
        with resources.as_file(resources.files(__package__)) as pkg_path:
            locale_path = pkg_path / 'locale'
            gettext.bindtextdomain(__package__, str(locale_path))
            gettext.textdomain(__package__)

            self.title = _('Raspberry Pi PMIC Monitor')
            return self.app.run(sys.argv if args is None else args)

    def do_activate(self, user_data):
        self.main_loop = GLib.MainLoop()
        self._run_id = GLib.idle_add(self._call_run)
        self.main_loop.run()

    def _call_run(self):
        # This is a one-shot method; we want to run once, and once only
        if self._run_id is not None:
            GLib.source_remove(self._run_id)
            self._run_id = None
            self.run()

    def run(self):
        self.notifier = Notifications()


class ResetApplication(NotifierApplication):
    APP_ID = 'com.canonical.pemmican.ResetGui'
    RPI_PSU_URL = 'https://rptl.io/rpi5-power-supply-info'
    BROWNOUT_INHIBIT = 'brownout_warning.inhibit'
    MAX_CURRENT_INHIBIT = 'max_current_warning.inhibit'

    def __init__(self):
        super().__init__()
        self.inhibit = None

    def run(self):
        super().run()
        self.notifier.on_closed = self.do_notification_closed
        self.notifier.on_action = self.do_notification_action
        self.do_check()

    def do_notification_closed(self, msg_id, reason):
        if not self.notifier.pending:
            self.main_loop.quit()

    def do_notification_action(self, msg_id, action_key):
        if action_key == 'moreinfo':
            webbrowser.open_new_tab(self.RPI_PSU_URL)
        else: # action_key == 'suppress'
            inhibit_path = XDG_CONFIG_HOME / __package__ / self.inhibit
            inhibit_path.parent.mkdir(parents=True, exist_ok=True)
            inhibit_path.touch()

    def do_check(self):
        try:
            brownout = reset_brownout() and not any(
                (p / __package__ / self.BROWNOUT_INHIBIT).exists()
                for p in XDG_CONFIG_DIRS)
            max_current = (psu_max_current() < 5000) and not any(
                (p / __package__ / self.MAX_CURRENT_INHIBIT).exists()
                for p in XDG_CONFIG_DIRS)
        except OSError:
            # We're probably not on a Pi 5; just exit
            brownout = max_current = False
        if not brownout and not max_current:
            self.main_loop.quit()
            return

        caps = self.notifier.get_capabilities()
        escape = html.escape if 'body-markup' in caps else lambda s: s
        # Customize what we notify based on the notification system's
        # capabilities; if we have actions, use them, otherwise tack "more
        # info" URLs onto the notification itself, using hyperlinks if capable
        if 'actions' in caps:
            actions = [
                ('moreinfo', _('More information')),
                ('suppress', _("Don't show again")),
            ]
            suffix = ''
        elif 'body-hyperlinks' in caps:
            actions = []
            suffix = (
                f'<a href="{escape(self.RPI_PSU_URL)}">' +
                escape(_("More information")) +
                '</a>')
        else:
            actions = []
            suffix = escape(_('See {self.RPI_PSU_URL} for more information')
                            .format(self=self))
        # Check for brownout initially. If brownout caused a reset, don't
        # bother double-warning about an inadequate PSU
        if brownout:
            self.inhibit = self.BROWNOUT_INHIBIT
            body=escape(_(
                'Reset due to low power; please check your power supply')) + (
                '. ' + suffix if suffix else '')
            self.notifier.notify(
                self.title, body=body,
                hints={'urgency': 2}, actions=actions)
        elif max_current:
            self.inhibit = self.MAX_CURRENT_INHIBIT
            body=escape(_(
                'This power supply is not capable of supplying 5A; power '
                'to peripherals will be restricted')) + (
                '. ' + suffix if suffix else '')
            self.notifier.notify(
                self.title, body=body,
                hints={'urgency': 1}, actions=actions)
        # If we didn't show any notifications, just exit immediately
        if not self.notifier.pending:
            self.main_loop.quit()


class MonitorApplication(NotifierApplication):
    APP_ID = 'com.canonical.pemmican.MonitorGui'
    RPI_PSU_URL = 'https://rptl.io/rpi5-power-supply-info'
    UNDERVOLT_INHIBIT = 'undervolt.inhibit'
    OVERCURRENT_INHIBIT = 'overcurrent.inhibit'

    def __init__(self):
        super().__init__()
        self.overcurrent_monitor = None
        self.overcurrent_observer = None
        self.overcurrent_msg_id = 0
        self.overcurrent_counts = {}
        self.undervolt_monitor = None
        self.undervolt_observer = None
        self.undervolt_msg_id = 0

    def run(self):
        super().run()
        check_undervolt = not any(
            (p / __package__ / self.UNDERVOLT_INHIBIT).exists()
            for p in XDG_CONFIG_DIRS)
        check_overcurrent = not any(
            (p / __package__ / self.OVERCURRENT_INHIBIT).exists()
            for p in XDG_CONFIG_DIRS)
        if not check_undervolt and not check_overcurrent:
            self.main_loop.quit()
            return

        context = Context()
        if check_overcurrent:
            self.overcurrent_monitor = Monitor.from_netlink(context)
            self.overcurrent_monitor.filter_by(subsystem='usb')
            self.overcurrent_observer = MonitorObserver(self.overcurrent_monitor)
            self.overcurrent_observer.connect('device-event', self.do_usb_device)
            self.overcurrent_monitor.start()
        if check_undervolt:
            self.undervolt_monitor = Monitor.from_netlink(context)
            self.undervolt_monitor.filter_by(subsystem='hwmon')
            self.undervolt_observer = MonitorObserver(self.undervolt_monitor)
            self.undervolt_observer.connect('device-event', self.do_hwmon_device)
            self.undervolt_monitor.start()

    def do_usb_device(self, observer, device):
        for key, value in device.properties.items():
            print(repr(key), repr(value))
        try:
            if device.action == 'change':
                port = device.properties['OVER_CURRENT_PORT']
                count = int(device.properties['OVER_CURRENT_COUNT'])
            else:
                return
        except KeyError:
            return
        if port and self.overcurrent_counts[port] > count:
            self.overcurrent_counts[port] = count
            self.overcurrent_msg_id = self.notify(
                'overcurrent',
                _('USB overcurrent; please check your connected USB devices'),
                self.overcurrent_msg_id)

    def do_hwmon_device(self, observer, device):
        try:
            if device.action == 'change':
                name = device.attributes.asstring('name')
                alarm = device.attributes.asint('in0_lcrit_alarm')
        except KeyError:
            return
        if name == 'rpi_volt' and alarm:
            self.undervolt_msg_id = self.notify(
                'undervolt',
                _('Low voltage warning; please check your power supply'),
                self.undervolt_msg_id)

    def notify(self, key, msg, replace_id=0):
        caps = self.notifier.get_capabilities()
        escape = html.escape if 'body-markup' in caps else lambda s: s
        # Customize what we notify based on the notification system's
        # capabilities; if we have actions, use them, otherwise tack "more
        # info" URLs onto the notification itself, using hyperlinks if capable
        if 'actions' in caps:
            actions = [
                ('moreinfo', _('More information')),
                (f'suppress_{key}', _("Don't show again")),
            ]
            suffix = ''
        elif 'body-hyperlinks' in caps:
            actions = []
            suffix = (
                f'<a href="{escape(self.RPI_PSU_URL)}">' +
                escape(_("More information")) +
                '</a>')
        else:
            actions = []
            suffix = escape(_('See {self.RPI_PSU_URL} for more information')
                            .format(self=self))

        return self.notifier.notify(
            self.title, body=escape(msg) + ('. ' + suffix if suffix else ''),
            hints={'urgency': 2}, actions=actions, replace_id=replace_id)

    def do_notification_closed(self, msg_id, reason):
        if msg_id == self.undervolt_msg_id:
            self.undervolt_msg_id = 0
        elif msg == self.overcurrent_msg_id:
            self.overcurrent_msg_id = 0

    def do_notification_action(self, msg_id, action_key):
        if action_key == 'moreinfo':
            webbrowser.open_new_tab(self.RPI_PSU_URL)
        else:
            inhibit_path = XDG_CONFIG_HOME / __package__ / {
                'suppress_undervolt': self.UNDERVOLT_INHIBIT,
                'suppress_overcurrent': self.OVERCURRENT_INHIBIT,
            }[action_key]
            inhibit_path.parent.mkdir(parents=True, exist_ok=True)
            inhibit_path.touch()
            # TODO: Stop the corresponding monitor and terminate if both
            # are now inhibited


reset_main = ResetApplication()
monitor_main = MonitorApplication()

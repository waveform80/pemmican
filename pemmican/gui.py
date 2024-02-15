import os
import sys
import html
import locale
import gettext
import webbrowser
from importlib import resources
from time import monotonic, sleep

import gi
gi.require_version('Gio', '2.0')
gi.require_version('GLib', '2.0')
from gi.repository import Gio, GLib
from dbus.mainloop.glib import DBusGMainLoop
from pyudev import Context, Monitor
from pyudev.glib import MonitorObserver

from .power import reset_brownout, psu_max_current
from .notify import Notifications
from .const import (
    XDG_CONFIG_DIRS,
    XDG_CONFIG_HOME,
    RPI_PSU_URL,
    BROWNOUT_INHIBIT,
    MAX_CURRENT_INHIBIT,
    UNDERVOLT_INHIBIT,
    OVERCURRENT_INHIBIT,
)


try:
    locale.setlocale(locale.LC_ALL, '')
except locale.Error:
    locale.setlocale(locale.LC_ALL, 'C')
    _ = lambda s: s
else:
    _ = gettext.gettext


class NotifierApplication:
    APP_ID = 'com.canonical.pemmican'

    def __init__(self):
        self.title = ''
        self.app = None
        self.main_loop = None
        self.notifier = None
        self._run_start = None

    def __call__(self, args=None):
        # Bail if we don't have DISPLAY or WAYLAND_DISPLAY set in the
        # environment (which are required to launch the browser on "more
        # information"); the service will retry us later (when hopefully
        # they've shown up...)
        if not os.environ.keys() & {'DISPLAY', 'WAYLAND_DISPLAY'}:
            print('Missing DISPLAY / WAYLAND_DISPLAY',
                  file=sys.stderr, flush=True)
            return 1
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
        GLib.idle_add(self._call_run)
        self._run_start = monotonic()
        self.main_loop.run()

    def _call_run(self):
        try:
            self.notifier = Notifications()
        except DBusException as err:
            if err.get_dbus_name() in (
                'org.freedesktop.DBus.Error.NameHasNoOwner',
                'org.freedesktop.DBus.Error.ServiceUnknown',
            ):
                if monotonic - self._run_start > 60:
                    # We've waited a full minute for the notification service
                    # to show up; bail with the exception
                    raise
                else:
                    # Wait a while and re-run the idle handler (True return
                    # indicates re-run requested)
                    sleep(1)
                    return True
            else:
                raise
        self._run_id = None
        self.run()
        return False

    def run(self):
        raise NotImplementedError()


class ResetApplication(NotifierApplication):
    APP_ID = 'com.canonical.pemmican.ResetGui'

    def __init__(self):
        super().__init__()
        self.inhibit = None

    def run(self):
        self.notifier.on_closed = self.do_notification_closed
        self.notifier.on_action = self.do_notification_action
        self.do_check()

    def do_notification_closed(self, msg_id, reason):
        if not self.notifier.pending:
            self.main_loop.quit()

    def do_notification_action(self, msg_id, action_key):
        if action_key == 'moreinfo':
            webbrowser.open_new_tab(RPI_PSU_URL)
        else: # action_key == 'suppress'
            inhibit_path = XDG_CONFIG_HOME / __package__ / self.inhibit
            inhibit_path.parent.mkdir(parents=True, exist_ok=True)
            inhibit_path.touch()

    def do_check(self):
        try:
            brownout = reset_brownout() and not any(
                (p / __package__ / BROWNOUT_INHIBIT).exists()
                for p in XDG_CONFIG_DIRS)
            max_current = (psu_max_current() < 5000) and not any(
                (p / __package__ / MAX_CURRENT_INHIBIT).exists()
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
                f'<a href="{escape(RPI_PSU_URL)}">' +
                escape(_("More information")) +
                '</a>')
        else:
            actions = []
            suffix = escape(_('See {RPI_PSU_URL} for more information')
                            .format(self=self))
        # Check for brownout initially. If brownout caused a reset, don't
        # bother double-warning about an inadequate PSU
        if brownout:
            self.inhibit = BROWNOUT_INHIBIT
            body=escape(_(
                'Reset due to low power; please check your power supply')) + (
                '. ' + suffix if suffix else '')
            self.notifier.notify(
                self.title, body=body,
                hints={'urgency': 2}, actions=actions)
        elif max_current:
            self.inhibit = MAX_CURRENT_INHIBIT
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
        check_undervolt = not any(
            (p / __package__ / UNDERVOLT_INHIBIT).exists()
            for p in XDG_CONFIG_DIRS)
        check_overcurrent = not any(
            (p / __package__ / OVERCURRENT_INHIBIT).exists()
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
                f'<a href="{escape(RPI_PSU_URL)}">' +
                escape(_("More information")) +
                '</a>')
        else:
            actions = []
            suffix = escape(_('See {RPI_PSU_URL} for more information')
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
            webbrowser.open_new_tab(RPI_PSU_URL)
        else:
            inhibit_path = XDG_CONFIG_HOME / __package__ / {
                'suppress_undervolt': UNDERVOLT_INHIBIT,
                'suppress_overcurrent': OVERCURRENT_INHIBIT,
            }[action_key]
            inhibit_path.parent.mkdir(parents=True, exist_ok=True)
            inhibit_path.touch()
            # TODO: Stop the corresponding monitor and terminate if both
            # are now inhibited


reset_main = ResetApplication()
monitor_main = MonitorApplication()

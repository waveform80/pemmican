# pemmican: notifies users of Raspberry Pi 5 power issues
#
# Copyright (c) 2024 Dave Jones <dave.jones@canonical.com>
# Copyright (c) 2024 Canonical Ltd.
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""
This module contains the "main" entry points for the :program:`pemmican-reset`
and :program:`pemmican-mon` applications, :class:`ResetApplication` and
:class:`MonitorApplication`, respectively. Both are derived from an abstract
base class, :class:`NotifierApplication` containing the logic common to both.
"""

import os
import sys
import html
import webbrowser
from time import monotonic, sleep
from abc import ABC, abstractmethod

import gi
gi.require_version('Gio', '2.0')
gi.require_version('GLib', '2.0')
from gi.repository import Gio, GLib
from dbus.mainloop.glib import DBusGMainLoop
from dbus.exceptions import DBusException
from pyudev import Context, Monitor
from pyudev.glib import MonitorObserver

from . import lang
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


class NotifierApplication(ABC):
    """
    Base class for a GLib GApplication which needs to talk to the freedestkop
    `notification service`_. An instance of this class can be called as a
    "main" function, optionally passing in the command line parameters.

    As a GApplication with an identifier (see :attr:`APP_ID`), only one
    instance is typically permitted to run. Additional instances will exit
    before activation, but will signal the original instance to activate
    instead. The XDG directories, particularly those related to configuration
    (:envvar:`XDG_CONFIG_HOME` and :envvar:`XDG_CONFIG_DIRS`) are expected in
    the environment.

    The application will terminate early with a non-zero exit code if
    :envvar:`DISPLAY` or :envvar:`WAYLAND_DISPLAY` are missing from the
    environment. Finally, if the freedesktop notification service does not show
    up within 1 minute of the application starting, the application will also
    terminate with a non-zero exit code.

    This is an abstract class; descendents need to implement the :meth:`run`
    method.

    .. attribute:: APP_ID

        The application's identifier, in the typical form of a reverse
        domain-name. This should be overridden at the class-level in each
        descendent.

    .. _notification service: https://specifications.freedesktop.org/notification-spec/
    """
    APP_ID = 'com.canonical.pemmican'

    def __init__(self):
        super().__init__()
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
        with lang.init():
            self.title = lang._('Raspberry Pi PMIC Monitor')
            return self.app.run(sys.argv if args is None else args)

    def do_activate(self, user_data):
        """
        Application activation. This starts the GLib main loop; any set up
        which should be performed before entering the main loop should be done
        here.

        The application's main logic (in the abstract :meth:`run` method) is
        ultimately executed as a one-shot idle handler from the GLib main loop,
        configured here.
        """
        self.main_loop = GLib.MainLoop()
        GLib.idle_add(self._call_run)
        self._run_start = monotonic()
        self.main_loop.run()

    def _call_run(self):
        """
        This method is run as an idle handler from the GLib main loop. If the
        freedesktop notification service is available, this executes the
        abstract :meth:`run` method. Otherwise, provided we haven't yet timed
        out, it schedules a future retry.
        """
        try:
            self.notifier = Notifications()
        except DBusException as err:
            if err.get_dbus_name() in (
                'org.freedesktop.DBus.Error.NameHasNoOwner',
                'org.freedesktop.DBus.Error.ServiceUnknown',
            ):
                if monotonic() - self._run_start > 60:
                    raise
                else:
                    sleep(1)
                    return True
            else:
                raise
        self._run_id = None
        self.run()
        return False

    @abstractmethod
    def run(self):
        """
        This abstract method should be overridden in descendents to provide the
        main logic of the application.
        """
        raise NotImplementedError()


class ResetApplication(NotifierApplication):
    """
    Checks the Raspberry Pi 5's power status and reports, via the freedesktop
    notification mechanism, if the last reset occurred due to a brownout
    (undervolt) situation, or if the current power supply failed to negotiate a
    5A supply. This script is intended to be run from a systemd user slice as
    part of the :file:`graphical-session.target`.
    """
    APP_ID = 'com.canonical.pemmican.ResetGui'

    def __init__(self):
        super().__init__()
        self.inhibit = None

    def run(self):
        self.notifier.on_closed = self.do_notification_closed
        self.notifier.on_action = self.do_notification_action
        self.do_check()

    def do_notification_closed(self, msg_id, reason):
        """
        Callback executed when the user dismisses a notification by any
        mechanism (explicit close, timeout, action activation, etc). As a
        oneshot application, which can only ever show one notification, we
        just quit if it's closed.
        """
        self.main_loop.quit()

    def do_notification_action(self, msg_id, action_key):
        """
        Callback executed when the user activates an action on one of our
        pending notifications. This launches the web-browser for the "More
        information" action, or touches the appropriate file for the "Don't
        show again" action.
        """
        if action_key == 'moreinfo':
            webbrowser.open_new_tab(RPI_PSU_URL)
        else: # action_key == 'suppress'
            inhibit_path = XDG_CONFIG_HOME / __package__ / self.inhibit
            inhibit_path.parent.mkdir(parents=True, exist_ok=True)
            inhibit_path.touch()

    def do_check(self):
        """
        This method is the bulk of the :program:`pemmican-reset` application.
        It runs the checks on the device-tree nodes and, if notifications are
        required, queries the notification service's capabilities to format the
        notifications accordingly.
        """
        try:
            brownout = reset_brownout() and not any(
                (p / __package__ / BROWNOUT_INHIBIT).exists()
                for p in [XDG_CONFIG_HOME] + XDG_CONFIG_DIRS)
            max_current = (psu_max_current() < 5000) and not any(
                (p / __package__ / MAX_CURRENT_INHIBIT).exists()
                for p in [XDG_CONFIG_HOME] + XDG_CONFIG_DIRS)
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
                ('moreinfo', lang._('More information')),
                ('suppress', lang._("Don't show again")),
            ]
            suffix = ''
        elif 'body-hyperlinks' in caps:
            actions = []
            suffix = (
                f'<a href="{escape(RPI_PSU_URL)}">' +
                escape(lang._("More information")) +
                '</a>')
        else:
            actions = []
            suffix = escape(lang._('See {RPI_PSU_URL} for more information')
                            .format(RPI_PSU_URL=RPI_PSU_URL))
        # Check for brownout initially. If brownout caused a reset, don't
        # bother double-warning about an inadequate PSU
        if brownout:
            self.inhibit = BROWNOUT_INHIBIT
            body=escape(lang._(
                'Reset due to low power; please check your power supply')) + (
                '. ' + suffix if suffix else '')
            self.notifier.notify(
                self.title, body=body,
                hints={'urgency': 2}, actions=actions)
        else: # max_current
            self.inhibit = MAX_CURRENT_INHIBIT
            body=escape(lang._(
                'This power supply is not capable of supplying 5A; power '
                'to peripherals will be restricted')) + (
                '. ' + suffix if suffix else '')
            self.notifier.notify(
                self.title, body=body,
                hints={'urgency': 1}, actions=actions)
        # If nothing is pending (already!), just exit immediately
        if not self.notifier.pending:
            self.main_loop.quit()


class MonitorApplication(NotifierApplication):
    """
    Monitors the Raspberry Pi 5's power supply for reports of undervolt
    (deficient power supply), or overcurrent (excessive draw by USB
    peripherals). Issues are reported via the freedesktop notification
    mechanism. This script is intended to be run from a systemd user slice as
    part of the :file:`graphical-session.target`.
    """
    APP_ID = 'com.canonical.pemmican.MonitorGui'

    def __init__(self):
        super().__init__()
        self.overcurrent_monitor = None
        self.overcurrent_observer = None
        self.overcurrent_handle = None
        self.overcurrent_msg_id = 0
        self.overcurrent_counts = {}
        self.undervolt_monitor = None
        self.undervolt_observer = None
        self.undervolt_handle = None
        self.undervolt_msg_id = 0

    def run(self):
        check_undervolt = not any(
            (p / __package__ / UNDERVOLT_INHIBIT).exists()
            for p in [XDG_CONFIG_HOME] + XDG_CONFIG_DIRS)
        check_overcurrent = not any(
            (p / __package__ / OVERCURRENT_INHIBIT).exists()
            for p in [XDG_CONFIG_HOME] + XDG_CONFIG_DIRS)
        if not check_undervolt and not check_overcurrent:
            self.main_loop.quit()
            return

        self.notifier.on_closed = self.do_notification_closed
        self.notifier.on_action = self.do_notification_action
        context = Context()
        if check_overcurrent:
            self.overcurrent_monitor = Monitor.from_netlink(context)
            self.overcurrent_monitor.filter_by(subsystem='usb')
            self.overcurrent_observer = MonitorObserver(self.overcurrent_monitor)
            self.overcurrent_handle = self.overcurrent_observer.connect(
                'device-event', self.do_usb_device)
            self.overcurrent_monitor.start()
        if check_undervolt:
            self.undervolt_monitor = Monitor.from_netlink(context)
            self.undervolt_monitor.filter_by(subsystem='hwmon')
            self.undervolt_observer = MonitorObserver(self.undervolt_monitor)
            self.undervolt_handle = self.undervolt_observer.connect(
                'device-event', self.do_hwmon_device)
            self.undervolt_monitor.start()

    def do_usb_device(self, observer, device):
        """
        Callback registered for USB device events. This method performs further
        filtering to determine if this is actually an overcurrent event, and
        dispatches a notification if it is.
        """
        try:
            if device.action == 'change':
                port = device.properties['OVER_CURRENT_PORT']
                count = int(device.properties['OVER_CURRENT_COUNT'])
            else:
                return
        except KeyError:
            return
        if (
            # Only display a notification if there's no active notification
            # already; this works around an issue in GNOME that replacing a
            # notification loses its actions
            self.overcurrent_msg_id == 0 and
            port and count > self.overcurrent_counts.get(port, 0)
        ):
            self.overcurrent_counts[port] = count
            self.overcurrent_msg_id = self.notify(
                'overcurrent',
                lang._('USB overcurrent; please check your connected USB devices'),
                replaces_id=self.overcurrent_msg_id)

    def do_hwmon_device(self, observer, device):
        """
        Callback registered for hardware monitoring events. This performs
        further filtering to determine if this is actually an undervolt event,
        and dispatches a notification if it is.
        """
        try:
            if device.action == 'change':
                name = device.attributes.asstring('name')
                alarm = device.attributes.asint('in0_lcrit_alarm')
            else:
                return
        except KeyError:
            return
        # See note in method above
        if self.undervolt_msg_id == 0 and name == 'rpi_volt' and alarm:
            self.undervolt_msg_id = self.notify(
                'undervolt',
                lang._('Low voltage warning; please check your power supply'),
                replaces_id=self.undervolt_msg_id)

    def notify(self, key, msg, *, replaces_id=0):
        """
        This method is called by the monitoring callbacks
        (:meth:`do_usb_device` and :meth:`do_hwmon_device`) to format and
        dispatch a notification according to the capabilities of the system's
        notification mechanism.
        """
        caps = self.notifier.get_capabilities()
        escape = html.escape if 'body-markup' in caps else lambda s: s
        # Customize what we notify based on the notification system's
        # capabilities; if we have actions, use them, otherwise tack "more
        # info" URLs onto the notification itself, using hyperlinks if capable
        if 'actions' in caps:
            actions = [
                ('moreinfo', lang._('More information')),
                (f'suppress_{key}', lang._("Don't show again")),
            ]
            suffix = ''
        elif 'body-hyperlinks' in caps:
            actions = []
            suffix = (
                f'<a href="{escape(RPI_PSU_URL)}">' +
                escape(lang._("More information")) +
                '</a>')
        else:
            actions = []
            suffix = escape(lang._('See {RPI_PSU_URL} for more information')
                            .format(RPI_PSU_URL=RPI_PSU_URL))

        return self.notifier.notify(
            self.title, body=escape(msg) + ('. ' + suffix if suffix else ''),
            hints={'urgency': 2}, actions=actions, replaces_id=replaces_id)

    def do_notification_closed(self, msg_id, reason):
        """
        Callback executed when the user dismisses a notification by any
        mechanism (explicit close, timeout, action activation, etc).
        """
        if msg_id == self.undervolt_msg_id:
            self.undervolt_msg_id = 0
        elif msg_id == self.overcurrent_msg_id:
            self.overcurrent_msg_id = 0

    def do_notification_action(self, msg_id, action_key):
        """
        Callback executed when the user activates an action on one of our
        pending notifications. This launches the web-browser for the "More
        information" action, or touches the appropriate file for the "Don't
        show again" action.
        """
        if action_key == 'suppress_undervolt':
            inhibit = XDG_CONFIG_HOME / __package__ / UNDERVOLT_INHIBIT
            inhibit.parent.mkdir(parents=True, exist_ok=True)
            inhibit.touch()
            self.undervolt_observer.disconnect(self.undervolt_handle)
            self.undervolt_handle = None
            self.undervolt_observer = None
            self.undervolt_monitor = None
        elif action_key == 'suppress_overcurrent':
            inhibit = XDG_CONFIG_HOME / __package__ / OVERCURRENT_INHIBIT
            inhibit.parent.mkdir(parents=True, exist_ok=True)
            inhibit.touch()
            self.overcurrent_observer.disconnect(self.overcurrent_handle)
            self.overcurrent_handle = None
            self.overcurrent_observer = None
            self.overcurrent_monitor = None
        else: # action_key == 'moreinfo'
            webbrowser.open_new_tab(RPI_PSU_URL)
        if self.undervolt_monitor is None and self.overcurrent_monitor is None:
            self.main_loop.quit()


reset_main = ResetApplication()
monitor_main = MonitorApplication()

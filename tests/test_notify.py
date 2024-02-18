# pemmican: notifies users of Raspberry Pi 5 power issues
#
# Copyright (c) 2024 Dave Jones <dave.jones@canonical.com>
# Copyright (c) 2024 Canonical Ltd.
#
# SPDX-License-Identifier: GPL-3.0-or-later

import pytest
from unittest import mock

from pemmican.notify import Notifications


def test_notifications_init(dbus):
    notifier = Notifications()
    assert notifier.on_closed is None
    assert notifier.on_action is None
    assert notifier.pending == frozenset()
    assert dbus.SessionBus().add_signal_receiver.call_count == 2


def test_notifications_init_with_bus(dbus):
    my_bus = dbus.SessionBus()
    notifier = Notifications(my_bus)
    assert notifier.on_closed is None
    assert notifier.on_action is None
    assert notifier.pending == frozenset()
    assert my_bus.add_signal_receiver.call_count == 2


def test_notifications_info(notify_intf):
    notifier = Notifications()

    notify_intf.GetServerInformation.return_value = (
        'foo-shell', 'FOO', '1.0', '1.2')
    assert notifier.get_server_info() == {
        'name': 'foo-shell',
        'vendor': 'FOO',
        'version': '1.0',
        'spec_version': '1.2',
    }


def test_notifications_caps(notify_intf):
    notifier = Notifications()

    caps = ['persistence', 'body', 'body-hyperlink']
    notify_intf.GetCapabilities.return_value = caps
    assert notifier.get_capabilities() == caps


def test_notifications_notify(notify_intf):
    notifier = Notifications()
    notify_intf.Notify.return_value = 9

    assert notifier.notify('Foo Info', body='The foo has started') == 9
    assert notifier.pending == {9}
    assert notify_intf.Notify.call_args.args == (
        '', 0, '', 'Foo Info', 'The foo has started', [], {}, -1)
    assert notify_intf.Notify.call_args.kwargs == {}

    notify_intf.Notify.return_value = 10
    assert notifier.notify(
        'Foo Error', body='The foo is on fire!',
        actions=[('put-it-out', 'Extinguish!'), ('let-it-burn', 'Leave It')],
        hints={'urgency': 2}) == 10
    assert notifier.pending == {9, 10}
    assert notify_intf.Notify.call_args.args == (
        '', 0, '', 'Foo Error', 'The foo is on fire!',
        ['put-it-out', 'Extinguish!', 'let-it-burn', 'Leave It'],
        {'urgency': 2}, -1)
    assert notify_intf.Notify.call_args.kwargs == {}


def test_notifications_not_pending(notify_intf):
    notifier = Notifications()
    notify_intf.Notify.return_value = 0

    assert notifier.notify('Foo Info', body='The foo has started') == 0
    # Ensure we don't set 0 (which is not a valid message ID) as a pending
    # identity
    assert notifier.pending == set()


def test_notifications_remove(notify_intf):
    notifier = Notifications()
    notifier.remove(10)
    assert notify_intf.CloseNotification.call_args.args == (10,)
    assert notify_intf.CloseNotification.call_args.kwargs == {}


def test_notifications_action(notify_intf):
    notifier = Notifications()
    notifier.on_action = mock.Mock()

    notifier._action_invoked(9, 'put-it-out')
    assert notifier.on_action.call_count == 0

    notify_intf.Notify.return_value = 10
    assert notifier.notify(
        'Foo Error', body='The foo is on fire!',
        actions=[('put-it-out', 'Extinguish!'), ('let-it-burn', 'Leave It')],
        hints={'urgency': 2}) == 10
    notifier._action_invoked(10, 'put-it-out')
    assert notifier.on_action.call_count == 1
    assert notifier.on_action.call_args.args == (10, 'put-it-out')
    notifier._action_invoked(11, 'put-it-out')
    assert notifier.on_action.call_count == 1


def test_notifications_no_action(notify_intf):
    notifier = Notifications()
    notifier.on_action = None

    notify_intf.Notify.return_value = 11
    assert notifier.notify(
        'Foo Error', body='The foo is on fire!',
        actions=[('put-it-out', 'Extinguish!'), ('let-it-burn', 'Leave It')],
        hints={'urgency': 2}) == 11
    # Ensure if on_action is None, the _action_invoked handler does not raise
    # an exception, even if the ID is pending and everything else is valid
    notifier._action_invoked(11, 'put-it-out')


def test_notifications_closed(notify_intf):
    notifier = Notifications()
    notifier.on_closed = mock.Mock()

    notifier._notification_closed(9, 2)
    assert notifier.on_closed.call_count == 0

    notify_intf.Notify.return_value = 10
    assert notifier.notify(
        'Foo Error', body='The foo is on fire!',
        actions=[('put-it-out', 'Extinguish!'), ('let-it-burn', 'Leave It')],
        hints={'urgency': 2}) == 10
    notifier._notification_closed(10, 2)
    assert notifier.on_closed.call_count == 1
    assert notifier.on_closed.call_args.args == (10, 2)
    notifier._notification_closed(11, 2)
    assert notifier.on_closed.call_count == 1


def test_notifications_closed_but_none(notify_intf):
    notifier = Notifications()
    notifier.on_closed = None

    notify_intf.Notify.return_value = 11
    assert notifier.notify(
        'Foo Error', body='The foo is on fire!',
        actions=[('put-it-out', 'Extinguish!'), ('let-it-burn', 'Leave It')],
        hints={'urgency': 2}) == 11
    # Ensure if on_closed is None, the _notification_closed handler does not
    # raise an exception, even if the ID is pending and everything else is
    # valid
    notifier._notification_closed(11, 2)

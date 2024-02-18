# pemmican: notifies users of Raspberry Pi 5 power issues
#
# Copyright (c) 2024 Dave Jones <dave.jones@canonical.com>
# Copyright (c) 2024 Canonical Ltd.
#
# SPDX-License-Identifier: GPL-3.0-or-later

from unittest import mock

import pytest

from pemmican.const import RPI_PSU_URL
from pemmican.gui import ResetApplication


@pytest.fixture()
def conf_dir(tmp_path):
    with (
        mock.patch('pemmican.gui.XDG_CONFIG_HOME', tmp_path),
        mock.patch('pemmican.gui.XDG_CONFIG_DIRS', [tmp_path]),
    ):
        yield tmp_path


@pytest.fixture()
def main(gio, glib, dbus, notify_intf, conf_dir, monkeypatch):
    with (
        monkeypatch.context() as m,
    ):
        m.setenv('DISPLAY', ':0')
        yield ResetApplication()


def test_main(main, glib, notify_intf):
    with (
        mock.patch('pemmican.gui.reset_brownout') as reset_brownout,
        mock.patch('pemmican.gui.psu_max_current') as psu_max_current,
    ):
        reset_brownout.return_value = False
        psu_max_current.return_value = 5000
        notify_intf.Notify.return_value = 1
        notify_intf.GetCapabilities.return_value = ['actions', 'body-hyperlinks']
        assert main() == 0
        assert notify_intf.Notify.call_count == 0
        assert glib.MainLoop().quit.call_count == 1


def test_missing_display(main, monkeypatch, capsys):
    with monkeypatch.context() as m:
        m.delenv('DISPLAY', raising=False)
        m.delenv('WAYLAND_DISPLAY', raising=False)
        assert main() == 1
        capture = capsys.readouterr()
        assert capture.err.strip().startswith('Missing DISPLAY')


def test_missing_notifier(main, dbus, dbus_exception):
    with (
        mock.patch('pemmican.gui.sleep') as sleep,
        mock.patch('pemmican.gui.monotonic') as monotonic,
    ):
        dbus.Interface.side_effect = dbus_exception(
            'org.freedesktop.DBus.Error.ServiceUnknown')
        monotonic.side_effect = list(range(100))
        with pytest.raises(dbus_exception):
            main()
        assert sleep.call_count == 60


def test_broken_notifier(main, dbus, dbus_exception):
    with mock.patch('pemmican.gui.sleep') as sleep:
        dbus.Interface.side_effect = dbus_exception(
            'org.freedesktop.DBus.Error.SomeOtherError')
        with pytest.raises(dbus_exception):
            main()
        assert sleep.call_count == 0


def test_brownout_basic(main, glib, notify_intf):
    with (
        mock.patch('pemmican.gui.reset_brownout') as reset_brownout,
        mock.patch('pemmican.gui.psu_max_current') as psu_max_current,
    ):
        reset_brownout.return_value = True
        psu_max_current.return_value = 5000
        notify_intf.Notify.return_value = 1
        notify_intf.GetCapabilities.return_value = []
        assert main() == 0
        assert notify_intf.Notify.call_args.args == (
            '', 0, '', 'Raspberry Pi PMIC Monitor',
            'Reset due to low power; please check your power supply. '
            f'See {RPI_PSU_URL} for more information',
            [], {'urgency': 2}, -1)
        assert glib.MainLoop().quit.call_count == 0


def test_brownout_hyperlinks(main, glib, notify_intf):
    with (
        mock.patch('pemmican.gui.reset_brownout') as reset_brownout,
        mock.patch('pemmican.gui.psu_max_current') as psu_max_current,
    ):
        reset_brownout.return_value = True
        psu_max_current.return_value = 5000
        notify_intf.Notify.return_value = 1
        notify_intf.GetCapabilities.return_value = ['body-hyperlinks']
        assert main() == 0
        assert notify_intf.Notify.call_args.args == (
            '', 0, '', 'Raspberry Pi PMIC Monitor',
            'Reset due to low power; please check your power supply. '
            f'<a href="{RPI_PSU_URL}">More information</a>',
            [], {'urgency': 2}, -1)
        assert glib.MainLoop().quit.call_count == 0


def test_brownout_actions(main, glib, notify_intf):
    with (
        mock.patch('pemmican.gui.reset_brownout') as reset_brownout,
        mock.patch('pemmican.gui.psu_max_current') as psu_max_current,
    ):
        reset_brownout.return_value = True
        psu_max_current.return_value = 3000
        notify_intf.Notify.return_value = 1
        notify_intf.GetCapabilities.return_value = ['actions', 'body-hyperlinks']
        assert main() == 0
        assert notify_intf.Notify.call_args.args == (
            '', 0, '', 'Raspberry Pi PMIC Monitor',
            'Reset due to low power; please check your power supply',
            ['moreinfo', 'More information', 'suppress', "Don't show again"],
            {'urgency': 2}, -1)
        assert glib.MainLoop().quit.call_count == 0


def test_max_current_actions(main, glib, notify_intf):
    with (
        mock.patch('pemmican.gui.reset_brownout') as reset_brownout,
        mock.patch('pemmican.gui.psu_max_current') as psu_max_current,
    ):
        reset_brownout.return_value = False
        psu_max_current.return_value = 3000
        notify_intf.Notify.return_value = 1
        notify_intf.GetCapabilities.return_value = ['actions', 'body-hyperlinks']
        assert main() == 0
        assert notify_intf.Notify.call_args.args == (
            '', 0, '', 'Raspberry Pi PMIC Monitor',
            'This power supply is not capable of supplying 5A; power to '
            'peripherals will be restricted',
            ['moreinfo', 'More information', 'suppress', "Don't show again"],
            {'urgency': 1}, -1)
        assert glib.MainLoop().quit.call_count == 0


def test_max_current_no_message_id(main, glib, notify_intf):
    with (
        mock.patch('pemmican.gui.reset_brownout') as reset_brownout,
        mock.patch('pemmican.gui.psu_max_current') as psu_max_current,
    ):
        reset_brownout.return_value = False
        psu_max_current.return_value = 3000
        # Notify will return 0 (which it mustn't according to the spec, but
        # just in case there's a dedficient implementation...)
        notify_intf.Notify.return_value = 0
        notify_intf.GetCapabilities.return_value = ['actions', 'body-hyperlinks']
        assert main() == 0
        assert notify_intf.Notify.call_args.args == (
            '', 0, '', 'Raspberry Pi PMIC Monitor',
            'This power supply is not capable of supplying 5A; power to '
            'peripherals will be restricted',
            ['moreinfo', 'More information', 'suppress', "Don't show again"],
            {'urgency': 1}, -1)
        assert glib.MainLoop().quit.call_count == 1


def test_non_pi(main, glib):
    with (
        mock.patch('pemmican.gui.reset_brownout') as reset_brownout,
        mock.patch('pemmican.gui.psu_max_current') as psu_max_current,
    ):
        reset_brownout.side_effect = FileNotFoundError()
        psu_max_current.return_value = 3000
        assert main() == 0
        assert glib.MainLoop().quit.call_count == 1


def test_more_info(main, glib, notify_intf):
    with (
        mock.patch('pemmican.gui.reset_brownout') as reset_brownout,
        mock.patch('pemmican.gui.psu_max_current') as psu_max_current,
        mock.patch('pemmican.gui.webbrowser') as webbrowser,
    ):
        reset_brownout.return_value = True
        psu_max_current.return_value = 3000
        notify_intf.Notify.return_value = 1
        notify_intf.GetCapabilities.return_value = ['actions', 'body-hyperlinks']
        assert main() == 0
        assert notify_intf.Notify.call_args.args == (
            '', 0, '', 'Raspberry Pi PMIC Monitor',
            'Reset due to low power; please check your power supply',
            ['moreinfo', 'More information', 'suppress', "Don't show again"],
            {'urgency': 2}, -1)
        assert glib.MainLoop().quit.call_count == 0
        main.notifier._action_invoked(1, 'moreinfo')
        assert webbrowser.open_new_tab.call_count == 1
        assert webbrowser.open_new_tab.call_args.args == (RPI_PSU_URL,)
        main.notifier._notification_closed(1, 2)
        assert glib.MainLoop().quit.call_count == 1


def test_inhibit(main, conf_dir, glib, notify_intf, tmp_path):
    with (
        mock.patch('pemmican.gui.reset_brownout') as reset_brownout,
        mock.patch('pemmican.gui.psu_max_current') as psu_max_current,
    ):
        reset_brownout.return_value = True
        psu_max_current.return_value = 5000
        notify_intf.Notify.return_value = 1
        notify_intf.GetCapabilities.return_value = ['actions', 'body-hyperlinks']
        assert main() == 0
        assert notify_intf.Notify.call_args.args == (
            '', 0, '', 'Raspberry Pi PMIC Monitor',
            'Reset due to low power; please check your power supply',
            ['moreinfo', 'More information', 'suppress', "Don't show again"],
            {'urgency': 2}, -1)
        assert glib.MainLoop().quit.call_count == 0
        assert not (conf_dir / 'pemmican' / 'brownout.inhibit').exists()
        main.notifier._action_invoked(1, 'suppress')
        assert (conf_dir / 'pemmican' / 'brownout.inhibit').exists()
        main.notifier._notification_closed(1, 2)
        assert glib.MainLoop().quit.call_count == 1

from unittest import mock

import pytest

from pemmican.const import RPI_PSU_URL
from pemmican.gui import MonitorApplication


@pytest.fixture()
def conf_dir(tmp_path):
    with (
        mock.patch('pemmican.gui.XDG_CONFIG_HOME', tmp_path),
        mock.patch('pemmican.gui.XDG_CONFIG_DIRS', [tmp_path]),
    ):
        yield tmp_path


@pytest.fixture()
def main(
    gio, glib, dbus, notify_intf, udev_context, udev_monitor, udev_observer,
    conf_dir, monkeypatch
):
    with (
        monkeypatch.context() as m,
    ):
        m.setenv('DISPLAY', ':0')
        yield MonitorApplication()


def test_main(main, glib, notify_intf):
    assert main() == 0
    assert notify_intf.Notify.call_count == 0
    assert glib.MainLoop().quit.call_count == 0
    assert main.overcurrent_monitor is not None
    assert main.undervolt_monitor is not None


def test_both_inhibited(main, conf_dir, glib, notify_intf):
    (conf_dir / 'pemmican').mkdir()
    (conf_dir / 'pemmican' / 'undervolt.inhibit').touch()
    (conf_dir / 'pemmican' / 'overcurrent.inhibit').touch()
    assert main() == 0
    assert notify_intf.Notify.call_count == 0
    assert glib.MainLoop().quit.call_count == 1


def test_undervolt_inhibited(main, conf_dir, glib, notify_intf):
    (conf_dir / 'pemmican').mkdir()
    (conf_dir / 'pemmican' / 'undervolt.inhibit').touch()
    assert main() == 0
    assert notify_intf.Notify.call_count == 0
    assert glib.MainLoop().quit.call_count == 0
    assert main.overcurrent_monitor is not None
    assert main.undervolt_monitor is None


def test_overcurrent_inhibited(main, conf_dir, glib, notify_intf):
    (conf_dir / 'pemmican').mkdir()
    (conf_dir / 'pemmican' / 'overcurrent.inhibit').touch()
    assert main() == 0
    assert notify_intf.Notify.call_count == 0
    assert glib.MainLoop().quit.call_count == 0
    assert main.overcurrent_monitor is None
    assert main.undervolt_monitor is not None


def test_missing_display(main, monkeypatch, capsys):
    with monkeypatch.context() as m:
        m.delenv('DISPLAY')
        m.delenv('WAYLAND_DISPLAY')
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


def test_usb_overcurrent(main, udev_observer, notify_intf):
    assert main() == 0
    assert notify_intf.Notify.call_count == 0
    device = mock.Mock()
    device.action = 'change'
    device.properties = {}
    device.properties['OVER_CURRENT_PORT'] = '4-2-port1'
    device.properties['OVER_CURRENT_COUNT'] = 1
    main.overcurrent_observer.event('device-event', device)
    assert notify_intf.Notify.call_count == 1

    # Re-send the same event, observe the call-count doesn't change (because
    # the count hasn't increased)
    main.overcurrent_observer.event('device-event', device)
    assert notify_intf.Notify.call_count == 1


def test_usb_other(main, udev_observer, notify_intf):
    assert main() == 0
    assert notify_intf.Notify.call_count == 0
    device = mock.Mock()
    device.action = 'add'
    device.properties = {}
    main.overcurrent_observer.event('device-event', device)
    assert notify_intf.Notify.call_count == 0

    device = mock.Mock()
    device.action = 'change'
    device.properties = {}
    # No OVER_CURRENT_PORT...
    device.properties['OVER_CURRENT_COUNT'] = 1
    main.overcurrent_observer.event('device-event', device)
    assert notify_intf.Notify.call_count == 0


def test_undervolt(main, udev_observer, notify_intf):
    assert main() == 0
    assert notify_intf.Notify.call_count == 0
    device = mock.Mock()
    device.action = 'change'
    device.attributes.asstring.side_effect = (
        lambda s: 'rpi_volt' if s == 'name' else 'foo')
    device.attributes.asint.side_effect = (
        lambda s: '1' if s == 'in0_lcrit_alarm' else '0')
    main.undervolt_observer.event('device-event', device)
    assert notify_intf.Notify.call_count == 1

    # Re-send the same event, observe the call-count changes because we're not
    # using a count here
    main.undervolt_observer.event('device-event', device)
    assert notify_intf.Notify.call_count == 2


def test_not_undervolt(main, udev_observer, notify_intf):
    assert main() == 0
    assert notify_intf.Notify.call_count == 0
    device = mock.Mock()
    # Wrong action
    device.action = 'add'
    main.undervolt_observer.event('device-event', device)
    assert notify_intf.Notify.call_count == 0

    # No in0_lcrit_alarm attribute
    device = mock.Mock()
    device.action = 'change'
    device.attributes.asstring.side_effect = (
        lambda s: 'rpi_volt' if s == 'name' else 'foo')
    device.attributes.asint.side_effect = KeyError('in0_lcrit_alarm')
    main.undervolt_observer.event('device-event', device)
    assert notify_intf.Notify.call_count == 0

    # Wrong name
    device = mock.Mock()
    device.action = 'change'
    device.attributes.asstring.side_effect = (
        lambda s: 'foo' if s == 'name' else 'rpi_volt')
    device.attributes.asint.side_effect = (
        lambda s: '1' if s == 'in0_lcrit_alarm' else '0')
    main.undervolt_observer.event('device-event', device)
    assert notify_intf.Notify.call_count == 0

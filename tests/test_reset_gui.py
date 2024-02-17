from unittest import mock

import pytest

from pemmican.gui import reset_main as main


@pytest.fixture()
def _dbus():
    class DBusException(Exception):
        def __init__(self, name, msg=''):
            self._name = name
            super().__init__(msg)
        def get_dbus_name(self):
            return self._name
    with (
        mock.patch('pemmican.notify.dbus') as mock_dbus,
        mock.patch('pemmican.gui.DBusGMainLoop') as mock_dbus_mainloop,
        mock.patch('pemmican.gui.DBusException', DBusException) as mock_dbus_exc,
    ):
        yield mock_dbus, mock_dbus_mainloop, mock_dbus_exc


@pytest.fixture()
def dbus(_dbus):
    return _dbus[0]


@pytest.fixture()
def dbus_exception(_dbus):
    return _dbus[2]


@pytest.fixture()
def notify_intf(dbus):
    return dbus.Interface()


@pytest.fixture()
def gio():
    with mock.patch('pemmican.gui.Gio') as Gio:
        handlers = {}
        app = Gio.Application()

        def connect(signal, handler, data=None):
            handlers[signal] = (handler, data)
        def run(args):
            handler, data = handlers['activate']
            handler(data)
            return 0

        app.connect.side_effect = connect
        app.run.side_effect = run
        yield Gio


@pytest.fixture()
def glib():
    with mock.patch('pemmican.gui.GLib') as GLib:
        handlers = {}
        loop = GLib.MainLoop()
        loop._quit = False

        def idle_add(handler):
            handlers['idle_add'] = handler
        def run():
            handler = handlers['idle_add']
            # TODO timeout
            while handler() and not loop._quit:
                pass
        def quit():
            loop._quit = True

        GLib.idle_add.side_effect = idle_add
        loop.run.side_effect = run
        loop.quit.side_effect = quit
        yield GLib


def test_main(gio, glib, dbus, notify_intf, monkeypatch):
    with (
        mock.patch('pemmican.gui.reset_brownout') as reset_brownout,
        mock.patch('pemmican.gui.psu_max_current') as psu_max_current,
        monkeypatch.context() as m,
    ):
        m.setenv('DISPLAY', ':0')
        reset_brownout.return_value = False
        psu_max_current.return_value = 5000
        assert main() == 0


def test_missing_display(gio, glib, monkeypatch, capsys):
    with monkeypatch.context() as m:
        m.delenv('DISPLAY')
        m.delenv('WAYLAND_DISPLAY')
        assert main() == 1
        capture = capsys.readouterr()
        assert capture.err.strip().startswith('Missing DISPLAY')


def test_missing_notifier(gio, glib, dbus, dbus_exception, monkeypatch):
    with (
        mock.patch('pemmican.gui.sleep') as sleep,
        mock.patch('pemmican.gui.monotonic') as monotonic,
        monkeypatch.context() as m,
    ):
        dbus.Interface.side_effect = dbus_exception(
            'org.freedesktop.DBus.Error.ServiceUnknown')
        monotonic.side_effect = list(range(100))
        m.setenv('DISPLAY', ':0')
        with pytest.raises(dbus_exception):
            main()
        assert sleep.call_count == 60


def test_broken_notifier(gio, glib, dbus, dbus_exception, monkeypatch):
    with (
        mock.patch('pemmican.gui.sleep') as sleep,
        monkeypatch.context() as m,
    ):
        dbus.Interface.side_effect = dbus_exception(
            'org.freedesktop.DBus.Error.SomeOtherError')
        m.setenv('DISPLAY', ':0')
        with pytest.raises(dbus_exception):
            main()
        assert sleep.call_count == 0


def test_brownout(gio, glib, dbus, monkeypatch):

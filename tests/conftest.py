from unittest import mock

import pytest


@pytest.fixture()
def dbus():
    with mock.patch('pemmican.notify.dbus') as mock_dbus:
        yield mock_dbus


@pytest.fixture()
def dbus_mainloop(dbus):
    with mock.patch('pemmican.gui.DBusGMainLoop') as mock_dbus_mainloop:
        yield mock_dbus_mainloop


@pytest.fixture()
def dbus_exception(dbus):
    class DBusException(Exception):
        def __init__(self, name, msg=''):
            self._name = name
            super().__init__(msg)
        def get_dbus_name(self):
            return self._name
    with mock.patch('pemmican.gui.DBusException', DBusException) as mock_exc:
        yield mock_exc


@pytest.fixture()
def notify_intf(dbus):
    return dbus.Interface()


@pytest.fixture()
def udev_context():
    with mock.patch('pemmican.gui.Context') as context:
        yield context


@pytest.fixture()
def udev_monitor(udev_context):
    with mock.patch('pemmican.gui.Monitor') as monitor:
        yield monitor


@pytest.fixture()
def udev_observer(udev_monitor):
    class MonitorObserver:
        def __init__(self, monitor):
            self.monitor = monitor
            self.handlers = {}
        def connect(self, event, handler):
            self.handlers[event] = handler
        def disconnect(self, event):
            del self.handlers[event]
        def event(self, event, device):
            self.handlers[event](self, device)
    with mock.patch('pemmican.gui.MonitorObserver', MonitorObserver) as observer:
        yield observer


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

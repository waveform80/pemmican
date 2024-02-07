import dbus


class Notifications:
    """
    Wraps the methods of the DBus Notifications freedesktop service. If *bus*
    is not specified, it defaults to the DBus :class:`~dbus.SessionBus`.
    """
    def __init__(self, bus=None):
        if bus is None:
            bus = dbus.SessionBus()
        service = 'org.freedesktop.Notifications'
        server = bus.get_object(service, '/org/freedesktop/Notifications')
        self._intf = dbus.Interface(server, dbus_interface=service)
        self._pending = set()
        self.on_closed = None
        self.on_action = None
        bus.add_signal_receiver(
            self._notification_closed, 'NotificationClosed', service)
        bus.add_signal_receiver(
            self._action_invoked, 'ActionInvoked', service)

    def get_server_info(self):
        """
        Returns a :class:`dict` with keys "name", "vendor", "version",
        and "spec_version" mapped to the values returned by the service.
        """
        return {
            key: value
            for key, value in zip(
                ('name', 'vendor', 'version', 'spec_version'),
                self._intf.GetServerInformation()
            )
        }

    def get_capabilities(self):
        """
        Return a :class:`list` of :class:`str` detailing the capabilities of
        the notification service.

        Typical values include "actions", the server will display specified
        actions to the user, "body", the server supports notification bodies,
        "body-markup", the server supports limited markup in the notification
        body, and "persistence", the server supports persistence of
        notifications. See the `Desktop Notifications Specification`_ for all
        possible return values.

        .. _Desktop Notifications Specification:
            https://specifications.freedesktop.org/notification-spec/latest/
        """
        return self._intf.GetCapabilities()

    def notify(self, summary, *, body='', app_name='', app_icon='',
               replaces_id=0, actions=None, hints=None, timeout=-1):
        """
        Send a notification to the service.

        The *summary*, a brief :class:`str` summarizing the message, must be
        included. The *body* is the full message which may optionally contain
        a limited form of XML markup, if "body-markup" is included in the
        result of :meth:`get_capabilities`.

        The optional *app_name* and *app_icon* strings identify the application
        sending the notification.

        The *actions* parameter specifies a :class:`list` of ``(id, label)``
        tuples where *id* is the action identifier, and *label* is the string
        to display for the action. This is only supported if "actions" is
        included in the result of :meth:`get_capabilities`.

        The *hints* parameter is a :class:`dict` of optional hints passed to
        the notification service. A common hint is "urgency" which takes the
        value 0 (low), 1 (normal), or 2 (critical).

        The *timeout* specifies how long the notification will remain
        displayed. The default of -1 is system-dependent. 0 indicates a
        notification never times out.

        The return value is the ID of the displayed notification. This may be
        used in future calls with the *replaces_id* parameter to replace prior
        notifications.
        """
        if actions is None:
            actions = []
        else:
            actions = [item for (id, label) in actions for item in (id, label)]
        if hints is None:
            hints = {}
        msg_id = self._intf.Notify(
            app_name, replaces_id, app_icon, summary, body, actions, hints,
            timeout)
        self._pending.add(msg_id)
        return msg_id

    def remove(self, msg_id):
        """
        Forces the notification identified by *msg_id* (an :class:`int` as
        returned by :meth:`notify`) to be removed from display.
        """
        self._intf.CloseNotification(msg_id)

    def _action_invoked(self, msg_id, action_key):
        if msg_id in self._pending:
            if callable(self.on_action):
                self.on_action(msg_id, action_key)

    def _notification_closed(self, msg_id, reason):
        try:
            self._pending.remove(msg_id)
        except KeyError:
            pass
        else:
            if callable(self.on_closed):
                self.on_closed(msg_id, reason)

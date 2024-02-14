===============
Installation
===============

Pemmican should be installed by default on all Ubuntu for Raspberry Pi images
from the 24.04 release ("Noble Numbat") onwards. However, should you wish to
install it manually for whatever reason, there are two primary packages which
provide different configurations of the application:

* ``pemmican-server`` installs the MOTD ("Message of the Day") plugins only,
  which check for brownout and power supply negotiation states. As the name
  suggests, this is intended for usage on server installations which lack any
  kind of desktop notification service.

* ``pemmican-desktop`` installs two globally enabled user services which
  attempt to communicate with an implementation of the freedesktop notification
  service. One service warns about brownout and power supply negotiation issues
  (the same as the MOTD service), the other is runtime monitor for overcurrent
  and undervolt issues.

These both rely on the ``python3-pemmican`` package (which is the actual code
for both implementations).

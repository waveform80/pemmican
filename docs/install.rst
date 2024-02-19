.. pemmican: notifies users of Raspberry Pi 5 power issues
..
.. Copyright (c) 2024 Dave Jones <dave.jones@canonical.com>
.. Copyright (c) 2024 Canonical Ltd.
..
.. SPDX-License-Identifier: GPL-3.0-or-later

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

These both rely on the ``pemmican-common`` package (which is the actual code
for both implementations).


From PyPI
===========

You may also choose to install Pemmican from PyPI:

.. code-block:: console

    $ pip install "pemmican[gui]"

The ``[gui]`` option should be included only if you want to include the
dependencies for the graphical :program:`pemmican-reset` and
:program:`pemmican-mon` applications.

Please note that, in this case, you will need to add service definitions to
launch the applications yourself. For the graphical applications, the following
two service definitions are recommended:

.. literalinclude:: ../systemd/pemmican-reset.service
    :language: ini
    :caption: /usr/lib/systemd/user/pemmican-reset.service

.. literalinclude:: ../systemd/pemmican-monitor.service
    :language: ini
    :caption: /usr/lib/systemd/user/pemmican-monitor.service

As these are user services, they will either need to be enabled on a per-user
basis, or globally like so:

.. code-block:: console

    $ sudo systemctl --global enable pemmican-reset.service
    $ sudo systemctl --global enable pemmican-monitor.service

For the console application (:program:`pemmican-cli`) the following
:manpage:`update-motd(5)` script is recommended:

.. code-block:: bash
    :caption: /etc/update-motd.d/97-pemmican

    #!/bin/sh

    if [ -x /usr/bin/pemmican-cli ]; then
        exec /usr/bin/pemmican-cli
    elif [ -x /usr/local/bin/pemmican-cli ]; then
        exec /usr/local/bin/pemmican-cli
    fi

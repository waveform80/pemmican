.. pemmican: notifies users of Raspberry Pi 5 power issues
..
.. Copyright (c) 2024 Dave Jones <dave.jones@canonical.com>
.. Copyright (c) 2024 Canonical Ltd.
..
.. SPDX-License-Identifier: GPL-3.0

=============
pemmican-cli
=============

.. include:: subst.rst


Synopsis
========

.. code-block:: text

   usage: pemmican-cli [-h] [--version]


.. program:: pemmican-cli

Options
=======

.. option:: -h, --help

    show the help message and exit

.. option:: --version

    show program's version number and exit


Usage
=====

:program:`pemmican-cli` is intended to be a one-shot operation, typically
launched by :manpage:`update-motd(5)`. It first checks whether the last reset
occurred due to a brownout (undervolt) condition and, if it was, prints a
warning to stdout.

If you wish to suppress this warning for your user, touch the file
|user/brownout.inhibit|. If you wish to suppress this warning system-wide,
touch the file |system/brownout.inhibit|.

.. warning::

    It is strongly recommended that any such notice is heeded, as brownout is
    very likely to lead to any manner of other (hard to predict or replicate)
    issues up to and including data corruption.

    Put simply, suppressing this warning is probably a very bad idea!

If the last reset was normal (or there was no last reset), the script further
checks if the power supply negotiated a full 5A feed. If it did not, this also
results in a warning printed to stdout.

The Pi 5 can be reliably operated without a 5A feed, provided the peripherals
attached to it are relatively light in their power draw. Depending on
circumstance, you may well wish to suppress this warning which can be done for
your individual user by touching the file |user/max_current.inhibit| or
system-wide by touching |system/max_current.inhibit|.


See Also
========

.. only:: not man

    :doc:`pemmican-reset`, :doc:`pemmican-mon`

.. only:: man

    :manpage:`pemmican-reset(1)`, :manpage:`pemmican-mon(1)`


Bugs
====

|bug-link|

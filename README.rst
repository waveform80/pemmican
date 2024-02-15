========
Pemmican
========

Pemmican is a small utility which warns users of power supply issues on the
Raspberry Pi 5 platform. It provides a command line utility, intended for use
from the `update-motd`_ facility for non-graphical platforms, and two
GLib-based applications for use on graphical platforms, which expect to talk to
a DBus service implementing the freedesktop `notifications specification`_:

* ``pemmican-cli`` -- the command line utility

* ``pemmican-reset`` -- the one-shot notification service which warns of
  brownout reset issues, and failure to negotiate a 5A feed

* ``pemmican-mon`` -- the persistent notification service which warns of active
  undervolt or USB overcurrent events

Usage
=====

End users should never need to run these directly; distro packaging should
integrate these applications into the platform as appropriate (an MOTD plugin
for the command line application, and systemd user services activated by
``graphical-session.target`` for the graphical applications).

What's in a Name?
=================

This project started life as PMICmon (for `Power Management IC`_ monitor), but
I kept mis-pronouncing it as as `pemmican`_!

Useful Links
============

* `Source code`_ on GitHub

* `Issues`_ on GitHub

* `Documentation`_ on ReadTheDocs

.. _update-motd: https://manpages.ubuntu.com/manpages/noble/en/man5/update-motd.5.html
.. _notifications specification: https://specifications.freedesktop.org/notification-spec/latest/
.. _Power Management IC: https://en.wikipedia.org/wiki/Power_management_integrated_circuit
.. _pemmican: https://en.wikipedia.org/wiki/Pemmican
.. _Source code: https://github.com/waveform80/pemmican
.. _Issues: https://github.com/waveform80/pemmican/issues
.. _Documentation: https://pemmican.readthedocs.io/

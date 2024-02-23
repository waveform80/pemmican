# pemmican: notifies users of Raspberry Pi 5 power issues
#
# Copyright (c) 2024 Dave Jones <dave.jones@canonical.com>
# Copyright (c) 2024 Canonical Ltd.
#
# SPDX-License-Identifier: GPL-3.0

"""
This module contains the "main" entry point for the :program:`pemmican-cli`
application. This is a trivial console script, intended to be run from the
:manpage:`update-motd(5)` mechanism. All output is written to stdout.
"""

import os
import argparse
from pathlib import Path
from importlib import metadata
from textwrap import fill

from . import lang
from .power import reset_brownout, psu_max_current
from .const import (
    XDG_CONFIG_HOME,
    XDG_CONFIG_DIRS,
    RPI_PSU_URL,
    BROWNOUT_INHIBIT,
    MAX_CURRENT_INHIBIT,
)


def main(args=None):
    """
    The entry-point for the :program:`pemmican-cli` application. Takes the
    command line *args* as its only parameter and returns the exit code of
    the application.
    """
    with lang.init():
        parser = argparse.ArgumentParser(description=lang._(
            """
            Checks the Raspberry Pi 5's power status and reports if the last
            reset occurred due to a brownout (undervolt) situation, or if the
            current power supply failed to negotiate a 5A supply. This script
            is intended to be run as part of the man:update-motd(5) process. If
            you wish to suppress the warnings generated by this script, please
            refer to man:pemmican-cli(1) for more information.
            """))
        parser.add_argument(
            '--version', action='version',
            version=metadata.version(__package__))
        parser.parse_args(args)

        try:
            brownout = reset_brownout() and not any(
                (p / __package__ / BROWNOUT_INHIBIT).exists()
                for p in [XDG_CONFIG_HOME] + XDG_CONFIG_DIRS)
            max_current = (psu_max_current() < 5000) and not any(
                (p / __package__ / MAX_CURRENT_INHIBIT).exists()
                for p in [XDG_CONFIG_HOME] + XDG_CONFIG_DIRS)
        except OSError:
            # We're probably not on a Pi 5; just exit
            return 0

        # Check for brownout initially. If brownout caused a reset, don't
        # bother double-warning about an inadequate PSU
        if brownout:
            print()
            print(fill(lang._(
                'Reset due to low power; please check your power supply')))
        elif max_current:
            print()
            print(fill(lang._(
                'This power supply is not capable of supplying 5A; power '
                'to peripherals will be restricted')))
        if brownout or max_current:
            print()
            print(fill(lang._(
                'See man:pemmican-cli(1) for information on suppressing '
                'this warning, or {RPI_PSU_URL} for more information on the '
                'Raspberry Pi 5 power supply'.format(RPI_PSU_URL=RPI_PSU_URL)
                )))

        return 0

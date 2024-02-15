import os
import locale
import gettext
from pathlib import Path
from importlib import resources
from textwrap import fill

from .power import reset_brownout, psu_max_current
from .const import (
    XDG_CONFIG_DIRS,
    RPI_PSU_URL,
    BROWNOUT_INHIBIT,
    MAX_CURRENT_INHIBIT,
)


try:
    locale.setlocale(locale.LC_ALL, '')
except locale.Error:
    locale.setlocale(locale.LC_ALL, 'C')
    _ = lambda s: s
else:
    _ = gettext.gettext


def main(args=None):
    with resources.as_file(resources.files(__package__)) as pkg_path:
        locale_path = pkg_path / 'locale'
        gettext.bindtextdomain(__package__, str(locale_path))
        gettext.textdomain(__package__)

        try:
            brownout = reset_brownout() and not any(
                (p / __package__ / BROWNOUT_INHIBIT).exists()
                for p in XDG_CONFIG_DIRS)
            max_current = (psu_max_current() < 5000) and not any(
                (p / __package__ / MAX_CURRENT_INHIBIT).exists()
                for p in XDG_CONFIG_DIRS)
        except OSError:
            # We're probably not on a Pi 5; just exit
            return 0

        # Check for brownout initially. If brownout caused a reset, don't
        # bother double-warning about an inadequate PSU
        if brownout:
            print()
            print(fill(
                _('Reset due to low power; please check your power supply')))
        elif max_current:
            print()
            print(fill(
                _('This power supply is not capable of supplying 5A; power '
                  'to peripherals will be restricted')))
        if brownout or max_current:
            print()
            print(fill(
                _('See man:pemmican-cli(1) for information on suppressing '
                  'this warning, or {RPI_PSU_URL} for more information on the '
                  'Raspberry Pi 5 power supply')))

        return 0

# pemmican: notifies users of Raspberry Pi 5 power issues
#
# Copyright (c) 2024 Dave Jones <dave.jones@canonical.com>
# Copyright (c) 2024 Canonical Ltd.
#
# SPDX-License-Identifier: GPL-3.0-or-later

import locale
import gettext
from importlib import resources
from contextlib import contextmanager


_ = gettext.gettext

@contextmanager
def init():
    try:
        locale.setlocale(locale.LC_ALL, '')
    except locale.Error:
        locale.setlocale(locale.LC_ALL, 'C')

    with resources.as_file(resources.files(__package__)) as pkg_path:
        locale_path = pkg_path / 'locale'
        gettext.bindtextdomain(__package__, str(locale_path))
        gettext.textdomain(__package__)
        yield

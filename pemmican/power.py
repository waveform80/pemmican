# pemmican: notifies users of Raspberry Pi 5 power issues
#
# Copyright (c) 2024 Dave Jones <dave.jones@canonical.com>
# Copyright (c) 2024 Canonical Ltd.
#
# SPDX-License-Identifier: GPL-3.0-or-later

import struct

from pathlib import Path


DT_POWER = Path('/proc/device-tree/chosen/power')


def reset_brownout():
    """
    Returns :data:`True` if the device-tree reports that a power brownout
    (undervolt condition) was the cause of the last reset. Raises
    :exc:`OSError` if the reset condition cannot be queried (e.g. if this is
    executed on a non-Raspberry Pi).
    """
    # D-T values are big-endian (hence the > prefix)
    fmt = struct.Struct('>I')
    with (DT_POWER / 'power_reset').open('rb') as f:
        value, = fmt.unpack(f.read(fmt.size))
        return bool(value & 0x02)


def psu_max_current():
    """
    Returns the maximum current negotiated with the PSU by the power supply in
    mA. Ideally this should be 5000 (indicating a power supply capable of 5V at
    5A), but may be 3000 or lower. Raises :exc:`OSError` if the maximum current
    could not be queried (e.g. if this is executed on a non-Raspberry Pi).
    """
    fmt = struct.Struct('>I')
    with (DT_POWER / 'max_current').open('rb') as f:
        value, = fmt.unpack(f.read(fmt.size))
        return value

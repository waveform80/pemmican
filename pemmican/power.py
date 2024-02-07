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
    # NOTE: Seems this node has different names on RaspiOS and Ubuntu (or
    # changed name between kernel versions?)
    # TODO: Find out which of these is "The One True Name" going forward and
    # make sure it's in the try branch
    try:
        buf = (DT_POWER / 'reset_event').read_bytes()
    except FileNotFoundError:
        buf = (DT_POWER / 'power_reset').read_bytes()
    return bool(struct.unpack('>I', buf)[0] & 0x02)


def psu_max_current():
    """
    Returns the maximum current negotiated with the PSU by the power supply in
    mA. Ideally this should be 5000 (indicating a power supply capable of 5V at
    5A), but may be 3000 or lower. Raises :exc:`OSError` if the maximum current
    could not be queried (e.g. if this is executed on a non-Raspberry Pi).
    """
    return struct.unpack('>I', (DT_POWER / 'max_current').read_bytes())[0]

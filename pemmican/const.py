import os
from pathlib import Path


XDG_CONFIG_HOME = Path(os.environ.get(
    'XDG_CONFIG_HOME', os.path.expanduser('~/.config')))
XDG_CONFIG_DIRS = [
    Path(p)
    for p in os.environ.get(
        'XDG_CONFIG_DIRS', f'{XDG_CONFIG_HOME}:/etc/xdg').split(':')
]

RPI_PSU_URL = 'https://rptl.io/rpi5-power-supply-info'

BROWNOUT_INHIBIT    = 'brownout.inhibit'
MAX_CURRENT_INHIBIT = 'max_current.inhibit'
UNDERVOLT_INHIBIT   = 'undervolt.inhibit'
OVERCURRENT_INHIBIT = 'overcurrent.inhibit'

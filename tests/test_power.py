# pemmican: notifies users of Raspberry Pi 5 power issues
#
# Copyright (c) 2024 Dave Jones <dave.jones@canonical.com>
# Copyright (c) 2024 Canonical Ltd.
#
# SPDX-License-Identifier: GPL-3.0-or-later

import struct
from unittest import mock

import pytest

from pemmican.power import *


@pytest.fixture()
def dt_power(tmp_path):
    dt_power = tmp_path / 'power'
    with mock.patch('pemmican.power.DT_POWER', dt_power) as p:
        dt_power.mkdir()
        (dt_power / 'power_reset').write_bytes(struct.pack('>I', 0))
        (dt_power / 'max_current').write_bytes(struct.pack('>I', 5000))
        yield dt_power


def test_reset_brownout(dt_power):
    assert not reset_brownout()
    (dt_power / 'power_reset').write_bytes(struct.pack('>I', 2))
    assert reset_brownout()


def test_psu_max_current(dt_power):
    assert psu_max_current() == 5000
    (dt_power / 'max_current').write_bytes(struct.pack('>I', 3000))
    assert psu_max_current() == 3000

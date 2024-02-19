# pemmican: notifies users of Raspberry Pi 5 power issues
#
# Copyright (c) 2024 Dave Jones <dave.jones@canonical.com>
# Copyright (c) 2024 Canonical Ltd.
#
# SPDX-License-Identifier: GPL-3.0-or-later

from unittest import mock

import pytest

from pemmican.cli import *


def test_help(capsys):
    with pytest.raises(SystemExit) as err:
        main(['--version'])
    assert err.value.code == 0
    capture = capsys.readouterr()
    assert capture.out.strip() == '1.0.1'

    with pytest.raises(SystemExit) as err:
        main(['--help'])
    assert err.value.code == 0
    capture = capsys.readouterr()
    assert capture.out.strip().startswith('usage:')


def test_lang_fallback(capsys):
    import locale
    with mock.patch('pemmican.lang.locale.setlocale') as setlocale:
        setlocale.side_effect = [locale.Error, None]
        with pytest.raises(SystemExit) as err:
            main(['--version'])
        assert err.value.code == 0
        # Ensure we fell back to C locale on initial failure
        assert setlocale.call_count == 2
        assert setlocale.call_args.args == (locale.LC_ALL, 'C')


def test_regular_operation(capsys):
    with (
        mock.patch('pemmican.cli.reset_brownout') as reset_brownout,
        mock.patch('pemmican.cli.psu_max_current') as psu_max_current,
    ):
        reset_brownout.return_value = False
        psu_max_current.return_value = 5000
        assert main([]) == 0
        capture = capsys.readouterr()
        assert capture.out.strip() == ''


def test_non_pi_operation(capsys):
    with (
        mock.patch('pemmican.cli.reset_brownout') as reset_brownout,
        mock.patch('pemmican.cli.psu_max_current') as psu_max_current,
    ):
        reset_brownout.side_effect = FileNotFoundError('no such file or directory')
        psu_max_current.return_value = 5000
        assert main([]) == 0
        capture = capsys.readouterr()
        assert capture.out.strip() == ''


def test_brownout(capsys):
    with (
        mock.patch('pemmican.cli.reset_brownout') as reset_brownout,
        mock.patch('pemmican.cli.psu_max_current') as psu_max_current,
    ):
        reset_brownout.return_value = True
        psu_max_current.return_value = 3000
        assert main([]) == 0
        capture = capsys.readouterr()
        out = capture.out.strip()
        assert out.startswith('Reset due to low power')
        assert 'man:pemmican-cli(1)' in out
        assert RPI_PSU_URL in out
        # Note: PSU max current is also reported low (3A), but this doesn't
        # result in output
        assert '5A' not in out


def test_max_current(capsys):
    with (
        mock.patch('pemmican.cli.reset_brownout') as reset_brownout,
        mock.patch('pemmican.cli.psu_max_current') as psu_max_current,
    ):
        reset_brownout.return_value = False
        psu_max_current.return_value = 3000
        assert main([]) == 0
        capture = capsys.readouterr()
        out = capture.out.strip()
        assert out.startswith('This power supply is not capable')
        assert 'man:pemmican-cli(1)' in out
        assert RPI_PSU_URL in out
        assert 'Reset due to low power' not in out

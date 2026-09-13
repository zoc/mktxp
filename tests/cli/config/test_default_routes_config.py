# coding=utf8
## Copyright (c) 2020 Arseniy Kuznetsov
##
## This program is free software; you can redistribute it and/or
## modify it under the terms of the GNU General Public License
## as published by the Free Software Foundation; either version 2
## of the License, or (at your option) any later version.
##
## This program is distributed in the hope that it will be useful,
## but WITHOUT ANY WARRANTY; without even the implied warranty of
## MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
## GNU General Public License for more details.

import pytest
from configobj import ConfigObj
from mktxp.cli.config import MKTXPConfigHandler, MKTXPConfigKeys, ConfigEntry, CustomConfig


@pytest.mark.parametrize('key_name, key_value', [
    ('FE_DEFAULT_IP_ROUTES_KEY', 'default_ip_routes'),
    ('FE_DEFAULT_IPV6_ROUTES_KEY', 'default_ipv6_routes')
])
def test_default_routes_keys_registration(key_name, key_value):
    """
    Verifies the default routes keys are defined and default to off.
    """
    assert hasattr(MKTXPConfigKeys, key_name)
    assert getattr(MKTXPConfigKeys, key_name) == key_value

    assert key_value in MKTXPConfigKeys.BOOLEAN_KEYS_NO
    assert key_value not in MKTXPConfigKeys.BOOLEAN_KEYS_YES

    assert key_value in ConfigEntry.MKTXPConfigEntry._fields


def test_default_routes_keys_are_off_by_default(tmpdir):
    """
    Verifies that on an existing config without the new keys, these get injected as disabled.
    """
    mktxp_conf_path = tmpdir.join('mktxp.conf')
    _mktxp_conf_path = tmpdir.join('_mktxp.conf')
    mktxp_conf_path.write("""
[default]

[Sample-Router]
    hostname = 192.168.88.1
""")
    _mktxp_conf_path.write("""
[MKTXP]
verbose_mode = False
""")

    handler = MKTXPConfigHandler()
    handler(os_config=CustomConfig(str(tmpdir)))

    config_entry = handler.config_entry('Sample-Router')
    assert config_entry.default_ip_routes is False
    assert config_entry.default_ipv6_routes is False

    final_config = ConfigObj(str(mktxp_conf_path))
    latest_defaults = final_config[MKTXPConfigKeys.MKTXP_LATEST_DEFAULT_ENTRY_KEY]
    assert latest_defaults[MKTXPConfigKeys.FE_DEFAULT_IP_ROUTES_KEY] == 'False'
    assert latest_defaults[MKTXPConfigKeys.FE_DEFAULT_IPV6_ROUTES_KEY] == 'False'


def test_default_routes_keys_router_level_override(tmpdir):
    """
    Verifies that the default routes switches can be turned on per router entry.
    """
    mktxp_conf_path = tmpdir.join('mktxp.conf')
    _mktxp_conf_path = tmpdir.join('_mktxp.conf')
    mktxp_conf_path.write("""
[default]
    default_ip_routes = False
    default_ipv6_routes = False

[Sample-Router]
    hostname = 192.168.88.1
    default_ip_routes = True
    default_ipv6_routes = True
""")
    _mktxp_conf_path.write("""
[MKTXP]
verbose_mode = False
""")

    handler = MKTXPConfigHandler()
    handler(os_config=CustomConfig(str(tmpdir)))

    config_entry = handler.config_entry('Sample-Router')
    assert config_entry.default_ip_routes is True
    assert config_entry.default_ipv6_routes is True

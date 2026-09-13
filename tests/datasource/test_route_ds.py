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
from unittest.mock import Mock

from mktxp.datasource.route_ds import RouteMetricsDataSource
from mktxp.cli.config import MKTXPConfigKeys


class TestDefaultRouteRecords:

    @pytest.fixture
    def mock_router_entry(self):
        router_entry = Mock()
        router_entry.router_name = 'test_router'
        router_entry.config_entry.hostname = '192.168.1.1'
        router_entry.config_entry.custom_labels = None
        router_entry.router_id = {
            MKTXPConfigKeys.ROUTERBOARD_NAME: 'test_router',
            MKTXPConfigKeys.ROUTERBOARD_ADDRESS: '192.168.1.1'
        }

        resource = Mock()
        router_api = Mock()
        router_api.get_resource.return_value = resource
        router_entry.api_connection.router_api.return_value = router_api

        return router_entry, router_api, resource

    def test_default_route_records_ipv4(self, mock_router_entry):
        router_entry, router_api, resource = mock_router_entry
        resource.call.return_value = [
            {'dst-address': '0.0.0.0/0', 'gateway': '10.0.0.1', 'routing-table': 'main', 'comment': 'ISP1 primary', 'active': 'true'},
            {'dst-address': '0.0.0.0/0', 'gateway': '10.0.1.1', 'routing-table': 'backup', 'comment': 'ISP2 failover', 'active': 'false'}
        ]

        records = RouteMetricsDataSource.default_route_records(router_entry)

        router_api.get_resource.assert_called_once_with('/ip/route')
        resource.call.assert_called_once_with('print', {}, {'dst-address': '0.0.0.0/0'})

        assert records == [
            {'gateway': '10.0.0.1', 'routing_table': 'main', 'comment': 'ISP1 primary', 'active': 1, **router_entry.router_id},
            {'gateway': '10.0.1.1', 'routing_table': 'backup', 'comment': 'ISP2 failover', 'active': 0, **router_entry.router_id}
        ]

    def test_default_route_records_ipv6(self, mock_router_entry):
        router_entry, router_api, resource = mock_router_entry
        resource.call.return_value = [
            {'dst-address': '::/0', 'gateway': 'fe80::1%ether1', 'routing-table': 'main', 'comment': 'ISP1 v6', 'active': 'true'}
        ]

        records = RouteMetricsDataSource.default_route_records(router_entry, ipv6 = True)

        router_api.get_resource.assert_called_once_with('/ipv6/route')
        resource.call.assert_called_once_with('print', {}, {'dst-address': '::/0'})

        assert records == [
            {'gateway': 'fe80::1%ether1', 'routing_table': 'main', 'comment': 'ISP1 v6', 'active': 1, **router_entry.router_id}
        ]

    def test_default_route_records_filters_out_non_default_routes(self, mock_router_entry):
        router_entry, _, resource = mock_router_entry
        resource.call.return_value = [
            {'dst-address': '0.0.0.0/0', 'gateway': '10.0.0.1', 'routing-table': 'main', 'active': 'true'},
            {'dst-address': '192.168.88.0/24', 'gateway': 'bridge', 'routing-table': 'main', 'active': 'true'}
        ]

        records = RouteMetricsDataSource.default_route_records(router_entry)

        assert len(records) == 1
        assert records[0]['gateway'] == '10.0.0.1'

    def test_default_route_records_legacy_and_missing_fields(self, mock_router_entry):
        """ RouterOS v6 reports routing-mark, and omits it altogether for the main table
        """
        router_entry, _, resource = mock_router_entry
        resource.call.return_value = [
            {'dst-address': '0.0.0.0/0', 'gateway': '10.0.0.1', 'routing-mark': 'isp2', 'active': 'true'},
            {'dst-address': '0.0.0.0/0', 'gateway': '10.0.0.2', 'active': 'true'},
            {'dst-address': '0.0.0.0/0', 'active': 'false'}
        ]

        records = RouteMetricsDataSource.default_route_records(router_entry)

        assert records == [
            {'gateway': '10.0.0.1', 'routing_table': 'isp2', 'comment': '', 'active': 1, **router_entry.router_id},
            {'gateway': '10.0.0.2', 'routing_table': 'main', 'comment': '', 'active': 1, **router_entry.router_id},
            {'gateway': '', 'routing_table': 'main', 'comment': '', 'active': 0, **router_entry.router_id}
        ]

    def test_default_route_records_no_default_route(self, mock_router_entry):
        router_entry, _, resource = mock_router_entry
        resource.call.return_value = []

        assert RouteMetricsDataSource.default_route_records(router_entry) == []

    def test_default_route_records_api_error(self, mock_router_entry):
        router_entry, _, resource = mock_router_entry
        resource.call.side_effect = Exception('API connection failed')

        assert RouteMetricsDataSource.default_route_records(router_entry) is None

    def test_default_route_records_with_custom_labels(self, mock_router_entry):
        router_entry, _, resource = mock_router_entry
        router_entry.config_entry.custom_labels = 'dc:london'
        resource.call.return_value = [
            {'dst-address': '0.0.0.0/0', 'gateway': '10.0.0.1', 'routing-table': 'main', 'active': 'true'}
        ]

        records = RouteMetricsDataSource.default_route_records(router_entry)

        assert records[0][MKTXPConfigKeys.CUSTOM_LABELS_METADATA_ID] == {'dc': 'london'}

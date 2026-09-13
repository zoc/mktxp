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
from unittest.mock import Mock, patch

from mktxp.collector.route_collector import RouteCollector
from mktxp.cli.config import MKTXPConfigKeys


def _mock_router_entry(*, default_ip_routes = False, default_ipv6_routes = False):
    router_entry = Mock()
    router_entry.router_name = 'test_router'
    router_entry.config_entry.hostname = '192.168.1.1'
    router_entry.config_entry.route = False
    router_entry.config_entry.ipv6_route = False
    router_entry.config_entry.default_ip_routes = default_ip_routes
    router_entry.config_entry.default_ipv6_routes = default_ipv6_routes
    router_entry.config_entry.custom_labels = None
    router_entry.router_id = {
        MKTXPConfigKeys.ROUTERBOARD_NAME: 'test_router',
        MKTXPConfigKeys.ROUTERBOARD_ADDRESS: '192.168.1.1'
    }
    return router_entry


def test_default_routes_skipped_when_disabled():
    router_entry = _mock_router_entry()

    with patch('mktxp.collector.route_collector.RouteMetricsDataSource.default_route_records') as mock_ds:
        metrics = list(RouteCollector.collect(router_entry))

    mock_ds.assert_not_called()
    assert metrics == []


def test_default_ip_routes_metrics():
    router_entry = _mock_router_entry(default_ip_routes = True)

    default_route_records = [
        {'gateway': '10.0.0.1', 'routing_table': 'main', 'comment': 'ISP1 primary', 'active': 1, **router_entry.router_id},
        {'gateway': '10.0.1.1', 'routing_table': 'backup', 'comment': '', 'active': 0, **router_entry.router_id}
    ]

    with patch('mktxp.collector.route_collector.RouteMetricsDataSource.default_route_records') as mock_ds:
        mock_ds.return_value = default_route_records
        metrics = list(RouteCollector.collect(router_entry))

    mock_ds.assert_called_once_with(router_entry)
    assert len(metrics) == 1

    default_route_metric = metrics[0]
    assert default_route_metric.name == 'mktxp_routes_default_route'
    assert len(default_route_metric.samples) == 2

    samples = {sample.labels['gateway']: sample for sample in default_route_metric.samples}
    assert samples['10.0.0.1'].value == 1
    assert samples['10.0.0.1'].labels['routing_table'] == 'main'
    assert samples['10.0.0.1'].labels['comment'] == 'ISP1 primary'
    assert samples['10.0.1.1'].value == 0
    assert samples['10.0.1.1'].labels['routing_table'] == 'backup'
    assert samples['10.0.1.1'].labels['comment'] == ''

    for sample in default_route_metric.samples:
        assert sample.labels[MKTXPConfigKeys.ROUTERBOARD_NAME] == 'test_router'
        assert sample.labels[MKTXPConfigKeys.ROUTERBOARD_ADDRESS] == '192.168.1.1'


def test_default_ipv6_routes_metrics():
    router_entry = _mock_router_entry(default_ipv6_routes = True)

    default_route_records = [
        {'gateway': 'fe80::1%ether1', 'routing_table': 'main', 'comment': 'ISP1 v6', 'active': 1, **router_entry.router_id}
    ]

    with patch('mktxp.collector.route_collector.RouteMetricsDataSource.default_route_records') as mock_ds:
        mock_ds.return_value = default_route_records
        metrics = list(RouteCollector.collect(router_entry))

    mock_ds.assert_called_once_with(router_entry, ipv6 = True)
    assert len(metrics) == 1

    default_route_metric = metrics[0]
    assert default_route_metric.name == 'mktxp_routes_default_route_ipv6'
    assert len(default_route_metric.samples) == 1
    assert default_route_metric.samples[0].labels['gateway'] == 'fe80::1%ether1'
    assert default_route_metric.samples[0].labels['routing_table'] == 'main'
    assert default_route_metric.samples[0].labels['comment'] == 'ISP1 v6'
    assert default_route_metric.samples[0].value == 1


@pytest.mark.parametrize('records', [None, []])
def test_default_routes_no_records(records):
    router_entry = _mock_router_entry(default_ip_routes = True, default_ipv6_routes = True)

    with patch('mktxp.collector.route_collector.RouteMetricsDataSource.default_route_records') as mock_ds:
        mock_ds.return_value = records
        metrics = list(RouteCollector.collect(router_entry))

    assert mock_ds.call_count == 2
    assert metrics == []


def test_default_routes_independent_of_route_counts():
    """ Default routes metrics are gated on their own switches, not on the route counts ones
    """
    router_entry = _mock_router_entry(default_ip_routes = True)
    router_entry.config_entry.route = True

    with patch('mktxp.collector.route_collector.RouteMetricsDataSource.metric_records') as mock_counts_ds, \
         patch('mktxp.collector.route_collector.RouteMetricsDataSource.default_route_records') as mock_default_ds:
        mock_counts_ds.return_value = None
        mock_default_ds.return_value = [
            {'gateway': '10.0.0.1', 'routing_table': 'main', 'comment': '', 'active': 1, **router_entry.router_id}
        ]
        metrics = list(RouteCollector.collect(router_entry))

    assert [metric.name for metric in metrics] == ['mktxp_routes_default_route']


def test_default_routes_comment_separates_otherwise_identical_routes():
    """ Two routes sharing a gateway and routing table stay distinct series via their comments
    """
    router_entry = _mock_router_entry(default_ip_routes = True)

    default_route_records = [
        {'gateway': '10.0.0.1', 'routing_table': 'main', 'comment': 'ISP1 primary', 'active': 1, **router_entry.router_id},
        {'gateway': '10.0.0.1', 'routing_table': 'main', 'comment': 'ISP1 standby', 'active': 0, **router_entry.router_id}
    ]

    with patch('mktxp.collector.route_collector.RouteMetricsDataSource.default_route_records') as mock_ds:
        mock_ds.return_value = default_route_records
        metrics = list(RouteCollector.collect(router_entry))

    samples = metrics[0].samples
    assert len(samples) == 2
    assert {sample.labels['comment']: sample.value for sample in samples} == {
        'ISP1 primary': 1, 'ISP1 standby': 0
    }

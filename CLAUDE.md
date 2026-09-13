# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
pip install -e ".[test]"        # dev install with test deps
pytest                          # full suite (fast, all mocked - no router needed)
pytest tests/collector/test_route_collector.py::test_default_ip_routes_metrics   # single test
tox run -e py313                # single interpreter via tox (CI matrix: py39-py313)
```

There is no linter or formatter configured; match surrounding style.

Running the tool locally (`mktxp export`, `mktxp diag ...`, `mktxp rsc ...`) reads/writes real config in
`~/.config/mktxp/`. Use `--cfg-dir <path>` to point any command at a throwaway config directory instead.

## Architecture

Three product surfaces share one config layer and one RouterOS API connection layer, dispatched from
`mktxp/cli/dispatch.py`: the Prometheus exporter (`export`), CLI diagnostics (`diag`), and GitOps `.rsc`
config management (`rsc`, the only surface that needs no router).

### Exporter data flow

`ExportProcessor` (`mktxp/exporter/server.py`) registers `CollectorHandler` with the prometheus_client
`REGISTRY` and serves it over waitress. On each scrape:

`CollectorHandler` → for each `RouterEntry` → every collector in `CollectorRegistry` →
`<X>Collector.collect(router_entry)` → `<X>MetricsDataSource.metric_records(...)` → RouterOS API.

- **`mktxp/flow/`** — orchestration. `collector_registry.py` is the ordered list of collectors run per
  router; `collector_handler.py` runs entries sync or in a thread pool with per-router and total scrape
  timeouts; `router_entry.py` holds per-router connection, `router_id` labels, and RouterOS capability
  detection (wireless package type, ROS 6 vs 7); `probe_*.py` implements the `/probe` multi-target
  endpoint, where a router entry marked `module_only` is scraped on demand instead of on `/metrics`.
- **`mktxp/datasource/<x>_ds.py`** — one per RouterOS API domain. Fetches records and normalizes them via
  `BaseDSProcessor.trimmed_records`, which renames `-`/`.` keys to `_`, filters to `metric_labels`, injects
  `router_id` and parsed `custom_labels`, and applies a `translation_table` of per-field converters.
  `BaseDSProcessor.count_records` issues a server-side `count-only` print. Data sources catch their own
  exceptions, print a message, and return `None` — collectors must handle a `None`/empty result.
- **`mktxp/collector/<x>_collector.py`** — turns records into prometheus metric families via
  `BaseCollector.{gauge,counter,info}_collector(name, doc, records, metric_key, metric_labels)`. The base
  prepends `mktxp_` to every name, appends `routerboard_name`/`routerboard_address` and any custom labels,
  and de-duplicates records that would collide on the same label set. Collectors are generators that
  `yield` metric families and gate themselves on `router_entry.config_entry.<feature_key>` — the registry
  runs them unconditionally.
- **`mktxp/flow/processor/enrichment.py`** — cross-domain enrichment (DHCP lease name resolution,
  `interface_name_format` handling, unit parsing from `mktxp/utils/units.py`).

Metric naming: `mktxp_<domain>_<subject>`, with an `_ipv6` suffix for IPv6 variants of an IPv4 family.
Keep label cardinality low — volatile per-scrape values belong in gauges, not in info-metric labels.

### Adding a metric with a config switch

A feature flag touches four files in lockstep — all are required for the entry to be readable:

1. `mktxp/cli/config/keys.py` — add `FE_<X>_KEY = '<x>'`, and put it in `BOOLEAN_KEYS_NO` (default off) or
   `BOOLEAN_KEYS_YES` (default on); string/int switches go in `STR_KEYS`/`INT_KEYS` plus a
   `DEFAULT_FE_*` constant wired into `loader.py::_default_value_for_key`.
2. `mktxp/cli/config/models.py` — add the key to the `MKTXPConfigEntry` namedtuple.
3. `mktxp/cli/config/mktxp.conf` — add the documented line under `[default]` (this file is the template
   copied to a user's config dir on first run).
4. `docs/configuration.md` — add the row to the metrics collection switches table.

Existing user configs are migrated automatically: `loader.py` injects any key it does not find into a
`[new_default_parameters]` section of `mktxp.conf` and rewrites the file, so new keys must always have a
sensible default rather than being required.

### Config layer

`config_handler` (`mktxp/cli/config/loader.py`) is a module-level singleton, callable to (re)load from
disk. `mktxp.conf` holds router entries; `_mktxp.conf` holds the `[MKTXP]` daemon settings plus `[RSC]`
and `[DIAG]` sections. Every router entry resolves through `[default]`, so `config_entry(name)` returns a
fully populated `MKTXPConfigEntry` namedtuple. `models.py::mockSystemEntry` is the fallback system entry
used before initialization and by tests.

### Diagnostics and RSC

`mktxp/diag/` — one handler per domain in `DiagRegistry`, each declaring its CLI switch and reusing the
exporter's data sources; table rendering lives in `mktxp/cli/output/`.

`mktxp/rsc/` — a lexer/parser producing an AST (`ast.py`) of a RouterOS `.rsc` export, run through
`RSCEngine`: a `MiddlewarePipeline` (determinism sorter, script extractor, sanitizer) then a
`HandlerChain` of per-domain handlers that split the config into numbered files. Output must be
deterministic — the point is clean Git diffs.

## Tests

`tests/` mirrors the package layout. Everything is mocked (`unittest.mock`), no live router. Two
established styles for collectors: patch the data source (`patch('mktxp.collector.x_collector.XMetricsDataSource.metric_records')`)
to assert on yielded metric families, or mock the API chain
(`router_entry.api_connection.router_api().get_resource(path)`) to exercise the data source too. Assert on
`metric.name` and `metric.samples[].labels/value`, and always cover both the enabled and disabled state of
a feature switch. Config tests build a `MKTXPConfigHandler` against `CustomConfig(str(tmpdir))`.

Commit messages follow `<area>: <summary>` (e.g. `wireless: export client uptime/rates as gauges`).

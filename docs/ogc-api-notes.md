# OGC API notes

Design rationale and known limitations of the OGC API (pygeoapi) side of INTERPLANT. The step-by-step operations live in [`deploy/README.md`](../deploy/README.md); this file holds the reasoning behind them and the measured behaviour of the pinned pygeoapi release, so the runbook can stay short.

## What is deliberately not here

- No Docker except the pygeoapi container, whose exception is recorded in the
  next section together with the obligation it carries. `arctrl` is a
  pure-Python wheel and the endpoint needs only Flask, psycopg and gunicorn,
  so containers buy nothing for those while costing us CVE patching that
  Ubuntu otherwise does for free.
- No local nginx. The TLS reverse proxy already terminates TLS and buffers. A local
  nginx becomes worthwhile when pygeoapi needs to share a port.

## The one container on this box: pygeoapi

The deployment design decides for native installs, and names the case where
containers earn their place:
reproducing awkward dependencies. `arctrl` turned out not to be awkward - it
ships as a pure wheel with no runtime - but pygeoapi genuinely is, so it is the
deliberate exception to "no Docker" above. GDAL, rasterio, fiona and netCDF4
are not a clean install on a stock 24.04 box, and the upstream image is the
supported way they are served. Revisit the exception if pygeoapi ever becomes
installable without GDAL: the container's reason for existing is the dependency
alone, so an installable pygeoapi retires it the way `arctrl`'s pure-wheel
status retired the container for the OAI endpoint.

- The image is pinned to `geopython/pygeoapi:0.23.4` and must never be
  `latest`. Nothing rebuilds it and nothing watches these tags for CVEs; the
  pin is the only guarantee of what is being served.
- The unit forwards a fixed list of environment variables into the container
  with bare `docker run -e` flags, pulled from the unit's `EnvironmentFile`.
  The owner DSNs (`INTERPLANT_DSN`, `INTERPLANT_PG_DSN`) are deliberately
  not in that list, so the public container carries only the `pygeoapi_ro`
  credential. The bind address, port and URL prefix come from
  `CONTAINER_HOST`, `CONTAINER_PORT` and `SCRIPT_NAME`, not from the YAML's
  `server.bind` placeholders, which only pygeoapi's standalone dev server
  reads.
- **The obligation that comes with the exception.** The native-install security
  argument is not cancelled by it: native installs win because
  `unattended-upgrades` patches Ubuntu's own packages for free, and no process
  exists to do the same for a pinned image. Whoever operates this VM owns
  periodically checking for a newer pygeoapi release and bumping the pin. Left
  implicit, this becomes an unpatched public service - and the OGC API is
  public and unauthenticated.

### HTML templates

`ogc/templates` and `ogc/static` are bind-mounted read-only into the
container, so a deploy is a checkout plus a restart; nothing is copied or built.

`server.templates.static` replaces Flask's static folder outright, so
pygeoapi's own `default.css`, `logo.png` and `favicon.ico` no longer resolve.
That is intentional: every reference to them lived in `_base.html`, which we
now own. `pygeoapi.png` is vendored into `ogc/static/img/` so the
"Powered by pygeoapi" credit keeps working.

## Known OGC API limitations (pygeoapi 0.23.4)

Measured against the running service before the endpoint went public. Each is a limitation of the pinned pygeoapi, not of our data or config,
and none is fixable from configuration. `tests/stack/test_pygeoapi_known_limitations.py`
pins all three as `xfail`, so whichever one an upgrade fixes turns into an
`XPASS` and tells us to update this section.

**1. `q=` is silently a no-op. This is the dangerous one.**
`PostgreSQLProvider.query()` accepts a `q` argument and never uses it - there is
no `_get_q_filter` in `provider/sql.py`. So `?q=anything` returns HTTP 200 with
the complete unfiltered collection. A client cannot tell a search that matched
everything from a search that was discarded. `?q=zzzznonexistentzzz` returns all
153 records.

Consequence: do not tell anyone the catalog supports free-text search, and treat
the advertised `ogcapi-records-1/1.0/conf/opensearch` conformance class as false.

**2. Filtering on an array column returns HTTP 500.**
`_get_property_filters` (`provider/sql.py:507`) emits `column == value`
unconditionally, so `?omics_domains=imaging` becomes
`omics_domains = 'imaging'` against a `text[]` and PostgreSQL raises
`malformed array literal`. This affects `omics_domains`, `organism` and
`keywords` (text[]) and `contacts` and `externalIds` (jsonb) - five of the
ten advertised properties on every record collection. jsonb behaves exactly
as text[] here.

There is no workaround at our layer. It is not fixable by removing the column
from the provider's `properties` list, because `get_fields` builds the
filterable field set from every reflected column and ignores that list
(`provider/sql.py:288`). It is not fixable by switching the columns to `jsonb`
either - measured, same 500. CQL2 rejects them with a 400, `A_CONTAINS`
included.

We keep the arrays, because `keywords` genuinely is an array in OGC API Records
and flattening it to `"drought,heat"` would turn a loud 500 into a quiet wrong
answer. Omics filtering is served correctly by the seven `dataplant-*`
collections, which filter in SQL inside the view.

**3. The conformance list overstates what the service does.**
`/conformance` is emitted by pygeoapi from its own capabilities, not from our
config, so it advertises classes we do not satisfy:

| Advertised class | Reality |
|---|---|
| `ogcapi-features-4/1.0/conf/create-replace-delete` | Read-only. POST/PUT/DELETE return 400 `Collection is not editable`, and the DB role holds SELECT only. Verified nothing is written. |
| `ogcapi-records-1/1.0/conf/opensearch` | `q=` is a no-op - see 1. |
| `ogcapi-features-3/1.0/conf/queryables-query-parameters` | True for 5 of 8 properties; the three array ones 500 - see 2. |

Claims that were checked and hold: `ogcapi-records-1/1.0/conf/sorting`
(`sortby=title` and `sortby=-title` both order correctly) and `datetime`
filtering, which was broken until `time_field` was declared and now
discriminates properly on all nine collections.

## arc-locations is a query surface, not a catalogue

Measured on the live corpus: 442 points, but they come from only
**20 of 153 records**, and **387 of them (88%) come from a single ARC**
(`dataplant-dormancy-nhutran-2025`). The median contributing ARC has one point.
133 records carry no location at all.

Two things follow, both now stated in the collection's own description so they
reach clients through `/collections`:

**Feature ids are not durable.** An id is `<record id>:<ordinal>`, the ordinal
comes from the order the harvester emitted the locations in, and
`apply_catalog_views` rebuilds the view after every nightly publish. A given id
can therefore point at a different location tomorrow. Nothing citable should
use one: cite the `arc-records` entry and reach its points with
`?record_id=<id>`.

That is also why this collection can never be a harvest source for any
catalogue, AWI's included. A harvester's contract is stable identity across
runs; theirs additionally deletes anything not re-seen within 5 days, so
shifting ids would churn records in and out. Harvest `arc-records` items - one
document per ARC - which is what OGC API Records items are for. Harvesting
points would also *lose* the 87% of ARCs that have none.

**The advertised extent is world-wide but the data is not.** The bbox stays
`[-180,-90,180,90]` deliberately, so an empty result for a region means "no
location extracted for any ARC here", not "no research data here". Query
`arc-records` for the latter.

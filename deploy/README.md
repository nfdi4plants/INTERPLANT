# Deploying INTERPLANT on interplant-live

Target: `interplant-live` (192.0.2.10), Ubuntu 24.04.4, reached by SSH through
the `jump-host` jump host. `<admin>` has sudo (password required); `interplant`
(uid 1002) has none and is the account the services run as.

Add to `~/.ssh/config` on the workstation:

    Host interplant-live
        HostName 192.0.2.10
        ProxyJump jump-host

There is no CI path to this host. Installation is deliberate, and the VM pulls
its own code: `gitlab.fz-juelich.de` is reachable from the VM (verified
2026-08-20), so the deployed tree is a git checkout rather than an rsync copy.
That means `cat /opt/interplant/DEPLOYED_COMMIT` answers "what is running here?"
without guesswork.

## First install

Prerequisite: the code must be **pushed and merged to `main`**. The VM clones
from GitLab, so work that exists only on a workstation branch cannot be deployed.

One-time, in GitLab: Settings > Repository > Deploy tokens, create a token with
**only** the `read_repository` scope. Note the username and token.

On the VM:

    sudo install -m 0600 -o root -g root /dev/null /etc/interplant/deploy-token
    sudo tee /etc/interplant/deploy-token >/dev/null   # line 1: username, line 2: token

    sudo -u postgres createuser --pwprompt interplant
    sudo -u postgres createdb -O interplant interplant

    # Bootstrap the script itself once, then it self-updates from the checkout.
    curl -o /tmp/install.sh <raw URL of deploy/install.sh on main>
    sudo bash /tmp/install.sh main

Then edit `/etc/interplant/env`, put the real password in both DSN lines, and
`sudo systemctl restart interplant-oai`.

The deploy token is read-only and scoped to this repository. It never enters
`.git/config`: `install.sh` passes it through a per-invocation credential helper,
so the checkout on disk carries no credentials.

## Verifying before AWI is told anything

`install.sh` prints the `ufw` commands that restrict ports 8000 and 8001 and
runs none of them (there is no proxy address to allow yet). Until you run them
yourself, both ports are reachable from the whole internal network - confirm
the current state with `sudo ufw status` rather than assuming they are closed.

From the VM itself:

    curl -s 'http://192.0.2.10:8000/oai?verb=Identify' | head -20

Confirm `<baseURL>` reads `https://www.plabipd.de/oai` and not the internal
address. Then walk `ListRecords` by hand, following `resumptionToken` until a
response carries none:

    curl -s 'http://192.0.2.10:8000/oai?verb=ListRecords&metadataPrefix=oai_dc' \
        | grep -o '<resumptionToken>[^<]*'

Repeat with `&resumptionToken=<value>` in place of `metadataPrefix=oai_dc` until
the tag is empty or absent. The resumption handshake has never been executed
against a live client: AWI's offline emulation returns `None` for `file:` URLs,
so their multi-page loop was structurally unreachable in the test. `PAGE_SIZE =
100` (`oai/verbs.py:27`), so a full page carries a resumptionToken and the walk
is done once a response carries none. The corpus size is not known until the
first publish, so do not assume a particular number of pages ahead of time.
This is the last unverified item before the merge request.

## The first harvest

The nightly timer will do it, but run it once attended so you see the gate
verdict. Expect 30-60 minutes: the four mega-ARCs that used to dominate the run
are excluded from live enumeration (`harvester/exclusions.py`), and everything
else averages roughly 16s per ARC.

The unit bounds the run at `TimeoutStartSec=4h` and any single ARC's parse at
`--parse-timeout 900`. A SIGTERM at the 4h mark means the run was killed, not
that data was lost: staging is scratch and `public.records` is untouched until
the swap.

    sudo systemctl start interplant-refresh.service
    journalctl -u interplant-refresh -f

A refused gate leaves `public.records` untouched and exits non-zero. Read the
report under `/var/lib/interplant/harvest-runs/` before overriding anything.

**The timer comes back on by itself.** `install.sh` runs `systemctl enable --now
interplant-refresh.timer`, so deploying this re-enables and starts it. That means
an afternoon deploy gives you an unattended 02:00 run before you have watched one
finish. Either do the attended run the same day, or hold the timer off until you
have:

    sudo systemctl disable --now interplant-refresh.timer

and turn it back on when you are satisfied:

    sudo systemctl enable --now interplant-refresh.timer
    systemctl list-timers interplant-refresh.timer

`NEXT` must show a real date. A blank `NEXT` means the triggered service is
still running, not that the timer is broken.

### Parsing an excluded mega-ARC by hand

The four excluded ARCs are only kept out of the nightly; they are still
reachable on demand. `--local-dir` harvests ARC subdirectories found one level
under the path you give it (`harvester/acquire.py`'s `iter_local_arcs`), so
clone into a subdirectory rather than pointing `--local-dir` at the ARC itself.
This is a read-only public clone and needs no token:

    mkdir -p /tmp/megadir
    GIT_LFS_SKIP_SMUDGE=1 git clone --depth 1 \
      https://git.nfdi4plants.org/usadellab/BreedingValue-Public-Dataset.git \
      /tmp/megadir/BreedingValue-Public-Dataset

    sudo -u interplant /opt/interplant/.venv/bin/python -m harvester harvest \
      --local-dir /tmp/megadir --dry-run --out-dir /tmp/megarun

Budget about 7h40m for that one; that is the measured figure on this box,
2026-08-31. Keep `--dry-run`. Dropping it and adding `--dsn` writes straight to
`public.records` with no gate, and the next successful nightly swap deletes the
row again, because `publish.swap` truncates `public.records` and refills it from
staging. There is no supported way to pin a record that the nightly does not
re-stage.

## When the gate refuses

The snapshot in `published_projects` only advances on a successful swap, so a
refusal is not self-healing: the corpus stays stale, `--max-age-days 7` then
makes every subsequent night harvest unconditionally, and the gate refuses
again. Left alone, this means a nightly 30-60 minute clone storm against
`git.nfdi4plants.org` every night forever, with nobody told - there is no mail
relay or monitoring on this box, so nothing pages anyone. The only way this
gets noticed is a human looking.

**Notice it.** There is no alerting; check periodically:

    systemctl status interplant-refresh
    systemctl is-failed interplant-refresh
    journalctl -u interplant-refresh --since -7d

A green `systemctl status` is not enough. After any successful run, check the
audit report for parse timeouts:

    grep -l ParseTimeout /var/lib/interplant/harvest-runs/*.json

A hit means an ARC exceeded the 900s cap, so its record is silently missing from
the published corpus and AWI will expire it after five days. Add that ARC to
`harvester/exclusions.py` or investigate why it got slow.

**Diagnose it.** `journalctl -u interplant-refresh` names the refusal kind
(`empty`, `mismatch`, `floor`, `minimum`) and the counts involved. Cross-check
against the audit report it points to under
`/var/lib/interplant/harvest-runs/` - that report is the only record of which
ARCs were seen and what happened to each one that night.

**Override it deliberately, once you understand why it refused.** The
`--min-records` flag is the override, but it is not in
`interplant-refresh.service`'s `ExecStart`, so lowering it there would apply
every night, not just once. Run a one-off invocation instead, either by hand:

    sudo -u interplant /opt/interplant/.venv/bin/python -m harvester refresh \
        --out-dir /var/lib/interplant/harvest-runs --min-records 100

or transient, via `systemd-run`, if you want it logged under its own unit:

    sudo systemd-run --uid=interplant --pipe --wait \
        --property="EnvironmentFile=/etc/interplant/env" \
        --working-directory=/opt/interplant \
        /opt/interplant/.venv/bin/python -m harvester refresh \
        --out-dir /var/lib/interplant/harvest-runs --min-records 100

A lowered floor is a one-off judgment call about tonight's corpus, not a
standing configuration change - do not edit the unit to lower it permanently
without also revisiting whether `DEFAULT_MIN_RECORDS` itself should move.

## Upgrades

    ssh interplant-live 'sudo /opt/interplant/deploy/install.sh main'

It fetches, hard-resets to the requested ref, rewrites `DEPLOYED_COMMIT`,
rebuilds the venv from the pinned requirements, re-applies the schema
(idempotent), and restarts the units. Pass a tag instead of `main` to deploy a
specific release, or to roll back:

    ssh interplant-live 'sudo /opt/interplant/deploy/install.sh v1.2.3'

Rolling back the code does not roll back the database. The schema is additive so
far, but check before assuming an older tag can read a newer `records` table.

## Publishing the OGC API

pygeoapi serves the published corpus as nine collections, and this branch's
`deploy/interplant-pygeoapi.service` starts serving them from the internal
interface the moment `install.sh` runs. The public path under `www.plabipd.de`
is still to be agreed with Marie; `/ogc` is the example used everywhere below
and is already baked into `INTERPLANT_OGC_BASE_URL` - and therefore into every
`link` pygeoapi emits, so the path cannot be guessed now and corrected silently
later: anything already harvested would carry the wrong URLs. Roll out in
order, verifying each step, and stop before step 6 if anything fails.

1. Merge `feat/arc-location-geometry` first. The nine served collections are
   the catalog views that branch adds; this feature serves nothing without
   them.
2. Fill the new variables in `/etc/interplant/env` (see
   `deploy/interplant.env.example`): the six `INTERPLANT_PG_*` variables for
   the read-only database access, plus `CONTAINER_HOST`, `CONTAINER_PORT`
   and `INTERPLANT_OGC_BASE_URL`. Do NOT add `SCRIPT_NAME` here: both units
   load this file, gunicorn reads that variable from its environment, and a
   value here mounts the OAI endpoint under the OGC prefix, taking
   `www.plabipd.de/oai` down (it lives in `interplant-pygeoapi.service`). Keep
   `INTERPLANT_PG_PASSWORD` and `INTERPLANT_PG_RO_PASSWORD` identical:
   `install.sh` sets the `pygeoapi_ro` role's password from the RO variable,
   and pygeoapi itself connects with the plain one, so drift means a public
   500. Then `chmod 0600` and `chown root:root`, as the template demands.
3. Confirm Docker is installed on the VM: `docker --version`. Docker was
   absent when this box was surveyed (2026-08-20); if it still is, install it
   before running `install.sh`, because `interplant-pygeoapi.service` has
   `Requires=docker.service` and will not start without it.
4. Run `deploy/install.sh`. It also installs the postgis apt package and runs
   `CREATE EXTENSION IF NOT EXISTS postgis` against the `interplant` database,
   then applies the catalog views and creates the `pygeoapi_ro` role with the
   password from `INTERPLANT_PG_RO_PASSWORD`. The script restarts the unit
   rather than `enable --now`, so the container runs the just-deployed config,
   not the previous deploy's. This applies to EXISTING installs too - re-run
   `install.sh` (it is idempotent): the nightly refresh re-applies the catalog
   views after every publish, and a box without the extension fails there
   identically to a fresh install (`function st_geomfromgeojson(jsonb) does not
   exist`).
5. Verify locally on the VM before exposing anything:

        curl -s "http://192.0.2.10:8001/ogc/collections?f=json" | head -40
        curl -s "http://192.0.2.10:8001/ogc/collections/arc-locations/items?f=json&limit=2"

   Expect nine collections and real point features. The `/ogc` prefix is
   required, not optional: `SCRIPT_NAME=/ogc` mounts the API under that path,
   and a path without it makes gunicorn return HTTP 500 with a `<title>Bad
   Request</title>` "Configuration problem" page, which looks like a broken
   install. A 500 here is a path mismatch, not a failed deployment.
6. Ask Marie two things at once: to map the public path to
   `192.0.2.10:8001`, and whether her proxy passes the `/ogc` prefix
   through unchanged. The OAI precedent passes `/oai` through, and
   `SCRIPT_NAME=/ogc` assumes the same. Without the prefix gunicorn returns
   HTTP 500 with `<title>Bad Request</title>` (a "Configuration problem"
   page), which looks like a broken install - do not roll back over it: the
   path mismatch is the cause, not the deployment. Confirm the prefix with
   Marie (pass-through, as for `/oai`) and set `SCRIPT_NAME` to match
   whatever the proxy forwards (empty means the app serves at `/`) by editing
   `Environment=SCRIPT_NAME=` in `interplant-pygeoapi.service`, never the
   shared env file, with `INTERPLANT_OGC_BASE_URL` sharing that path. Then apply the `ufw` rules
   for 8001 that `install.sh` printed. Like port 8000, the script prints and
   does not apply: until you run them, 8001 is reachable from the whole
   internal network.
7. Verify from outside that the `links` carry the public URL, not the internal
   address. This is the `server.url` check: if the links say `192.0.2.10`,
   `INTERPLANT_OGC_BASE_URL` is wrong.
8. After the next nightly, confirm the publish succeeded with pygeoapi live:
   check the newest report under `/var/lib/interplant/harvest-runs/`. The lock
   behaviour is already pinned by `tests/stack/test_swap_survives_slow_reader.py`,
   so this is confirmation under real traffic, not the first time anyone finds
   out.

**Rolling back** is `sudo systemctl stop interplant-pygeoapi.service`: the
unit stops, the container leaves, and nothing else moves. The OAI endpoint is a
separate unit and is never loaded by this one, so `www.plabipd.de/oai` stays up
throughout - nothing here can affect earth-data.de.

## What is deliberately not here

- No Docker except the pygeoapi container, whose exception is recorded in the
  next section together with the obligation it carries. `arctrl` is a
  pure-Python wheel and the endpoint needs only Flask, psycopg and gunicorn,
  so containers buy nothing for those while costing us CVE patching that
  Ubuntu otherwise does for free.
- No local nginx. Marie's proxy already terminates TLS and buffers. A local
  nginx becomes worthwhile when pygeoapi needs to share a port.

## The one container on this box: pygeoapi

Decision 1 of the deployment design
(`docs/superpowers/specs/2026-08-20-production-deployment-design.md`) decides
for native installs, and names the case where containers earn their place:
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
- **The obligation that comes with the exception.** Decision 1's security
  argument is not cancelled by it: native installs win because
  `unattended-upgrades` patches Ubuntu's own packages for free, and no process
  exists to do the same for a pinned image. Whoever operates this VM owns
  periodically checking for a newer pygeoapi release and bumping the pin. Left
  implicit, this becomes an unpatched public service - and the OGC API is
  public and unauthenticated.

## Known OGC API limitations (pygeoapi 0.23.4)

Measured against the running service on 2026-09-15, before the endpoint went
public. Each is a limitation of the pinned pygeoapi, not of our data or config,
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
`keywords` - three of the eight advertised properties on every record
collection.

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

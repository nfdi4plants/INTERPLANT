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

From the VM itself, since ufw denies 8000 from elsewhere until Marie supplies
the proxy address:

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
100` (`oai/verbs.py:27`) and the verified corpus is 144 records
(`harvester/publish.py`), so expect two pages: 100 records with a
resumptionToken, then the remaining 44 with none. Do not hunt for a third page
that cannot exist at this corpus size; the page count will only grow as the
corpus does. This is the last unverified item before the merge request.

## The first harvest

The nightly timer will do it, but run it once attended, because the mega-ARC
parse time is unmeasured. Four ARCs have never been parsed to completion;
`usadellab/BreedingValue-Public-Dataset` has 91 assays and the only datapoint is
"25+ minutes" as a lower bound. Measure that one alone first. `--local-dir`
harvests ARC subdirectories found one level under the path you give it
(`harvester/acquire.py`'s `iter_local_arcs`), so clone the ARC into a
subdirectory rather than pointing `--local-dir` at the ARC itself. This is a
read-only public clone from DataPLANT's GitLab; it needs no token:

    mkdir -p /tmp/megadir
    git clone --depth 1 \
        https://git.nfdi4plants.org/usadellab/BreedingValue-Public-Dataset.git \
        /tmp/megadir/BreedingValue-Public-Dataset

    sudo -u interplant /opt/interplant/.venv/bin/python -m harvester harvest \
        --local-dir /tmp/megadir --dry-run --out-dir /tmp/megarun

Then the real thing, watching it:

    sudo systemctl start interplant-refresh.service
    journalctl -u interplant-refresh -f

A refused gate leaves `public.records` untouched and exits non-zero. Read the
report under `/var/lib/interplant/harvest-runs/` before overriding anything.

## Upgrades

    ssh interplant-live 'sudo /opt/interplant/deploy/install.sh main'

It fetches, hard-resets to the requested ref, rewrites `DEPLOYED_COMMIT`,
rebuilds the venv from the pinned requirements, re-applies the schema
(idempotent), and restarts the units. Pass a tag instead of `main` to deploy a
specific release, or to roll back:

    ssh interplant-live 'sudo /opt/interplant/deploy/install.sh v1.2.3'

Rolling back the code does not roll back the database. The schema is additive so
far, but check before assuming an older tag can read a newer `records` table.

## What is deliberately not here

- No Docker. `arctrl` is a pure-Python wheel and the endpoint needs only Flask,
  psycopg and gunicorn, so containers buy nothing here while costing us CVE
  patching that Ubuntu otherwise does for free.
- No PostGIS. Nothing in the OAI serving path needs it; it arrives with the
  catalogue work.
- No local nginx. Marie's proxy already terminates TLS and buffers. A local
  nginx becomes worthwhile when pygeoapi needs to share a port.

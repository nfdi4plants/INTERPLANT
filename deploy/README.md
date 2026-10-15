# Deploying INTERPLANT

Runbook for installing and operating INTERPLANT on a single Ubuntu VM. Design
rationale and OGC API limitations are in [`docs/ogc-api-notes.md`](../docs/ogc-api-notes.md).

## 1. Overview

Everything runs natively under systemd, except pygeoapi, which is the one
Docker container.

| Unit | What it is | Port |
|---|---|---|
| `interplant-oai.service` | OAI-PMH endpoint (gunicorn) | 8000 |
| `interplant-pygeoapi.service` | OGC API (pinned pygeoapi container) | 8001 |
| `interplant-refresh.service` + `.timer` | nightly harvest and publish, 02:00 | none |

TLS is terminated by a reverse proxy on another host. It forwards
`https://<public-host>/oai` to `<vm-ip>:8000` and `https://<public-host>/ogc`
to `<vm-ip>:8001`, passing the path prefix through unchanged. The services
run as the `interplant` account, which has no sudo.

## 2. Prerequisites

- Ubuntu VM, a sudo-capable `<admin-user>`, Docker (`sudo apt-get install -y docker.io`) and PostgreSQL.
- The VM can reach the GitLab host. The VM pulls its own code, so
  `cat /opt/interplant/DEPLOYED_COMMIT` answers "what is running here?".
- The code you want is pushed and merged to `main`.
- A GitLab deploy token with **only** `read_repository` (Settings > Repository > Deploy tokens).
- SSH config on your workstation:

      Host <vm-host>
          HostName <vm-ip>
          ProxyJump <jump-host>

## 3. First install

On the VM, as `<admin-user>`:

    sudo mkdir -p /etc/interplant
    sudo install -m 0600 -o root -g root /dev/null /etc/interplant/deploy-token
    sudo tee /etc/interplant/deploy-token >/dev/null   # line 1: username, line 2: token

    sudo -u postgres createuser --pwprompt interplant
    sudo -u postgres createdb -O interplant interplant

    curl -o /tmp/install.sh <raw URL of deploy/install.sh on main>
    sudo bash /tmp/install.sh main

The first run writes `/etc/interplant/env` from the template and stops. Edit it
(see `deploy/interplant.env.example`):

- the real database password in both DSN lines;
- `INTERPLANT_PG_PASSWORD` and `INTERPLANT_PG_RO_PASSWORD`, which must be identical;
- `INTERPLANT_OAI_BIND=<vm-ip>:8000`, the internal interface, never `0.0.0.0`;
- `CONTAINER_HOST=<vm-ip>`, `CONTAINER_PORT=8001`;
- `INTERPLANT_OAI_BASE_URL=https://<public-host>/oai` and `INTERPLANT_OGC_BASE_URL=https://<public-host>/ogc`.

Then re-run the installer:

    sudo /tmp/install.sh main

`install.sh` refuses to continue if a required key is missing, still a
placeholder, or if the OAI bind is `0.0.0.0`. The token never enters
`.git/config`.

## 4. Firewall

`install.sh` prints the `ufw` commands and runs none of them, so ports 8000 and
8001 stay open to the whole internal network until you run them. Substitute the
proxy's address and check with `sudo ufw status`:

    sudo ufw allow from <proxy-ip> to any port 8000 proto tcp
    sudo ufw deny 8000
    sudo ufw allow from <proxy-ip> to any port 8001 proto tcp
    sudo ufw deny 8001

## 5. Verify

OAI, from the VM:

    curl -s 'http://<vm-ip>:8000/oai?verb=Identify' | head -20
    curl -s 'http://<vm-ip>:8000/oai?verb=ListRecords&metadataPrefix=oai_dc' \
        | grep -o '<resumptionToken>[^<]*'

`<baseURL>` must be `https://<public-host>/oai`, not the internal address. Repeat
the `ListRecords` call with `&resumptionToken=<value>` instead of `metadataPrefix`
until a response carries no token (`PAGE_SIZE` is 100).

OGC, from the VM:

    curl -s 'http://<vm-ip>:8001/ogc/collections?f=json' | head -40
    curl -s 'http://<vm-ip>:8001/ogc/collections/arc-locations/items?f=json&limit=2'

Expect nine collections and real point features. The `/ogc` prefix is required:
without it gunicorn returns HTTP 500 with a "Configuration problem" page. That
is a path mismatch, not a broken install. From outside the VM, check that the
`links` in the same responses carry `https://<public-host>/ogc`, not `<vm-ip>`.

## 6. First harvest

Run it once attended to see the gate verdict. Expect 30-60 minutes.

    sudo systemctl start interplant-refresh.service
    journalctl -u interplant-refresh -f

The run is bounded by `TimeoutStartSec=4h` and `--parse-timeout 900` per ARC.
A kill at 4h loses nothing: staging is scratch and `public.records` is
untouched until the swap.

**The timer re-enables itself on every install** (`systemctl enable --now`), so a
deploy can start an unattended 02:00 run before you have watched one. To hold it off:

    sudo systemctl disable --now interplant-refresh.timer
    sudo systemctl enable --now interplant-refresh.timer     # when satisfied
    systemctl list-timers interplant-refresh.timer

`NEXT` must show a date. Blank means the triggered service is still running.

## 7. Upgrades and rollback

    ssh <vm-host> 'sudo /opt/interplant/deploy/install.sh main'
    ssh <vm-host> 'sudo /opt/interplant/deploy/install.sh v1.2.3'   # a tag: deploy or roll back

It fetches, hard-resets to the ref, rebuilds the venv, re-applies the schema
(idempotent) and restarts the units. A code rollback does not roll back the
database; check that an older tag can read the current `records` table.

## 8. Monitoring and when the gate refuses

There is no alerting or mail relay. A refused gate leaves `public.records`
untouched but is not self-healing: the corpus goes stale and the nightly
re-harvests everything, silently, until someone looks. Check weekly:

    systemctl is-failed interplant-refresh
    journalctl -u interplant-refresh --since -7d
    grep -l ParseTimeout /var/lib/interplant/harvest-runs/*.json

A `ParseTimeout` hit means that ARC's record is missing from the published
corpus. Add it to `harvester/exclusions.py` or find out why it was slow.

To read a refusal, `journalctl` names the kind (`empty`, `mismatch`, `floor`,
`minimum`) and the counts. The audit report under
`/var/lib/interplant/harvest-runs/` shows what happened to each ARC.

To override once, after you understand why it refused, run a one-off with a
lower floor (by hand, or logged under its own unit):

    sudo -u interplant /opt/interplant/.venv/bin/python -m harvester refresh \
        --out-dir /var/lib/interplant/harvest-runs --min-records 100

    sudo systemd-run --uid=interplant --pipe --wait \
        --property="EnvironmentFile=/etc/interplant/env" \
        --working-directory=/opt/interplant \
        /opt/interplant/.venv/bin/python -m harvester refresh \
        --out-dir /var/lib/interplant/harvest-runs --min-records 100

Never lower `--min-records` in the unit: it would apply every night.

## 9. Never hand-delete production records

The portal harvests whatever is published and expires records it no longer sees
after 5 days, so a truncated corpus deletes real records downstream. Stale
records are pruned by the nightly swap; do not `DELETE FROM records` by hand.

## 10. Parsing an excluded mega-ARC by hand

The excluded ARCs are only kept out of the nightly. `--local-dir` harvests
subdirectories one level below the path, so clone into a subdirectory:

    mkdir -p /tmp/megadir
    GIT_LFS_SKIP_SMUDGE=1 git clone --depth 1 \
      https://git.nfdi4plants.org/usadellab/BreedingValue-Public-Dataset.git \
      /tmp/megadir/BreedingValue-Public-Dataset
    sudo -u interplant /opt/interplant/.venv/bin/python -m harvester harvest \
      --local-dir /tmp/megadir --dry-run --out-dir /tmp/megarun

Budget about 7h40m. Keep `--dry-run`: without it the row is written with no
gate, and the next nightly swap deletes it, because the swap refills
`public.records` from staging.

## 11. pygeoapi operations

- The image is pinned in `interplant-pygeoapi.service` and must never be
  `latest`. Nothing watches it for CVEs; the VM operator owns checking for new
  releases and bumping the pin.
- Never put `SCRIPT_NAME` in `/etc/interplant/env`. Both units load that file,
  and a value there mounts the OAI endpoint under the OGC prefix and takes it
  down. It lives in the pygeoapi unit; to change the public path, edit that
  unit and `INTERPLANT_OGC_BASE_URL` together.
- Keep `INTERPLANT_PG_PASSWORD` equal to `INTERPLANT_PG_RO_PASSWORD`:
  `install.sh` sets the `pygeoapi_ro` role from the RO one, pygeoapi connects
  with the other, and drift is a public 500.
- `ogc/templates` and `ogc/static` are bind-mounted, so a deploy plus restart
  picks up changes. After changing a logo in `ogc/brand/src/`, run
  `make brand-assets` and commit the result.
- Rollback: `sudo systemctl stop interplant-pygeoapi`. Nothing else moves; the
  OAI endpoint is a separate unit.

## 12. More

Why pygeoapi is a container, known pygeoapi limitations and the semantics of
`arc-locations`: [`docs/ogc-api-notes.md`](../docs/ogc-api-notes.md).

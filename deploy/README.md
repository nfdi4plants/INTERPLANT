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

`install.sh` only prints the `ufw` commands that restrict port 8000; it does
not run them (there is no proxy address to allow yet). Until you run them
yourself, port 8000 is reachable from the whole internal network - confirm
the current state with `sudo ufw status` rather than assuming it is closed.

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

## What is deliberately not here

- No Docker. `arctrl` is a pure-Python wheel and the endpoint needs only Flask,
  psycopg and gunicorn, so containers buy nothing here while costing us CVE
  patching that Ubuntu otherwise does for free.
- No PostGIS. Nothing in the OAI serving path needs it; it arrives with the
  catalogue work.
- No local nginx. Marie's proxy already terminates TLS and buffers. A local
  nginx becomes worthwhile when pygeoapi needs to share a port.

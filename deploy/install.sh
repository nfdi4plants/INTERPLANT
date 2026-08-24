#!/usr/bin/env bash
# Install or upgrade INTERPLANT on interplant-live.
#
#   sudo ./install.sh [ref]     # ref defaults to main; pass a tag to roll back
#
# Run as a sudo-capable user, not as interplant. Idempotent: safe to
# re-run. The VM pulls its own code from gitlab.fz-juelich.de using the
# read-only deploy token at /etc/interplant/deploy-token.
set -euo pipefail

REPO=/opt/interplant
STATE=/var/lib/interplant
ENVFILE=/etc/interplant/env
TOKENFILE=/etc/interplant/deploy-token
ORIGIN=https://gitlab.fz-juelich.de/ibg-3/data-management/projects/interplant.git
REF=${1:-main}

echo "== packages =="
sudo apt-get update
sudo apt-get install -y postgresql python3-venv git

# Deploy-token credentials are supplied per invocation via -c, never written
# into .git/config, so the token does not end up readable in the checkout.
# TOKENFILE holds two lines: username, then token.
git_auth() {
    sudo git -c "credential.helper=!f() { \
        sed -n '1s/^/username=/p;2s/^/password=/p' $TOKENFILE; }; f" "$@"
}

echo "== database =="
# listen_addresses stays at the Ubuntu default of localhost. The endpoint
# reaches Postgres over loopback and nothing off-box ever should.
# Checks the role AND the database: a role-exists/database-missing state
# (half-finished first install, or a dropdb) used to sail past a role-only
# check and die at the schema step with a raw "database does not exist"
# error. A Postgres that is simply down also lands in this branch, so the
# message below does not assert the role is definitely missing.
role_ok=$(sudo -u postgres psql -tAc \
    "SELECT 1 FROM pg_roles WHERE rolname='interplant'")
db_ok=$(sudo -u postgres psql -tAc \
    "SELECT 1 FROM pg_database WHERE datname='interplant'")
if [ "$role_ok" != "1" ] || [ "$db_ok" != "1" ]; then
    echo "Role and/or database 'interplant' not found (or Postgres is not"
    echo "reachable as the postgres user). If Postgres is up, create them:"
    echo "  sudo -u postgres createuser --pwprompt interplant"
    echo "  sudo -u postgres createdb -O interplant interplant"
    exit 1
fi

echo "== code =="
sudo mkdir -p "$STATE/harvest-runs" "$(dirname "$ENVFILE")"
if [ ! -f "$TOKENFILE" ]; then
    echo "MISSING $TOKENFILE. Create a read-only deploy token in GitLab"
    echo "(Settings > Repository > Deploy tokens, scope read_repository), then:"
    echo "  sudo install -m 0600 -o root -g root /dev/null $TOKENFILE"
    echo "  sudo tee $TOKENFILE >/dev/null   # line 1: username, line 2: token"
    exit 1
fi
sudo chown root:root "$TOKENFILE"
sudo chmod 0600 "$TOKENFILE"

if [ -d "$REPO/.git" ]; then
    git_auth -C "$REPO" fetch --prune origin
else
    sudo mkdir -p "$REPO"
    git_auth clone "$ORIGIN" "$REPO"
fi
# --force so a local edit made in anger on the VM cannot block an upgrade.
sudo git -C "$REPO" checkout --force "$REF"
sudo git -C "$REPO" reset --hard "origin/$REF" 2>/dev/null \
    || sudo git -C "$REPO" reset --hard "$REF"

# Record what is actually deployed, so "is the fix live?" is answerable.
sudo git -C "$REPO" rev-parse HEAD | sudo tee "$REPO/DEPLOYED_COMMIT" >/dev/null

# Root-owned so the service cannot rewrite its own code.
sudo chown -R root:root "$REPO"
sudo chown -R interplant:interplant "$STATE"

echo "== venv =="
sudo python3 -m venv "$REPO/.venv"
sudo "$REPO/.venv/bin/pip" install --require-hashes -r "$REPO/deploy/requirements.txt"

echo "== env file =="
if [ ! -f "$ENVFILE" ]; then
    sudo cp "$REPO/deploy/interplant.env.example" "$ENVFILE"
    sudo chown root:root "$ENVFILE"
    sudo chmod 0600 "$ENVFILE"
    echo "WROTE $ENVFILE from the template. Fill in the password before starting."
    # The template's password is the CHANGE-ME placeholder. Continuing into
    # the schema step would connect with that placeholder and fail with a
    # confusing psycopg authentication error instead of stopping cleanly, and
    # would go on to enable the units against a database they cannot reach.
    echo "Edit $ENVFILE, then re-run install.sh."
    exit 1
fi

echo "== schema =="
# Read the env file with systemd-run rather than reconstructing it through
# xargs, which would mangle any password containing shell metacharacters.
sudo systemd-run --pipe --wait --quiet \
    --uid=interplant \
    --property="EnvironmentFile=$ENVFILE" \
    --working-directory="$REPO" \
    "$REPO/.venv/bin/python" -c \
    'import os; from harvester import db
c = db.connect(os.environ["INTERPLANT_PG_DSN"])
db.apply_schema(c)
print("schema applied")'

echo "== units =="
sudo cp "$REPO"/deploy/interplant-*.service "$REPO"/deploy/interplant-*.timer \
    /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable interplant-oai.service
# enable --now starts a STOPPED unit but is a no-op on one already running:
# `start` on an active unit does nothing. Without an explicit restart, an
# upgrade would rewrite DEPLOYED_COMMIT and the venv while gunicorn keeps
# serving the old code, making DEPLOYED_COMMIT an actively misleading answer
# to "is the fix live?". `restart` on an inactive unit still starts it, so
# this stays correct on the first install too. Do not simplify this back to
# `enable --now`.
sudo systemctl restart interplant-oai.service
sudo systemctl enable --now interplant-refresh.timer   # timer: --now is correct

echo "== firewall =="
echo "MANUAL STEP, not applied by this script. Once Marie supplies the proxy"
echo "address, run these yourself:"
echo "  sudo ufw allow from <PROXY_IP> to any port 8000 proto tcp"
echo "  sudo ufw deny 8000"
echo "Port 8000 is reachable from the whole internal network until you do."

echo "Done. Check: systemctl status interplant-oai; systemctl list-timers interplant-refresh"

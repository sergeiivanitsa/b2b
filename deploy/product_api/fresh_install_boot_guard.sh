#!/usr/bin/env bash
# Boot-time nginx admission guard for an incomplete production fresh install.
set -Eeuo pipefail
umask 027

if [[ $# -ne 2 ]]; then
  echo 'usage: fresh_install_boot_guard.sh STAGE RELEASE_SHA' >&2
  exit 2
fi

stage=$1
release_sha=$2
state_root=/var/lib/pork/deploy-state
active_receipt=$state_root/fresh-install-active.json
success_receipt=$state_root/fresh-install-success.json

[[ "$stage" = /* && -d "$stage" && ! -L "$stage" ]]
[[ "$release_sha" =~ ^[0-9a-f]{40}$ ]]
test -f "$stage/product_api_legacy_0015_h2_bootstrap.conf"
test ! -L "$stage/product_api_legacy_0015_h2_bootstrap.conf"

verify_receipt() {
  local path=$1
  local phase=$2
  test -f "$path" && test ! -L "$path"
  python3 - "$path" "$phase" "$release_sha" "$stage" <<'PY'
import json
import sys

path, phase, release_sha, stage = sys.argv[1:]
with open(path, encoding="utf-8", newline="") as handle:
    raw = handle.read()
data = json.loads(raw)
expected = {
    "phase": phase,
    "release_sha": release_sha,
    "schema_version": "production_fresh_install_global_v1",
    "stage": stage,
}
if data != expected or raw != json.dumps(expected, separators=(",", ":"), sort_keys=True) + "\n":
    raise SystemExit("fresh-install boot receipt identity mismatch; STOP")
PY
}

# A terminal receipt admits the already verified regular configuration.  Any
# other enabled-guard state must prove exact active ownership and synchronously
# replace the on-disk server configuration with maintenance before nginx may
# start.  The guard intentionally never starts or reloads nginx itself.
if test -e "$success_receipt" || test -L "$success_receipt"; then
  verify_receipt "$success_receipt" success
  exit 0
fi
verify_receipt "$active_receipt" active
install -m 640 "$stage/product_api_legacy_0015_h2_bootstrap.conf" \
  /etc/nginx/sites-available/pork.su.conf
nginx -t

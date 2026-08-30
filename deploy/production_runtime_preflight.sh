#!/usr/bin/env bash
# SHA-bound production preflight. All remote operations are read-only.
set -euo pipefail

if test "$#" -ne 9; then
  echo "production preflight requires nine exact arguments; STOP" >&2
  exit 2
fi

release_sha=$1
ru_target=$2
us_target=$3
ru_release_root=$4
us_release_root=$5
known_hosts=$6
drain_deadline=$7
stable_interval=$8
output_root=$9

[[ "$release_sha" =~ ^[0-9a-f]{40}$ ]]
[[ "$ru_target" =~ ^[A-Za-z0-9._-]+@[A-Za-z0-9.-]+$ ]]
[[ "$us_target" =~ ^[A-Za-z0-9._-]+@[A-Za-z0-9.-]+$ ]]
[[ "$ru_release_root" =~ ^/[A-Za-z0-9][A-Za-z0-9._-]*(/[A-Za-z0-9][A-Za-z0-9._-]*){2,}$ ]]
[[ "$us_release_root" =~ ^/[A-Za-z0-9][A-Za-z0-9._-]*(/[A-Za-z0-9][A-Za-z0-9._-]*){2,}$ ]]
[[ "$drain_deadline" =~ ^[1-9][0-9]*$ ]]
[[ "$stable_interval" =~ ^[1-9][0-9]*$ ]]
test "$stable_interval" -lt "$drain_deadline"
test -f "$known_hosts" && test ! -L "$known_hosts"
test -f deploy/product_api/worker_drain.py
test -f deploy/us/gateway_runtime_identity.py
mkdir -p "$output_root"
test -d "$output_root" && test ! -L "$output_root"

ssh_args=(-o BatchMode=yes -o StrictHostKeyChecking=yes -o "UserKnownHostsFile=$known_hosts")

ssh "${ssh_args[@]}" "$ru_target" bash -s -- "$ru_release_root" "$release_sha" <<'REMOTE' > "$output_root/ru-runtime.json"
set -euo pipefail
release_root=$1
candidate_release_sha=$2
state_root=/var/lib/pork/deploy-state
active_receipt=$state_root/fresh-install-active.json
success_receipt=$state_root/fresh-install-success.json

command -v docker >/dev/null
command -v systemctl >/dev/null
command -v curl >/dev/null
command -v python3 >/dev/null
command -v psql >/dev/null
test "$(id -u)" -eq 0
test -d "$release_root" && test ! -L "$release_root"
test "$(realpath -e -- "$release_root")" = "$release_root"
test ! -e "$release_root/$candidate_release_sha" && test ! -L "$release_root/$candidate_release_sha"
test -d "$state_root" && test ! -L "$state_root"
test ! -e "$active_receipt" && test ! -L "$active_receipt"
test -f "$success_receipt" && test ! -L "$success_receipt"
python3 - "$success_receipt" "$release_root" <<'PY'
import json
import re
import sys

path, release_root = sys.argv[1:]
raw = open(path, encoding="utf-8", newline="").read()
value = json.loads(raw)
release_sha = value.get("release_sha") if isinstance(value, dict) else None
if not isinstance(release_sha, str) or re.fullmatch(r"[0-9a-f]{40}", release_sha) is None:
    raise SystemExit("fresh-install success identity is invalid; STOP")
expected = {
    "phase": "success",
    "release_sha": release_sha,
    "schema_version": "production_fresh_install_global_v1",
    "stage": f"{release_root}/{release_sha}-fresh-install",
}
if value != expected or raw != json.dumps(expected, separators=(",", ":"), sort_keys=True) + "\n":
    raise SystemExit("fresh-install success receipt is not canonical; STOP")
PY

mapfile -t recovery_units < <(
  {
    systemctl list-units --all --type=service --full --no-legend --no-pager 'pork-production-fresh-install-*.service'
    systemctl list-unit-files --type=service --full --no-legend --no-pager 'pork-production-fresh-install-*.service'
    systemctl list-units --all --type=service --full --no-legend --no-pager 'pork-legacy-0015-bootstrap-*.service'
    systemctl list-unit-files --type=service --full --no-legend --no-pager 'pork-legacy-0015-bootstrap-*.service'
  } | awk 'NF {print $1}' | sort -u
)
for unit in "${recovery_units[@]}"; do
  [[ "$unit" =~ ^pork-(production-fresh-install|legacy-0015-bootstrap)-[a-z0-9-]+\.service$ ]]
  active_state=$(systemctl show --property=ActiveState --value "$unit")
  case "$active_state" in
    inactive) ;;
    *) echo "production recovery unit is not quiescent; STOP" >&2; exit 2 ;;
  esac
  if enabled_state=$(systemctl is-enabled "$unit" 2>/dev/null); then
    enabled_status=0
  else
    enabled_status=$?
  fi
  case "$enabled_state" in
    disabled|masked|static|indirect|not-found) ;;
    *) echo "production recovery unit remains enabled ($enabled_status); STOP" >&2; exit 2 ;;
  esac
done

product_id=$(docker compose -f /opt/b2b/docker-compose.product.yml --env-file /opt/b2b/.env.product ps -q product_api)
report_id=$(docker compose -f /opt/b2b/docker-compose.product.yml --env-file /opt/b2b/.env.product ps -q company_report_worker)
narrative_id=$(docker compose -f /opt/b2b/docker-compose.product.yml --env-file /opt/b2b/.env.product ps -q company_card_narrative_worker)
for container_id in "$product_id" "$report_id" "$narrative_id"; do
  [[ "$container_id" =~ ^[0-9a-f]{64}$ ]]
  test "$(docker inspect --format '{{.State.Running}}' "$container_id")" = true
  test "$(docker inspect --format '{{.HostConfig.RestartPolicy.Name}}' "$container_id")" = unless-stopped
done
product_image=$(docker inspect --format '{{.Image}}' "$product_id")
[[ "$product_image" =~ ^sha256:[0-9a-f]{64}$ ]]
test "$(docker inspect --format '{{.Image}}' "$report_id")" = "$product_image"
test "$(docker inspect --format '{{.Image}}' "$narrative_id")" = "$product_image"
release_rows=()
for container_id in "$product_id" "$report_id" "$narrative_id"; do
  mapfile -t rows < <(docker inspect --format '{{range .Config.Env}}{{println .}}{{end}}' "$container_id" | sed -n 's/^PRODUCT_RELEASE_COMMIT=//p')
  test "${#rows[@]}" -eq 1
  [[ "${rows[0]}" =~ ^[0-9a-f]{40}$ ]]
  release_rows+=("${rows[0]}")
done
test "${release_rows[0]}" = "${release_rows[1]}"
test "${release_rows[0]}" = "${release_rows[2]}"
curl --fail --silent --show-error http://127.0.0.1:8000/health >/dev/null
available_blocks=$(df -Pk "$release_root" | awk 'NR == 2 {print $4}')
[[ "$available_blocks" =~ ^[1-9][0-9]*$ ]]
python3 - "$candidate_release_sha" "${release_rows[0]}" "$product_id" "$report_id" "$narrative_id" "$product_image" "$available_blocks" <<'PY'
import json
import sys

candidate, current, product, report, narrative, image, available = sys.argv[1:]
value = {
    "available_blocks_1k": int(available),
    "candidate_release_sha": candidate,
    "current_product_image_id": image,
    "current_release_sha": current,
    "narrative_worker_container": narrative,
    "product_container": product,
    "report_worker_container": report,
    "schema_version": "production_ru_runtime_preflight_v1",
}
print(json.dumps(value, separators=(",", ":"), sort_keys=True))
PY
REMOTE

ssh "${ssh_args[@]}" "$ru_target" \
  "set -euo pipefail; report_id=\$(docker compose -f /opt/b2b/docker-compose.product.yml --env-file /opt/b2b/.env.product ps -q company_report_worker); narrative_id=\$(docker compose -f /opt/b2b/docker-compose.product.yml --env-file /opt/b2b/.env.product ps -q company_card_narrative_worker); python3 - --container \"\$report_id\" --container \"\$narrative_id\" --settings-container \"\$report_id\" --deadline-seconds '$drain_deadline' --stable-interval-seconds '$stable_interval' --validate-only --release-sha '$release_sha'" \
  < deploy/product_api/worker_drain.py > "$output_root/worker-drain.json"

ssh "${ssh_args[@]}" "$us_target" \
  "python3 - --release-root '$us_release_root' --candidate-release-sha '$release_sha' --environment-file /opt/b2b/.env.gateway --expected-loopback 127.0.0.1:8001 --health-url http://127.0.0.1:8001/health" \
  < deploy/us/gateway_runtime_identity.py > "$output_root/gateway-runtime.json"

python3 - "$output_root" "$release_sha" <<'PY'
import json
import re
import sys
from hashlib import sha256
from pathlib import Path

root = Path(sys.argv[1])
release_sha = sys.argv[2]
records = {}
for name in ("ru-runtime", "worker-drain", "gateway-runtime"):
    path = root / f"{name}.json"
    raw = path.read_bytes()
    if raw.startswith(b"\xef\xbb\xbf") or b"\r" in raw or not raw.endswith(b"\n"):
        raise SystemExit(f"{name} receipt bytes are not canonical; STOP")
    value = json.loads(raw.decode("utf-8"))
    canonical = (json.dumps(value, separators=(",", ":"), sort_keys=True) + "\n").encode()
    if raw != canonical:
        raise SystemExit(f"{name} receipt JSON is not canonical; STOP")
    records[name] = (value, sha256(raw).hexdigest())

ru, _ = records["ru-runtime"]
worker, _ = records["worker-drain"]
gateway, _ = records["gateway-runtime"]
if ru.get("candidate_release_sha") != release_sha:
    raise SystemExit("RU preflight release binding mismatch; STOP")
if worker.get("outcome") != "validated" or worker.get("release_sha") != release_sha:
    raise SystemExit("worker preflight release binding mismatch; STOP")
if gateway.get("identity_mode") != "prior" or gateway.get("requested_release_sha") != release_sha:
    raise SystemExit("Gateway preflight release binding mismatch; STOP")
if worker.get("report_worker_container") != ru.get("report_worker_container") or worker.get("narrative_worker_container") != ru.get("narrative_worker_container"):
    raise SystemExit("RU worker container binding changed during preflight; STOP")
if not all(re.fullmatch(r"[0-9a-f]{64}", digest) for _, digest in records.values()):
    raise SystemExit("preflight receipt digest is invalid; STOP")

combined = {
    "candidate_release_sha": release_sha,
    "gateway_runtime_sha256": records["gateway-runtime"][1],
    "ru_runtime_sha256": records["ru-runtime"][1],
    "schema_version": "production_runtime_preflight_v1",
    "worker_drain_sha256": records["worker-drain"][1],
}
(root / "production-runtime-preflight.json").write_text(
    json.dumps(combined, separators=(",", ":"), sort_keys=True) + "\n",
    encoding="utf-8",
    newline="\n",
)
PY

cat "$output_root/production-runtime-preflight.json"

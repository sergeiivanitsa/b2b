#!/usr/bin/env bash
# Durable, destructive, one-time production fresh-install state machine.
#
# Once schema-reset-armed exists this runner has no legacy/image rollback path.
# Every retry remains behind maintenance ingress and resumes the exact candidate
# until fresh-install-success is durable.
set -Eeuo pipefail
umask 027

if [[ $# -ne 7 ]]; then
  echo 'usage: fresh_install_runner.sh STAGE RELEASE_SHA SEED_SHA256 UNIT_NAME OPERATION_TIMEOUT IDENTITY_CREDENTIAL CONTROL_SHA' >&2
  exit 2
fi

stage=$1
release_sha=$2
seed_sha256=$3
unit_name=$4
operation_timeout=$5
identity_credential=$6
control_sha=$7
runner_gid=$(id -g)

[[ "$stage" = /* && -d "$stage" && ! -L "$stage" ]]
[[ "$release_sha" =~ ^[0-9a-f]{40}$ ]]
[[ "$control_sha" =~ ^[0-9a-f]{40}$ ]]
[[ "$seed_sha256" =~ ^[0-9a-f]{64}$ ]]
[[ "$unit_name" =~ ^pork-production-fresh-install-[a-z0-9-]+$ ]]
[[ "$operation_timeout" =~ ^[1-9][0-9]*$ ]]
test "$operation_timeout" -ge 30 && test "$operation_timeout" -le 900
test -f "$identity_credential" && test ! -L "$identity_credential"
test "$(stat -c '%u:%g:%a' -- "$identity_credential")" = 0:0:600
test "$EUID" -eq 0
test "$(id -gn)" = www-data
test "$runner_gid" = "$(getent group www-data | cut -d: -f3)"

exec 9<"$stage"
flock -x 9

bounded() {
  timeout --foreground --signal=TERM --kill-after=30 "${operation_timeout}s" "$@"
}

terminal_bounded() {
  timeout --foreground --signal=TERM --kill-after=30 120s "$@"
}

path_present() {
  test -e "$1" || test -L "$1"
}

# The protected-main workflow may intentionally repair deployment control
# while reusing an older build-once application release.  Bind this durable
# runner to that exact control checkout before any image is loaded or runtime
# state is changed.
test "$0" = "$stage/fresh_install_runner.sh"
test -f "$0" && test ! -L "$0"
test -f "$stage/deployment-control.json" && test ! -L "$stage/deployment-control.json"
runner_sha256=$(bounded sha256sum "$0" | cut -d' ' -f1)
[[ "$runner_sha256" =~ ^[0-9a-f]{64}$ ]]
bounded python3 - "$stage/deployment-control.json" "$control_sha" \
  "$release_sha" "$runner_sha256" <<'PY'
import json
import re
import sys

path, control_sha, release_sha, runner_sha256 = sys.argv[1:]
if (
    re.fullmatch(r"[0-9a-f]{40}", control_sha) is None
    or re.fullmatch(r"[0-9a-f]{40}", release_sha) is None
    or re.fullmatch(r"[0-9a-f]{64}", runner_sha256) is None
):
    raise SystemExit("deployment control identity invalid; STOP")
with open(path, encoding="utf-8", newline="") as handle:
    raw = handle.read()
value = {
    "control_sha": control_sha,
    "release_sha": release_sha,
    "runner_sha256": runner_sha256,
    "schema_version": "production_fresh_install_control_v1",
}
if (
    json.loads(raw) != value
    or raw != json.dumps(value, separators=(",", ":"), sort_keys=True) + "\n"
):
    raise SystemExit("deployment control receipt mismatch; STOP")
PY

marker() {
  local phase=$1
  local temporary="$stage/.$phase.$$.tmp"
  test ! -e "$stage/$phase" && test ! -L "$stage/$phase"
  test ! -e "$temporary" && test ! -L "$temporary"
  python3 - "$phase" "$release_sha" "$temporary" <<'PY'
import json
import os
from pathlib import Path
import sys

phase, release_sha, destination = sys.argv[1:]
payload = {
    "phase": phase,
    "release_sha": release_sha,
    "schema_version": "production_fresh_install_marker_v1",
}
path = Path(destination)
with path.open("xb") as handle:
    os.fchmod(handle.fileno(), 0o640)
    handle.write((json.dumps(payload, separators=(",", ":"), sort_keys=True) + "\n").encode())
    handle.flush()
    os.fsync(handle.fileno())
PY
  bounded mv -T "$temporary" "$stage/$phase"
  bounded sync -f "$stage"
}

marker_once() {
  local phase=$1
  if path_present "$stage/$phase"; then
    test -f "$stage/$phase" && test ! -L "$stage/$phase"
    python3 - "$stage/$phase" "$phase" "$release_sha" <<'PY'
import json
import sys
path, phase, release_sha = sys.argv[1:]
with open(path, encoding="utf-8", newline="") as handle:
    raw = handle.read()
data = json.loads(raw)
expected = {"phase": phase, "release_sha": release_sha, "schema_version": "production_fresh_install_marker_v1"}
if data != expected or raw != json.dumps(expected, separators=(",", ":"), sort_keys=True) + "\n":
    raise SystemExit("fresh-install marker identity mismatch; STOP")
PY
  else
    marker "$phase"
  fi
}

verify_gateway_receipt() {
  bounded python3 - "$stage/gateway-complete" \
    "$stage/release-manifest-$release_sha.json" "$release_sha" <<'PY'
import json
from pathlib import Path
import re
import sys

receipt_path = Path(sys.argv[1])
manifest_path = Path(sys.argv[2])
release_sha = sys.argv[3]
if re.fullmatch(r"[0-9a-f]{40}", release_sha) is None:
    raise SystemExit("exact Gateway receipt release identity invalid; STOP")
raw = receipt_path.read_text(encoding="utf-8")
receipt = json.loads(raw)
manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
image = manifest["images"][f"gateway-api-{release_sha}.oci.tar"]
allowed_gateway_image_ids = sorted({image.get("oci_digest"), image.get("config_digest")})
gateway_image_id = receipt.get("gateway_image_id")
expected = {
    "allowed_gateway_image_ids": allowed_gateway_image_ids,
    "gateway_image_id": gateway_image_id,
    "phase": "gateway-complete",
    "release_sha": release_sha,
    "schema_version": "production_fresh_install_gateway_v2",
}
if (
    not 1 <= len(allowed_gateway_image_ids) <= 2
    or any(
        not isinstance(item, str)
        or re.fullmatch(r"sha256:[0-9a-f]{64}", item) is None
        for item in allowed_gateway_image_ids
    )
    or not isinstance(gateway_image_id, str)
    or gateway_image_id not in allowed_gateway_image_ids
    or receipt != expected
    or raw != json.dumps(expected, separators=(",", ":"), sort_keys=True) + "\n"
):
    raise SystemExit("exact Gateway receipt mismatch; STOP")
PY
}

collect_ids() {
  local destination=$1
  shift
  local output line
  local -n values=$destination
  output=$("$@")
  values=()
  if test -n "$output"; then
    while IFS= read -r line; do
      [[ "$line" =~ ^[0-9a-f]{12,64}$ ]]
      values+=("$line")
    done <<< "$output"
  fi
}

readiness_run() {
  local deadline=$1
  shift
  local remaining=$((deadline - SECONDS))
  test "$remaining" -gt 0 || return 124
  timeout --foreground --signal=TERM --kill-after=1 "${remaining}s" "$@"
}

wait_product_ready() {
  local expected_id=$1
  local deadline=$((SECONDS + 30))
  local current_id current_image current_config_image current_running current_port current_env release_count release_value
  while (( SECONDS < deadline )); do
    if ! current_id=$(readiness_run "$deadline" env PRODUCT_ENV_FILE=/opt/b2b/.env.product \
      PRODUCT_IMAGE_TAG="$release_sha" PRODUCT_RELEASE_COMMIT="$release_sha" \
      docker compose -p "$project" --profile company-card-narrative \
      -f "$stage/docker-compose.product.yml" --env-file .env.product \
      ps -q --all product_api); then
      echo 'Product readiness container lookup failed or exceeded its shared deadline; STOP' >&2
      return 2
    fi
    if test "$current_id" != "$expected_id"; then
      echo 'Product readiness no longer targets the same Product container; STOP' >&2
      return 2
    fi
    if ! current_image=$(readiness_run "$deadline" docker inspect --format '{{.Image}}' "$current_id") || \
      ! current_config_image=$(readiness_run "$deadline" docker inspect --format '{{.Config.Image}}' "$current_id") || \
      ! current_running=$(readiness_run "$deadline" docker inspect --format '{{.State.Running}}' "$current_id") || \
      ! current_port=$(readiness_run "$deadline" docker port "$current_id" 8000/tcp) || \
      ! current_env=$(readiness_run "$deadline" docker inspect --format '{{range .Config.Env}}{{println .}}{{end}}' "$current_id"); then
      echo 'Product readiness identity inspection failed or exceeded its shared deadline; STOP' >&2
      return 2
    fi
    release_count=$(printf '%s\n' "$current_env" | sed -n '/^PRODUCT_RELEASE_COMMIT=/p' | wc -l)
    release_value=$(printf '%s\n' "$current_env" | sed -n 's/^PRODUCT_RELEASE_COMMIT=//p')
    if test "$current_image" != "$candidate_image" || \
      test "$current_config_image" != "b2b-product-api:$release_sha" || \
      test "$current_port" != 127.0.0.1:8000 || \
      test "$release_count" -ne 1 || test "$release_value" != "$release_sha"; then
      echo 'Product readiness identity changed from the signed candidate; STOP' >&2
      return 2
    fi
    if test "$current_running" = true && \
      readiness_run "$deadline" curl --connect-timeout 1 --max-time 2 --fail --silent --show-error \
        http://127.0.0.1:8000/health >/dev/null 2>&1; then
      return 0
    fi
    if test "$SECONDS" -lt "$deadline"; then
      sleep 1
    fi
  done
  echo "Product readiness deadline exceeded for id=$current_id running=$current_running image=$current_image config_image=$current_config_image; STOP" >&2
  return 2
}

stop_container() {
  local id=$1
  bounded docker update --restart=no "$id" >/dev/null
  if test "$(bounded docker inspect --format '{{.State.Running}}' "$id")" = true; then
    bounded docker kill --signal=TERM "$id" >/dev/null
    bounded docker wait "$id" >/dev/null
  fi
  test "$(bounded docker inspect --format '{{.State.Running}}' "$id")" = false
}

candidate_image_check() {
  local network=$1
  shift
  bounded docker run --rm --network "$network" \
    --env-file /opt/b2b/.env.product \
    --env "PRODUCT_RELEASE_COMMIT=$release_sha" \
    --mount "type=bind,source=$stage/fresh_install_candidate.py,target=/run/fresh_install_candidate.py,readonly" \
    "b2b-product-api:$release_sha" \
    python /run/fresh_install_candidate.py "$@" --release-sha "$release_sha"
}

signed_gateway_smoke_container() {
  local container=$1
  bounded docker exec -i "$container" python - gateway \
    --release-sha "$release_sha" < "$stage/fresh_install_candidate.py"
}

force_maintenance_ingress() {
  terminal_bounded install -m 640 \
    "$stage/product_api_legacy_0015_h2_bootstrap.conf" \
    /etc/nginx/sites-available/pork.su.conf
  terminal_bounded nginx -t
  # reload-or-restart is synchronous and also establishes maintenance when a
  # prior crash or reboot left nginx inactive.
  terminal_bounded systemctl reload-or-restart nginx
}

cleanup_boot_guard() {
  local guard=pork-production-fresh-install-ingress-guard.service
  local dropin=/etc/systemd/system/nginx.service.d/90-pork-production-fresh-install.conf
  local guard_path=/etc/systemd/system/$guard
  if path_present "$guard_path"; then
    terminal_bounded systemctl disable "$guard" >/dev/null
  fi
  if path_present "$dropin"; then
    test -f "$dropin" && test ! -L "$dropin"
    terminal_bounded unlink "$dropin"
  fi
  if path_present "$guard_path"; then
    test -f "$guard_path" && test ! -L "$guard_path"
    terminal_bounded unlink "$guard_path"
  fi
  terminal_bounded systemctl daemon-reload
  terminal_bounded systemctl stop "$guard" >/dev/null 2>&1 || true
}

verify_tree_access() {
  local root=$1
  local allow_current=${2:-false}
  [[ "$root" = /var/lib/pork/* ]]
  bounded python3 - "$root" "$EUID" "$runner_gid" "$allow_current" <<'PY'
import os
from pathlib import Path
import stat
import sys

root = Path(sys.argv[1])
uid, gid = map(int, sys.argv[2:4])
allow_current = sys.argv[4] == "true"
for current_root, directories, files in os.walk(root, followlinks=False):
    current = Path(current_root)
    metadata = current.stat(follow_symlinks=False)
    if current.is_symlink() or not stat.S_ISDIR(metadata.st_mode) or (metadata.st_uid, metadata.st_gid, stat.S_IMODE(metadata.st_mode)) != (uid, gid, 0o750):
        raise SystemExit("release directory identity invalid; STOP")
    for name in directories:
        path = current / name
        if path.is_symlink() and not (allow_current and current == root and name == "current"):
            raise SystemExit("release tree contains linked directory; STOP")
    for name in files:
        path = current / name
        metadata = path.stat(follow_symlinks=False)
        if path.is_symlink() or not stat.S_ISREG(metadata.st_mode) or (metadata.st_uid, metadata.st_gid, stat.S_IMODE(metadata.st_mode)) != (uid, gid, 0o640):
            raise SystemExit("release file identity invalid; STOP")
PY
  test -z "$(bounded runuser --user www-data --group www-data -- find "$root" -xdev \( -type d ! -executable -o -type f ! -readable \) -print -quit)"
}

expected_database_identity=$(cat "$identity_credential")
[[ "$expected_database_identity" =~ ^[0-9a-f]{64}$ ]]
expected_schema_inventory=$(
  python3 - "$stage/database-preflight.json" <<'PY'
import json
import re
import sys

preflight_raw = open(sys.argv[1], encoding="utf-8", newline="").read()
preflight = json.loads(preflight_raw)
if preflight_raw != json.dumps(preflight, separators=(",", ":"), sort_keys=True) + "\n" or preflight.get("phase") != "preflight":
    raise SystemExit("database preflight receipt invalid; STOP")
value = preflight.get("schema_inventory_sha256")
if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None:
    raise SystemExit("database digest identity invalid; STOP")
if preflight.get("alembic_revisions") != ["0015_claims_company_report_handoff"]:
    raise SystemExit("database preflight is not bound to the expected legacy database; STOP")
print(value)
PY
)
[[ "$expected_schema_inventory" =~ ^[0-9a-f]{64}$ ]]

db_guard() {
  local command=$1
  bounded docker run --rm --network host \
    --env-file /opt/b2b/.env.product \
    --env "EXPECTED_DATABASE_IDENTITY_SHA256=$expected_database_identity" \
    --env "EXPECTED_SCHEMA_INVENTORY_SHA256=$expected_schema_inventory" \
    --mount "type=bind,source=$stage/fresh_install_database.py,target=/run/fresh_install_database.py,readonly" \
    "b2b-product-api:$release_sha" python /run/fresh_install_database.py "$command" --release-sha "$release_sha"
}

disable_recovery_unit() {
  terminal_bounded systemctl disable "$unit_name.service" >/dev/null
}

global_receipt() {
  local phase=$1
  local state_root=/var/lib/pork/deploy-state
  local path="$state_root/fresh-install-$phase.json"
  local temporary="$state_root/.fresh-install-$phase.$$.tmp"
  bounded install -d -m 750 -o root -g root "$state_root"
  if path_present "$path"; then
    test -f "$path" && test ! -L "$path"
    bounded python3 - "$path" "$phase" "$release_sha" "$stage" <<'PY'
import json
import sys
path, phase, release_sha, stage = sys.argv[1:]
raw = open(path, encoding="utf-8", newline="").read()
data = json.loads(raw)
expected = {"phase": phase, "release_sha": release_sha, "schema_version": "production_fresh_install_global_v1", "stage": stage}
if data != expected or raw != json.dumps(expected, separators=(",", ":"), sort_keys=True) + "\n":
    raise SystemExit("another production fresh install owns the global marker; STOP")
PY
    return
  fi
  test ! -e "$temporary" && test ! -L "$temporary"
  python3 - "$temporary" "$phase" "$release_sha" "$stage" <<'PY'
import json
import os
import sys
path, phase, release_sha, stage = sys.argv[1:]
value = {"phase": phase, "release_sha": release_sha, "schema_version": "production_fresh_install_global_v1", "stage": stage}
with open(path, "xb") as handle:
    os.fchmod(handle.fileno(), 0o640)
    handle.write((json.dumps(value, separators=(",", ":"), sort_keys=True) + "\n").encode())
    handle.flush()
    os.fsync(handle.fileno())
PY
  bounded mv -T "$temporary" "$path"
  bounded sync -f "$state_root"
}

finish() {
  local status=$?
  trap - EXIT TERM INT HUP
  if path_present "$stage/fresh-install-success"; then
    # The canonical success marker is the terminal commit.  A signal or a
    # failed best-effort unit cleanup after that commit must never put an
    # already verified release back into maintenance.
    set +e
    marker_once fresh-install-success
    success_status=$?
    if test "$success_status" -eq 0; then
      cleanup_boot_guard
      guard_status=$?
      disable_recovery_unit
      unit_status=$?
      if test "$guard_status" -eq 0 && test "$unit_status" -eq 0; then
        exit 0
      fi
      exit 2
    fi
    set -e
    status=2
  fi
  if test "$status" -ne 0; then
    if path_present "$stage/schema-reset-armed" || path_present "$stage/ingress-armed"; then
      set +e
      force_maintenance_ingress
      maintenance_status=$?
      if test "$maintenance_status" -ne 0; then
        terminal_bounded systemctl stop nginx
      fi
      marker_once roll-forward-required
      set -e
    else
      marker_once maintenance-required
    fi
  fi
  exit "$status"
}
trap finish EXIT
trap 'exit 143' TERM INT HUP

unit_path="/etc/systemd/system/$unit_name.service"
test -f "$unit_path" && test ! -L "$unit_path"
bounded sha256sum --strict --check "$stage/fresh-install-tools-$release_sha.sha256"
path_present "$stage/gateway-complete"
verify_gateway_receipt
if path_present /var/lib/pork/deploy-state/fresh-install-success.json; then
  global_receipt success
fi
if path_present "$stage/fresh-install-success"; then
  marker_once fresh-install-success
  if path_present /var/lib/pork/deploy-state/fresh-install-active.json; then
    bounded unlink /var/lib/pork/deploy-state/fresh-install-active.json
    bounded sync -f /var/lib/pork/deploy-state
  fi
  disable_recovery_unit
  exit 0
fi
global_receipt active

# An armed destructive or regular-ingress cutover is a possible-publication
# boundary.  Every retry reasserts maintenance before image loading, storage
# reconciliation or any other slow work.
if path_present "$stage/schema-reset-armed" || path_present "$stage/ingress-armed"; then
  if path_present "$stage/schema-reset-armed"; then
    marker_once schema-reset-armed
  fi
  if path_present "$stage/ingress-armed"; then
    marker_once ingress-armed
  fi
  force_maintenance_ingress
  marker_once maintenance-ingress
fi

cd "$stage"
bounded sha256sum --strict --ignore-missing --check "checksums-$release_sha.txt"
bounded docker load --input "product-api-$release_sha.oci.tar" >/dev/null
mapfile -t allowed_product_image_ids < <(bounded python3 - \
  "release-manifest-$release_sha.json" "product-api-$release_sha.oci.tar" <<'PY'
import json
import re
import sys

record = json.load(open(sys.argv[1], encoding="utf-8"))["images"][sys.argv[2]]
allowed = sorted({record.get("oci_digest"), record.get("config_digest")})
if (
    not 1 <= len(allowed) <= 2
    or any(
        not isinstance(item, str)
        or re.fullmatch(r"sha256:[0-9a-f]{64}", item) is None
        for item in allowed
    )
):
    raise SystemExit("signed Product image identity pair is invalid; STOP")
print(*allowed, sep="\n")
PY
)
test "${#allowed_product_image_ids[@]}" -ge 1
test "${#allowed_product_image_ids[@]}" -le 2
candidate_image=$(bounded docker image inspect --format '{{.Id}}' "b2b-product-api:$release_sha")
candidate_image_allowed=false
for allowed_product_image_id in "${allowed_product_image_ids[@]}"; do
  if test "$candidate_image" = "$allowed_product_image_id"; then
    candidate_image_allowed=true
  fi
done
if test "$candidate_image_allowed" != true; then
  echo 'loaded Product runtime is outside the signed Product image identity pair; STOP' >&2
  exit 2
fi

project=$(cat "$stage/prior-product-compose-project")
provider_state=$(cat "$stage/prior-provider-state")
printf '%s\n' "$project" | grep -Eq '^[a-z0-9][a-z0-9_-]*$'
test "$provider_state" = enabled -o "$provider_state" = disabled
candidate_image_check none settings --provider-state "$provider_state"
candidate_image_check none alembic
candidate_image_check host gateway
marker_once gateway-signed-prearm

claims_root=/var/lib/pork/claims-uploads/v1
claims_target=/data/claims_uploads
claims_base=/var/lib/pork
claims_parent=$claims_base/claims-uploads
test -d "$claims_base" && test ! -L "$claims_base"
test "$(bounded realpath -e -- "$claims_base")" = "$claims_base"
test "$(bounded stat -c '%u' -- "$claims_base")" = 0
if path_present "$claims_parent"; then
  test -d "$claims_parent" && test ! -L "$claims_parent"
  test "$(bounded realpath -e -- "$claims_parent")" = "$claims_parent"
  test "$(bounded stat -c '%u:%g:%a' -- "$claims_parent")" = 0:0:750
else
  bounded install -d -m 750 -o root -g root "$claims_parent"
fi
test -d "$claims_parent" && test ! -L "$claims_parent"
test "$(bounded realpath -e -- "$claims_parent")" = "$claims_parent"
test "$(bounded stat -c '%u:%g:%a' -- "$claims_parent")" = 0:0:750
if ! path_present "$claims_root"; then
  bounded install -d -m 750 -o root -g root "$claims_root"
fi
test -d "$claims_root" && test ! -L "$claims_root"
test "$(bounded realpath -e -- "$claims_root")" = "$claims_root"
test "$(bounded stat -c '%u:%g:%a' -- "$claims_root")" = 0:0:750
bounded env PRODUCT_ENV_FILE=/opt/b2b/.env.product PRODUCT_IMAGE_TAG="$release_sha" PRODUCT_RELEASE_COMMIT="$release_sha" docker compose -f "$stage/docker-compose.product.yml" --env-file /opt/b2b/.env.product config --format json | bounded python3 -c 'import json,sys; root,target=sys.argv[1:]; data=json.load(sys.stdin); volumes=data.get("services",{}).get("product_api",{}).get("volumes",[]); matches=[item for item in volumes if item.get("target")==target]; (len(matches)==1 and matches[0].get("type")=="bind" and matches[0].get("source")==root and matches[0].get("read_only") is not True) or sys.exit("candidate Claims upload persistence mapping invalid; STOP")' "$claims_root" "$claims_target"

# Prepare immutable H2/Web roots.  No database or public runtime changes have
# happened yet; all archive graphs were already verified by exact-SHA QA.
seed_archive=company-public-h2-seed-bundle-e7478a2fba9aaca17829c3d99e89e8d83d4b3188.tgz
test "$(bounded sha256sum "$seed_archive" | cut -d' ' -f1)" = "$seed_sha256"
bounded install -d -m 750 -o root -g www-data /var/lib/pork/company-public-h2
bounded install -d -m 750 -o root -g www-data /var/lib/pork/company-public-h2/v1
bounded install -d -m 750 -o root -g www-data /var/lib/pork/web-ui
bounded install -d -m 750 -o root -g www-data /var/lib/pork/web-ui/v1
seed_extract=$(bounded mktemp -d -p "$stage" .seed-extract.XXXXXXXXXX)
candidate_extract=$(bounded mktemp -d -p "$stage" .candidate-extract.XXXXXXXXXX)
bounded chmod 750 "$seed_extract" "$candidate_extract"
bounded tar -xzf "$seed_archive" --no-same-owner --no-same-permissions --strip-components=1 -C "$seed_extract"
bounded python3 company_public_h2_seed.py verify-bundle "$seed_extract/seed-inventory.json" >/dev/null
bounded tar -xzf "company-public-h2-$release_sha.tgz" --no-same-owner --no-same-permissions --strip-components=1 -C "$candidate_extract"
storage_state=$(bounded python3 - "$seed_extract/seed-inventory.json" "$candidate_extract/public_h2_asset_manifest.json" /var/lib/pork/company-public-h2/v1 <<'PY'
from hashlib import sha256
import json
from pathlib import Path
import sys

inventory_path, candidate_path, root_value = map(Path, sys.argv[1:])
inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
seed = tuple(item["manifest_sha256"] for item in reversed(inventory["releases"]))
candidate = sha256(candidate_path.read_bytes()).hexdigest()
root = root_value
pointer = root / "manifest-set.json"
if not pointer.exists() and not pointer.is_symlink():
    if any(root.iterdir()):
        raise SystemExit("unmarked H2 root is not empty; STOP")
    print("empty")
else:
    data = json.loads(pointer.read_text(encoding="utf-8"))
    retained = tuple(data.get("retained_manifest_sha256", ()))
    if retained == seed:
        print("seeded")
    elif retained == (candidate, seed[0], seed[1]):
        print("candidate")
    else:
        raise SystemExit("H2 root is outside the exact resumable graph; STOP")
PY
)
case "$storage_state" in
  empty)
    bounded bash seed_company_public_h2_assets.sh "$seed_extract/seed-inventory.json" /var/lib/pork/company-public-h2/v1
    storage_state=seeded
    ;;
  seeded|candidate) ;;
  *) echo 'invalid H2 reconciliation state; STOP' >&2; exit 2 ;;
esac
bounded python3 company_public_h2_seed.py verify /var/lib/pork/company-public-h2/v1 /var/lib/pork/company-public-h2/v1 >/dev/null
force_maintenance_ingress
marker_once maintenance-ingress
if test "$storage_state" != candidate; then
  bounded bash install_company_public_h2_assets.sh "$candidate_extract" /var/lib/pork/company-public-h2/v1 127.0.0.1:443 https://pork.su "$candidate_extract/public_h2_asset_manifest.json"
fi
bounded python3 company_public_h2_seed.py verify /var/lib/pork/company-public-h2/v1 /var/lib/pork/company-public-h2/v1 >/dev/null
verify_tree_access /var/lib/pork/company-public-h2/v1
bounded rm -r -- "$seed_extract" "$candidate_extract"
marker_once storage-complete

# Stop every known Product-side DB writer before the destructive boundary and
# recheck it on each pre-migration retry rather than trusting a host marker.
if ! path_present "$stage/migration-complete"; then
  # Maintenance is already synchronously active.  Immediately before stopping
  # or removing legacy Product, re-prove the live container has no upload mount
  # and that its effective /data/claims_uploads is empty.  A stopped legacy
  # Product without both durable proofs is not a resumable state.
  collect_ids legacy_products bounded docker ps -aq \
    --filter label=com.docker.compose.service=product_api
  if test "${#legacy_products[@]}" -eq 1; then
    legacy_product=${legacy_products[0]}
    if test "$(bounded docker inspect --format '{{.State.Running}}' "$legacy_product")" = true; then
      test "$(bounded docker inspect --format '{{range .Mounts}}{{if eq .Destination "/data/claims_uploads"}}{{println .Destination}}{{end}}{{end}}' "$legacy_product")" = ""
      bounded docker exec -i "$legacy_product" python - legacy-claims \
        --release-sha "$release_sha" < "$stage/fresh_install_candidate.py"
      marker_once claims-legacy-checked
      marker_once claims-legacy-frozen
    else
      path_present "$stage/claims-legacy-checked"
      path_present "$stage/claims-legacy-frozen"
      marker_once claims-legacy-checked
      marker_once claims-legacy-frozen
    fi
  elif test "${#legacy_products[@]}" -eq 0; then
    path_present "$stage/claims-legacy-checked"
    path_present "$stage/claims-legacy-frozen"
    marker_once claims-legacy-checked
    marker_once claims-legacy-frozen
  else
    echo 'legacy Product topology is not singular; STOP' >&2
    exit 2
  fi
  if test "${#legacy_products[@]}" -eq 1; then
    stop_container "$legacy_product"
  fi
  for service in company_card_narrative_worker company_report_worker; do
    collect_ids ids bounded docker ps -aq --filter label=com.docker.compose.service="$service"
    for id in "${ids[@]}"; do
      stop_container "$id"
    done
  done
  for service in product_api company_report_worker company_card_narrative_worker; do
    collect_ids ids bounded docker ps -q --filter label=com.docker.compose.service="$service"
    test "${#ids[@]}" -eq 0
  done
  marker_once writers-stopped
fi

# Destructive boundary.  The transaction rechecks URL/name/server/role/owner,
# requires zero other sessions, captures the ACL and replaces only `public`.
if ! path_present "$stage/schema-reset-complete"; then
  # A historical marker cannot replace live readiness.  Re-run the exact
  # candidate signer immediately before every destructive attempt.
  candidate_image_check host gateway
  marker_once gateway-signed-destructive-boundary
  marker_once schema-reset-armed
  reset_tmp="$stage/.database-reset.$$.tmp"
  test ! -e "$reset_tmp" && test ! -L "$reset_tmp"
  db_guard reset > "$reset_tmp"
  bounded chmod 640 "$reset_tmp"
  bounded sync -f "$reset_tmp"
  bounded mv -T "$reset_tmp" "$stage/database-reset.json"
  bounded sync -f "$stage"
  marker_once schema-reset-complete
fi

# From here on failure may only leave maintenance and retry this exact SHA.
if ! path_present "$stage/migration-complete"; then
  if db_guard prepare-upgrade >/dev/null 2>&1; then
    bounded docker run --rm --network host --env-file /opt/b2b/.env.product "b2b-product-api:$release_sha" python -m alembic -c /app/alembic.ini upgrade head
  else
    # The only accepted alternative is a prior exact migration commit whose
    # host marker was interrupted.  A restored/wrong 0015 database fails both.
    db_guard verify-head >/dev/null
  fi
  migration_tmp="$stage/.database-migration.$$.tmp"
  db_guard verify-head > "$migration_tmp"
  bounded chmod 640 "$migration_tmp"
  bounded sync -f "$migration_tmp"
  bounded mv -T "$migration_tmp" "$stage/database-migration.json"
  bounded sync -f "$stage"
  marker_once migration-complete
fi
if path_present "$stage/product-complete"; then
  if path_present "$stage/ingress-armed"; then
    db_guard verify-live-runtime >/dev/null
  else
    db_guard verify-runtime >/dev/null
  fi
elif ! db_guard verify-head >/dev/null 2>&1; then
  # Product may have committed the sole superadmin during startup immediately
  # before a host crash, but no other application state is accepted.
  db_guard verify-runtime >/dev/null
fi

if ! path_present "$stage/product-complete"; then
  bounded install -m 640 docker-compose.product.yml /opt/b2b/docker-compose.product.yml
  cd /opt/b2b
  bounded env PRODUCT_ENV_FILE=/opt/b2b/.env.product PRODUCT_IMAGE_TAG="$release_sha" PRODUCT_RELEASE_COMMIT="$release_sha" docker compose -p "$project" --profile company-card-narrative -f "$stage/docker-compose.product.yml" --env-file .env.product up -d --no-build --force-recreate product_api company_report_worker company_card_narrative_worker
  product_id=
  for service in product_api company_report_worker company_card_narrative_worker; do
    id=$(bounded env PRODUCT_ENV_FILE=/opt/b2b/.env.product PRODUCT_IMAGE_TAG="$release_sha" PRODUCT_RELEASE_COMMIT="$release_sha" docker compose -p "$project" --profile company-card-narrative -f "$stage/docker-compose.product.yml" --env-file .env.product ps -q --all "$service")
    test -n "$id"
    test "$(bounded docker inspect --format '{{.Config.Image}}' "$id")" = "b2b-product-api:$release_sha"
    test "$(bounded docker inspect --format '{{.Image}}' "$id")" = "$candidate_image"
    if test "$service" = product_api; then
      product_id=$id
    else
      test "$(bounded docker inspect --format '{{.State.Running}}' "$id")" = true
    fi
  done
  test -n "$product_id"
  product_mount=$(bounded docker inspect --format '{{range .Mounts}}{{if eq .Destination "/data/claims_uploads"}}{{printf "%s|%s|%t" .Source .Destination .RW}}{{end}}{{end}}' "$product_id")
  test "$product_mount" = "/var/lib/pork/claims-uploads/v1|/data/claims_uploads|true"
  wait_product_ready "$product_id"
  db_guard verify-runtime >/dev/null
  marker_once product-complete
fi

if ! path_present "$stage/web-complete"; then
  cd "$stage"
  web_sha=$(bounded sha256sum "web-ui-$release_sha.tgz" | cut -d' ' -f1)
  bounded python3 install_web_ui_release.sh "web-ui-$release_sha.tgz" "$release_sha" /var/lib/pork/web-ui/v1 "$web_sha" 127.0.0.1:443 https://pork.su
  verify_tree_access /var/lib/pork/web-ui/v1 true
  marker_once web-complete
fi

cd /opt/b2b
product_id=$(bounded env PRODUCT_ENV_FILE=/opt/b2b/.env.product PRODUCT_IMAGE_TAG="$release_sha" PRODUCT_RELEASE_COMMIT="$release_sha" docker compose -p "$project" --profile company-card-narrative -f "$stage/docker-compose.product.yml" --env-file .env.product ps -q --all product_api)
wait_product_ready "$product_id"
bounded docker exec -i "$product_id" python - settings \
  --release-sha "$release_sha" --provider-state "$provider_state" \
  < "$stage/fresh_install_candidate.py"
signed_gateway_smoke_container "$product_id"
for service in product_api company_report_worker company_card_narrative_worker; do
  collect_ids ids bounded docker ps -q --filter label=com.docker.compose.service="$service"
  test "${#ids[@]}" -eq 1
  id=${ids[0]}
  test "$(bounded docker inspect --format '{{index .Config.Labels "com.docker.compose.project"}}' "$id")" = "$project"
  test "$(bounded docker inspect --format '{{.Config.Image}}' "$id")" = "b2b-product-api:$release_sha"
  test "$(bounded docker inspect --format '{{.Image}}' "$id")" = "$candidate_image"
  if test "$service" = product_api; then
    test "$id" = "$product_id"
  else
    test "$(bounded docker inspect --format '{{.State.Running}}' "$id")" = true
  fi
  test "$(bounded docker inspect --format '{{.HostConfig.RestartPolicy.Name}}' "$id")" = unless-stopped
done
test "$(bounded docker port "$product_id" 8000/tcp)" = 127.0.0.1:8000
product_mount=$(bounded docker inspect --format '{{range .Mounts}}{{if eq .Destination "/data/claims_uploads"}}{{printf "%s|%s|%t" .Source .Destination .RW}}{{end}}{{end}}' "$product_id")
test "$product_mount" = "/var/lib/pork/claims-uploads/v1|/data/claims_uploads|true"
if path_present "$stage/ingress-armed"; then
  db_guard verify-live-runtime >/dev/null
else
  # Before the first possible regular ingress exposure, the database must
  # still be the exact empty/default-off bootstrap state.
  db_guard verify-runtime >/dev/null
fi
marker_once ingress-armed
bounded install -m 640 "$stage/product_api.conf" /etc/nginx/sites-available/pork.su.conf
bounded nginx -t
bounded systemctl reload-or-restart nginx
bounded curl --connect-timeout 10 --max-time 30 --fail --silent --show-error --resolve pork.su:443:127.0.0.1 https://pork.su/ >/dev/null
code=$(bounded curl --connect-timeout 10 --max-time 30 --silent --output /dev/null --write-out '%{http_code}' --resolve pork.su:443:127.0.0.1 https://pork.su/api/internal/whoami)
test "$code" = 401
test "$(bounded readlink /var/lib/pork/web-ui/v1/current)" = "releases/$release_sha"
db_guard verify-live-runtime >/dev/null
marker_once ingress-complete
global_receipt success
if path_present /var/lib/pork/deploy-state/fresh-install-active.json; then
  bounded unlink /var/lib/pork/deploy-state/fresh-install-active.json
  bounded sync -f /var/lib/pork/deploy-state
fi
marker_once fresh-install-success
cleanup_boot_guard

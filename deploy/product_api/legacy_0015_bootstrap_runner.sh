#!/usr/bin/env bash
# Durable one-time legacy-0015 production bootstrap state machine.
# It is launched as a boot-enabled systemd service so runner cancellation or a
# host reboot cannot interrupt the marker-driven mutation/DB-first rollback.
set -Eeuo pipefail
umask 027

if [[ $# -ne 14 ]]; then
  echo 'usage: legacy_0015_bootstrap_runner.sh STAGE RELEASE PRIOR_RELEASE RECOVERY_HOOK BACKUP_ARTIFACT BACKUP_ID BACKUP_SHA256 HOOK_SHA256 DRAIN_DEADLINE STABLE_INTERVAL SEED_SHA256 UNIT_NAME OPERATION_TIMEOUT ROLLBACK_TIMEOUT' >&2
  exit 2
fi

stage=$1
release_sha=$2
prior_release_sha=$3
recovery_hook=$4
backup_artifact=$5
backup_id=$6
backup_sha256=$7
recovery_hook_sha256=$8
drain_deadline=$9
stable_interval=${10}
seed_sha256=${11}
unit_name=${12}
operation_timeout=${13}
rollback_timeout=${14}
runner_gid=$(id -g)

[[ "$stage" = /* && -d "$stage" && ! -L "$stage" ]]
[[ "$release_sha" =~ ^[0-9a-f]{40}$ ]]
[[ "$prior_release_sha" == 6bee95e881a3e9ea1fe324ca13c11ae239f896f4 ]]
[[ "$backup_id" =~ ^[A-Za-z0-9][A-Za-z0-9._:-]{7,127}$ ]]
[[ "$backup_sha256" =~ ^[0-9a-f]{64}$ ]]
[[ "$recovery_hook_sha256" =~ ^[0-9a-f]{64}$ ]]
[[ "$seed_sha256" =~ ^[0-9a-f]{64}$ ]]
[[ "$unit_name" =~ ^pork-legacy-0015-bootstrap-[a-z0-9-]+$ ]]
[[ "$operation_timeout" =~ ^[1-9][0-9]*$ ]]
[[ "$rollback_timeout" =~ ^[1-9][0-9]*$ ]]
[[ "$drain_deadline" =~ ^[0-9]+([.][0-9]+)?$ ]]
[[ "$stable_interval" =~ ^[0-9]+([.][0-9]+)?$ ]]
test "$EUID" -eq 0
test "$(id -gn)" = www-data
test "$runner_gid" = "$(getent group www-data | cut -d: -f3)"
test -f "$recovery_hook" && test ! -L "$recovery_hook" && test -x "$recovery_hook"
test -f "$backup_artifact" && test ! -L "$backup_artifact"

exec 9<"$stage"
flock -x 9

bounded() {
  timeout --foreground --signal=TERM --kill-after=30 "${operation_timeout}s" "$@"
}

rollback_bounded() {
  local limit=$rollback_timeout
  local remaining
  if test "${rollback_deadline_epoch:-0}" -gt 0; then
    remaining=$((rollback_deadline_epoch - EPOCHSECONDS - 90))
    test "$remaining" -gt 0 || return 124
    if test "$remaining" -lt "$limit"; then
      limit=$remaining
    fi
  fi
  timeout --foreground --signal=TERM --kill-after=30 "${limit}s" "$@"
}

terminal_bounded() {
  timeout --foreground --signal=TERM --kill-after=30 120s "$@"
}

path_present() {
  test -e "$1" || test -L "$1"
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

ensure_private_directory() {
  local path=$1
  local parent=${path%/*}
  local parent_mode
  [[ "$path" = /* && "$parent" = /* && "$parent" != / ]]
  test -d "$parent" && test ! -L "$parent"
  test "$(bounded realpath -e -- "$parent")" = "$parent"
  test "$(bounded stat -c '%u' -- "$parent")" = "$EUID"
  parent_mode=$(bounded stat -c '%a' -- "$parent")
  [[ "$parent_mode" =~ ^[0-7]{3,4}$ ]]
  (( (8#$parent_mode & 8#022) == 0 ))
  if test -e "$path" || test -L "$path"; then
    test -d "$path" && test ! -L "$path"
  else
    bounded install -d -m 750 "$path"
    bounded sync -f "$parent"
  fi
  test "$(bounded realpath -e -- "$path")" = "$path"
  test "$(bounded stat -c '%u:%g:%a' -- "$path")" = "$EUID:$runner_gid:750"
}

verify_nginx_tree_access() {
  local root=$1
  local allow_current=${2:-false}
  local inaccessible
  [[ "$root" = /var/lib/pork/* ]]
  test "$allow_current" = true -o "$allow_current" = false
  test -d "$root" && test ! -L "$root"
  bounded python3 - "$root" "$EUID" "$runner_gid" "$allow_current" <<'PY'
import os
from pathlib import Path
import stat
import sys

root = Path(sys.argv[1])
expected_uid = int(sys.argv[2])
expected_gid = int(sys.argv[3])
allow_current = sys.argv[4] == "true"
for current_root, directory_names, file_names in os.walk(root, followlinks=False):
    current = Path(current_root)
    metadata = current.stat(follow_symlinks=False)
    if (
        current.is_symlink()
        or not stat.S_ISDIR(metadata.st_mode)
        or metadata.st_uid != expected_uid
        or metadata.st_gid != expected_gid
        or stat.S_IMODE(metadata.st_mode) != 0o750
    ):
        raise SystemExit("nginx asset directory identity or permissions invalid; STOP")
    for name in directory_names:
        path = current / name
        if path.is_symlink() and not (
            allow_current and current == root and name == "current"
        ):
            raise SystemExit("nginx asset tree contains linked directory; STOP")
    for name in file_names:
        path = current / name
        if path.is_symlink():
            continue
        metadata = path.stat(follow_symlinks=False)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_uid != expected_uid
            or metadata.st_gid != expected_gid
            or stat.S_IMODE(metadata.st_mode) != 0o640
        ):
            raise SystemExit("nginx asset file identity or permissions invalid; STOP")
PY
  inaccessible=$(bounded runuser --user www-data --group www-data -- find "$root" -xdev \( -type d ! -executable -o -type f ! -readable \) -print -quit)
  test -z "$inaccessible"
}

test "$(bounded sha256sum "$recovery_hook" | cut -d' ' -f1)" = "$recovery_hook_sha256"
test "$(bounded sha256sum "$backup_artifact" | cut -d' ' -f1)" = "$backup_sha256"
bounded sha256sum --strict --check "$stage/legacy-bootstrap-tools-$release_sha.sha256"
bounded python3 - "$drain_deadline" "$stable_interval" "$operation_timeout" <<'PY'
import math
import sys

deadline, stable, operation = map(float, sys.argv[1:])
if not all(math.isfinite(value) and value > 0 for value in (deadline, stable, operation)):
    raise SystemExit("bootstrap timing contract invalid; STOP")
if stable >= deadline or deadline + 30 > operation:
    raise SystemExit("bootstrap drain does not fit the forward operation bound; STOP")
PY

unit_path="/etc/systemd/system/$unit_name.service"
wants_path="/etc/systemd/system/multi-user.target.wants/$unit_name.service"
test -f "$unit_path" && test ! -L "$unit_path"
if test -L "$wants_path"; then
  test "$(bounded readlink -f -- "$wants_path")" = "$unit_path"
else
  terminal_without_registration=false
  for terminal in bootstrap-success rollback-complete; do
    if test -f "$stage/$terminal" && test ! -L "$stage/$terminal" && test "$(cat "$stage/$terminal")" = "$release_sha"; then
      terminal_without_registration=true
    fi
  done
  test "$terminal_without_registration" = true
fi
bounded sync -f "$unit_path"
bounded sync -f /etc/systemd/system
if test -d /etc/systemd/system/multi-user.target.wants; then
  bounded sync -f /etc/systemd/system/multi-user.target.wants
fi

marker() {
  local name=$1
  local limiter=${2:-bounded}
  local temporary="$stage/.$name.$$.tmp"
  test ! -e "$stage/$name" && test ! -L "$stage/$name"
  test ! -e "$temporary" && test ! -L "$temporary"
  printf '%s\n' "$release_sha" > "$temporary"
  "$limiter" chmod 640 "$temporary"
  "$limiter" sync -f "$temporary"
  "$limiter" mv -T "$temporary" "$stage/$name"
  "$limiter" sync -f "$stage"
}

marker_once() {
  local name=$1
  local limiter=${2:-bounded}
  if test -e "$stage/$name" || test -L "$stage/$name"; then
    test -f "$stage/$name" && test ! -L "$stage/$name"
    test "$(cat "$stage/$name")" = "$release_sha"
  else
    marker "$name" "$limiter"
  fi
}

disable_recovery_unit() {
  terminal_bounded systemctl disable "$unit_name.service" >/dev/null
}

sole_legacy_revision() {
  local container=$1
  local revision
  revision=$(rollback_bounded docker exec -w /app/services/product_api "$container" python -m alembic -c alembic.ini current)
  case "$revision" in
    0015_claims_company_report_handoff|"0015_claims_company_report_handoff (head)") ;;
    *) echo 'database is not exactly sole revision 0015; STOP' >&2; return 2 ;;
  esac
}

legacy_web_tree_sha256() {
  local root=$1
  local limiter=${2:-bounded}
  "$limiter" python3 - "$root" <<'PY'
from hashlib import sha256
from pathlib import Path
import os
import stat
import sys

root = Path(sys.argv[1])
if root.is_symlink() or not root.is_dir():
    raise SystemExit("legacy Web root invalid; STOP")
digest = sha256()
count = 0
total = 0
observed_index = False
for current_root, directory_names, file_names in os.walk(root, followlinks=False):
    directory_names.sort()
    file_names.sort()
    current = Path(current_root)
    for name in directory_names:
        path = current / name
        if path.is_symlink() or not path.is_dir():
            raise SystemExit("legacy Web tree contains linked/non-directory entry; STOP")
    for name in file_names:
        path = current / name
        metadata = path.stat(follow_symlinks=False)
        if path.is_symlink() or not stat.S_ISREG(metadata.st_mode):
            raise SystemExit("legacy Web tree contains linked/non-file entry; STOP")
        relative = path.relative_to(root).as_posix()
        encoded = relative.encode("utf-8")
        if not encoded or len(encoded) > 4096:
            raise SystemExit("legacy Web path invalid; STOP")
        file_digest = sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                file_digest.update(chunk)
        count += 1
        total += metadata.st_size
        if count > 10000 or total > 256 * 1024 * 1024:
            raise SystemExit("legacy Web tree bounds invalid; STOP")
        observed_index = observed_index or relative == "index.html"
        digest.update(b"F")
        digest.update(len(encoded).to_bytes(4, "big"))
        digest.update(encoded)
        digest.update(metadata.st_size.to_bytes(8, "big"))
        digest.update(file_digest.digest())
if not observed_index or count == 0:
    raise SystemExit("legacy Web index missing; STOP")
print(digest.hexdigest())
PY
}

stop_exact_container() {
  local id=$1
  rollback_bounded docker update --restart=no "$id" >/dev/null
  if test "$(rollback_bounded docker inspect --format '{{.State.Running}}' "$id")" = true; then
    rollback_bounded docker kill --signal=TERM "$id" >/dev/null
  fi
  rollback_bounded docker wait "$id" >/dev/null
  test "$(rollback_bounded docker inspect --format '{{.State.Running}}' "$id")" = false
}

rollback_legacy() (
  set -Eeuo pipefail
  rollback_deadline_epoch=$((EPOCHSECONDS + 3300))
  local project old_image product_id report_id provider_state prior_web_tree_sha256
  project=$(cat "$stage/prior-product-compose-project")
  old_image=$(cat "$stage/prior-product-image-id")
  provider_state=$(cat "$stage/prior-provider-state")
  prior_web_tree_sha256=$(cat "$stage/prior-web-tree-sha256")
  printf '%s\n' "$project" | grep -Eq '^[a-z0-9][a-z0-9_-]*$'
  grep -Eq '^sha256:[0-9a-f]{64}$' "$stage/prior-product-image-id"
  test "$provider_state" = enabled -o "$provider_state" = disabled
  [[ "$prior_web_tree_sha256" =~ ^[0-9a-f]{64}$ ]]

  if path_present "$stage/migration-armed"; then
    test -f "$stage/migration-armed" && test ! -L "$stage/migration-armed"
    for service in company_card_narrative_worker company_report_worker product_api; do
      collect_ids ids rollback_bounded docker ps -aq --filter label=com.docker.compose.project="$project" --filter label=com.docker.compose.service="$service"
      for id in "${ids[@]}"; do
        stop_exact_container "$id"
      done
    done
    test "$(rollback_bounded sha256sum "$recovery_hook" | cut -d' ' -f1)" = "$recovery_hook_sha256"
    test "$(rollback_bounded sha256sum "$backup_artifact" | cut -d' ' -f1)" = "$backup_sha256"
    rollback_bounded "$recovery_hook" restore "$backup_artifact" "$backup_id" "$backup_sha256" 0015_claims_company_report_handoff >/dev/null 2>&1
    rollback_bounded "$recovery_hook" verify-restored "$backup_artifact" "$backup_id" "$backup_sha256" 0015_claims_company_report_handoff >/dev/null 2>&1
  fi

  rollback_bounded install -m 640 "$stage/prior-docker-compose.product.yml" /opt/b2b/docker-compose.product.yml
  test "$(rollback_bounded docker image inspect --format '{{.Id}}' "b2b-product-api:legacy-0015-rollback-$release_sha")" = "$old_image"
  rollback_bounded docker tag "b2b-product-api:legacy-0015-rollback-$release_sha" "b2b-product-api:$prior_release_sha"
  collect_ids narrative_ids rollback_bounded docker ps -aq --filter label=com.docker.compose.project="$project" --filter label=com.docker.compose.service=company_card_narrative_worker
  for id in "${narrative_ids[@]}"; do
    if test "$(rollback_bounded docker inspect --format '{{.State.Running}}' "$id")" = true; then
      stop_exact_container "$id"
    fi
    rollback_bounded docker rm "$id" >/dev/null
  done

  if path_present "$stage/migration-armed"; then
    cd /opt/b2b
    rollback_bounded env PRODUCT_IMAGE_TAG="$prior_release_sha" docker compose -p "$project" -f /opt/b2b/docker-compose.product.yml --env-file .env.product up -d --no-build --force-recreate product_api company_report_worker
    product_id=$(rollback_bounded env PRODUCT_IMAGE_TAG="$prior_release_sha" docker compose -p "$project" -f /opt/b2b/docker-compose.product.yml --env-file .env.product ps -q product_api)
    report_id=$(rollback_bounded env PRODUCT_IMAGE_TAG="$prior_release_sha" docker compose -p "$project" -f /opt/b2b/docker-compose.product.yml --env-file .env.product ps -q company_report_worker)
  else
    product_id=$(cat "$stage/prior-product-id")
    report_id=$(cat "$stage/prior-report-id")
    grep -Eq '^[0-9a-f]{12,64}$' "$stage/prior-product-id"
    grep -Eq '^[0-9a-f]{12,64}$' "$stage/prior-report-id"
    test "$(rollback_bounded docker inspect --format '{{index .Config.Labels "com.docker.compose.project"}}' "$product_id")" = "$project"
    test "$(rollback_bounded docker inspect --format '{{index .Config.Labels "com.docker.compose.service"}}' "$product_id")" = product_api
    test "$(rollback_bounded docker inspect --format '{{index .Config.Labels "com.docker.compose.project"}}' "$report_id")" = "$project"
    test "$(rollback_bounded docker inspect --format '{{index .Config.Labels "com.docker.compose.service"}}' "$report_id")" = company_report_worker
    if path_present "$stage/drain-armed"; then
      test -f "$stage/drain-armed" && test ! -L "$stage/drain-armed"
      stop_exact_container "$product_id"
      stop_exact_container "$report_id"
    else
      test "$(rollback_bounded docker inspect --format '{{.State.Running}}' "$product_id")" = true
      test "$(rollback_bounded docker inspect --format '{{.State.Running}}' "$report_id")" = true
      test "$(rollback_bounded docker inspect --format '{{.HostConfig.RestartPolicy.Name}}' "$product_id")" = unless-stopped
      test "$(rollback_bounded docker inspect --format '{{.HostConfig.RestartPolicy.Name}}' "$report_id")" = unless-stopped
    fi
    for id in "$product_id" "$report_id"; do
      rollback_bounded docker update --restart=unless-stopped "$id" >/dev/null
      if test "$(rollback_bounded docker inspect --format '{{.State.Running}}' "$id")" = false; then
        rollback_bounded docker start "$id" >/dev/null
      fi
    done
  fi

  test -n "$product_id" && test -n "$report_id"
  test "$(rollback_bounded docker inspect --format '{{index .Config.Labels "com.docker.compose.project"}}' "$product_id")" = "$project"
  test "$(rollback_bounded docker inspect --format '{{index .Config.Labels "com.docker.compose.service"}}' "$product_id")" = product_api
  test "$(rollback_bounded docker inspect --format '{{index .Config.Labels "com.docker.compose.project"}}' "$report_id")" = "$project"
  test "$(rollback_bounded docker inspect --format '{{index .Config.Labels "com.docker.compose.service"}}' "$report_id")" = company_report_worker
  test "$(rollback_bounded docker inspect --format '{{.Config.Image}}' "$product_id")" = "b2b-product-api:$prior_release_sha"
  test "$(rollback_bounded docker inspect --format '{{.Config.Image}}' "$report_id")" = "b2b-product-api:$prior_release_sha"
  test "$(rollback_bounded docker inspect --format '{{.Image}}' "$product_id")" = "$old_image"
  test "$(rollback_bounded docker inspect --format '{{.Image}}' "$report_id")" = "$old_image"
  test "$(rollback_bounded docker inspect --format '{{.State.Running}}' "$product_id")" = true
  test "$(rollback_bounded docker inspect --format '{{.State.Running}}' "$report_id")" = true
  test "$(rollback_bounded docker inspect --format '{{.HostConfig.RestartPolicy.Name}}' "$product_id")" = unless-stopped
  test "$(rollback_bounded docker inspect --format '{{.HostConfig.RestartPolicy.Name}}' "$report_id")" = unless-stopped
  test "$(rollback_bounded docker port "$product_id" 8000/tcp)" = 127.0.0.1:8000
  collect_ids global_products rollback_bounded docker ps -q --filter label=com.docker.compose.service=product_api
  collect_ids global_reports rollback_bounded docker ps -q --filter label=com.docker.compose.service=company_report_worker
  collect_ids global_narratives rollback_bounded docker ps -q --filter label=com.docker.compose.service=company_card_narrative_worker
  test "${#global_products[@]}" -eq 1 && test "${global_products[0]}" = "$product_id"
  test "${#global_reports[@]}" -eq 1 && test "${global_reports[0]}" = "$report_id"
  test "${#global_narratives[@]}" -eq 0
  sole_legacy_revision "$product_id"
  test "$(rollback_bounded docker exec "$product_id" python -c "from product_api.settings import get_settings; print('enabled' if get_settings().datanewton_enabled else 'disabled')")" = "$provider_state"
  rollback_bounded curl --connect-timeout 10 --max-time 30 --fail --silent --show-error http://127.0.0.1:8000/health >/dev/null

  if test -e /var/lib/pork/web-ui/v1 || test -L /var/lib/pork/web-ui/v1; then
    test -d /var/lib/pork/web-ui/v1 && test ! -L /var/lib/pork/web-ui/v1
    rollback_bounded python3 "$stage/install_web_ui_release.sh" rollback-uninitialized "$release_sha" /var/lib/pork/web-ui/v1 /var/lib/pork/web-ui/v1
  fi
  test "$(legacy_web_tree_sha256 /opt/b2b/services/web_ui/dist rollback_bounded)" = "$prior_web_tree_sha256"
  rollback_bounded install -m 640 "$stage/prior-nginx.conf" /etc/nginx/sites-available/pork.su.conf
  rollback_bounded nginx -t
  rollback_bounded systemctl reload nginx
  rollback_bounded curl --connect-timeout 10 --max-time 30 --fail --silent --show-error --resolve pork.su:443:127.0.0.1 https://pork.su/ >/dev/null
)

verify_exact_legacy_runtime() {
  local product_id report_id project old_image provider_state prior_web_tree_sha256
  product_id=$(cat "$stage/prior-product-id")
  report_id=$(cat "$stage/prior-report-id")
  project=$(cat "$stage/prior-product-compose-project")
  old_image=$(cat "$stage/prior-product-image-id")
  provider_state=$(cat "$stage/prior-provider-state")
  prior_web_tree_sha256=$(cat "$stage/prior-web-tree-sha256")
  [[ "$prior_web_tree_sha256" =~ ^[0-9a-f]{64}$ ]]
  bounded cmp -s "$stage/prior-docker-compose.product.yml" /opt/b2b/docker-compose.product.yml
  bounded cmp -s "$stage/prior-nginx.conf" /etc/nginx/sites-available/pork.su.conf
  test "$(bounded docker inspect --format '{{index .Config.Labels "com.docker.compose.project"}}' "$product_id")" = "$project"
  test "$(bounded docker inspect --format '{{index .Config.Labels "com.docker.compose.service"}}' "$product_id")" = product_api
  test "$(bounded docker inspect --format '{{index .Config.Labels "com.docker.compose.project"}}' "$report_id")" = "$project"
  test "$(bounded docker inspect --format '{{index .Config.Labels "com.docker.compose.service"}}' "$report_id")" = company_report_worker
  test "$(bounded docker inspect --format '{{.Image}}' "$product_id")" = "$old_image"
  test "$(bounded docker inspect --format '{{.Image}}' "$report_id")" = "$old_image"
  test "$(bounded docker inspect --format '{{.State.Running}}' "$product_id")" = true
  test "$(bounded docker inspect --format '{{.State.Running}}' "$report_id")" = true
  collect_ids products bounded docker ps -q --filter label=com.docker.compose.service=product_api
  collect_ids reports bounded docker ps -q --filter label=com.docker.compose.service=company_report_worker
  collect_ids narratives bounded docker ps -q --filter label=com.docker.compose.service=company_card_narrative_worker
  test "${#products[@]}" -eq 1 && test "${products[0]}" = "$product_id"
  test "${#reports[@]}" -eq 1 && test "${reports[0]}" = "$report_id"
  test "${#narratives[@]}" -eq 0
  test "$(bounded docker port "$product_id" 8000/tcp)" = 127.0.0.1:8000
  test "$(bounded docker exec "$product_id" python -c "from product_api.settings import get_settings; print('enabled' if get_settings().datanewton_enabled else 'disabled')")" = "$provider_state"
  sole_legacy_revision "$product_id"
  test "$(legacy_web_tree_sha256 /opt/b2b/services/web_ui/dist)" = "$prior_web_tree_sha256"
}

finish() {
  local status=$?
  trap - EXIT TERM INT HUP
  if test "$status" -ne 0 && ! path_present "$stage/bootstrap-success" && test "${reconciliation_only:-false}" != true; then
    set +e
    rollback_legacy
    rollback_status=$?
    set -e
    if test "$rollback_status" -eq 0; then
      marker_once rollback-complete terminal_bounded
      disable_recovery_unit
      status=0
    else
      marker_once rollback-failed terminal_bounded
    fi
  elif path_present "$stage/bootstrap-success"; then
    disable_recovery_unit
  fi
  exit "$status"
}
trap finish EXIT
trap 'exit 143' TERM INT HUP

for terminal in bootstrap-success rollback-complete; do
  if path_present "$stage/$terminal"; then
    marker_once "$terminal" terminal_bounded
    disable_recovery_unit
    exit 0
  fi
done

reconciliation_only=false
for nonterminal in bridge-armed bridge-complete drain-armed drain-complete migration-armed product-complete web-armed rollback-failed; do
  if path_present "$stage/$nonterminal"; then
    marker_once "$nonterminal"
    reconciliation_only=true
  fi
done
if test "$reconciliation_only" = true; then
  set +e
  rollback_legacy
  reconciliation_status=$?
  set -e
  if test "$reconciliation_status" -eq 0; then
    marker_once rollback-complete terminal_bounded
    disable_recovery_unit
    exit 0
  fi
  marker_once rollback-failed terminal_bounded
  exit 1
fi

verify_exact_legacy_runtime

# Phase 1: prepare/verify the immutable H2 root, then enter maintenance ingress.
cd "$stage"
bounded sha256sum --strict --ignore-missing --check "checksums-$release_sha.txt"
seed_archive=company-public-h2-seed-bundle-e7478a2fba9aaca17829c3d99e89e8d83d4b3188.tgz
test "$(bounded sha256sum "$seed_archive" | cut -d' ' -f1)" = "$seed_sha256"
seed_extract=$(bounded mktemp -d -p "$stage" .seed-extract.XXXXXXXXXX)
candidate_extract=$(bounded mktemp -d -p "$stage" .candidate-h2.XXXXXXXXXX)
bounded chmod 750 "$seed_extract" "$candidate_extract"
bounded tar -xzf "$seed_archive" --no-same-owner --no-same-permissions --strip-components=1 -C "$seed_extract"
bounded python3 company_public_h2_seed.py verify-bundle "$seed_extract/seed-inventory.json" >/dev/null
bounded tar -xzf "company-public-h2-$release_sha.tgz" --no-same-owner --no-same-permissions --strip-components=1 -C "$candidate_extract"
candidate_digest=$(bounded sha256sum "$candidate_extract/public_h2_asset_manifest.json" | cut -d' ' -f1)
h2_parent=/var/lib/pork/company-public-h2
h2_root="$h2_parent/v1"
ensure_private_directory /var/lib/pork
ensure_private_directory "$h2_parent"
ensure_private_directory "$h2_root"
ensure_private_directory /var/lib/pork/web-ui
ensure_private_directory /var/lib/pork/web-ui/v1
test "$(bounded stat -c '%u:%g:%a' -- "$h2_parent")" = "$EUID:$runner_gid:750"
test "$(bounded stat -c '%u:%g:%a' -- /var/lib/pork/web-ui/v1)" = "$EUID:$runner_gid:750"
if ! path_present "$h2_root/manifest-set.json"; then
  if test -e "$h2_root"; then
    test -d "$h2_root" && test ! -L "$h2_root"
    test -z "$(bounded find "$h2_root" -mindepth 1 -maxdepth 1 -print -quit)"
  fi
  bounded bash seed_company_public_h2_assets.sh "$seed_extract/seed-inventory.json" "$h2_root"
fi
bounded python3 company_public_h2_seed.py verify "$h2_root" "$h2_root" >/dev/null
verify_nginx_tree_access "$h2_root"
bounded python3 - "$candidate_digest" "$h2_root/manifest-set.json" <<'PY'
import json
import sys
candidate_digest, path = sys.argv[1:]
values = json.load(open(path, encoding="utf-8"))["retained_manifest_sha256"]
seed = [
    "97a76daefbb73e1b78935916516fa093f3db5027e09ea44f52df6f63ac18222b",
    "506b92be298a1e81d8550dad08c5ce4b5ece8fa3d163a78d286642ec75b4b060",
    "e48fa51389f5365f9fe445b0c49a0a2224103502a6b742ca1cb9bd705f63a6d6",
]
candidate = [candidate_digest, *seed[:2]]
if values not in (seed, candidate):
    raise SystemExit("unexpected H2 bootstrap state")
PY
marker bridge-armed
bounded install -m 640 product_api_legacy_0015_h2_bootstrap.conf /etc/nginx/sites-available/pork.su.conf
bounded nginx -t
bounded systemctl reload nginx
bounded bash install_company_public_h2_assets.sh "$candidate_extract" "$h2_root" 127.0.0.1:443 https://pork.su "$candidate_extract/public_h2_asset_manifest.json"
verify_nginx_tree_access "$h2_root"
bounded python3 - "$candidate_digest" "$h2_root/manifest-set.json" <<'PY'
import json
import sys
candidate_digest, path = sys.argv[1:]
values = json.load(open(path, encoding="utf-8"))["retained_manifest_sha256"]
expected = [
    candidate_digest,
    "97a76daefbb73e1b78935916516fa093f3db5027e09ea44f52df6f63ac18222b",
    "506b92be298a1e81d8550dad08c5ce4b5ece8fa3d163a78d286642ec75b4b060",
]
if values != expected:
    raise SystemExit("candidate H2 set mismatch")
PY
marker bridge-complete

# Phase 2: quiesce Product first, then drain exactly the sole legacy report worker.
product_id=$(cat "$stage/prior-product-id")
report_id=$(cat "$stage/prior-report-id")
test "$(bounded docker inspect --format '{{.State.Running}}' "$product_id")" = true
test "$(bounded docker inspect --format '{{.State.Running}}' "$report_id")" = true
marker drain-armed
bounded docker update --restart=no "$product_id" >/dev/null
bounded docker kill --signal=TERM "$product_id" >/dev/null
bounded docker wait "$product_id" >/dev/null
test "$(bounded docker inspect --format '{{.State.Running}}' "$product_id")" = false
drain_temporary="$stage/.legacy-worker-drain-result.$$.tmp"
test ! -e "$drain_temporary" && test ! -L "$drain_temporary"
test ! -e "$stage/legacy-worker-drain-result.json" && test ! -L "$stage/legacy-worker-drain-result.json"
bounded python3 "$stage/legacy_0015_worker_drain.py" --container "$report_id" --deadline-seconds "$drain_deadline" --stable-interval-seconds "$stable_interval" > "$drain_temporary"
test -s "$drain_temporary"
bounded python3 - "$drain_temporary" <<'PY'
import json
import re
import sys
value = json.load(open(sys.argv[1], encoding="utf-8"))
if (
    not isinstance(value, dict)
    or value.get("outcome") != "drained"
    or re.fullmatch(r"[0-9a-f]{64}", value.get("database_target_sha256", "")) is None
):
    raise SystemExit("legacy drain result invalid; STOP")
PY
bounded sync -f "$drain_temporary"
bounded mv -T "$drain_temporary" "$stage/legacy-worker-drain-result.json"
bounded sync -f "$stage"
test "$(bounded docker inspect --format '{{.State.Running}}' "$report_id")" = false
marker drain-complete

# Phase 3: bind the fresh frozen recovery point, then and only then migrate/start.
bounded "$recovery_hook" verify-current-frozen "$backup_artifact" "$backup_id" "$backup_sha256" 0015_claims_company_report_handoff >/dev/null 2>&1
bounded docker load --input "product-api-$release_sha.oci.tar" >/dev/null
expected_image=$(bounded python3 -c "import json,re,sys; value=json.load(open(sys.argv[1],encoding='utf-8')); digest=value['images'][sys.argv[2]]['config_digest']; (isinstance(digest,str) and re.fullmatch(r'sha256:[0-9a-f]{64}',digest)) or sys.exit('invalid Product config digest'); print(digest)" "release-manifest-$release_sha.json" "product-api-$release_sha.oci.tar")
candidate_image=$(bounded docker image inspect --format '{{.Id}}' "b2b-product-api:$release_sha")
test "$candidate_image" = "$expected_image"
drained_db_sha=$(bounded python3 -c "import json,re,sys; value=json.load(open(sys.argv[1],encoding='utf-8')); digest=value.get('database_target_sha256'); (isinstance(digest,str) and re.fullmatch(r'[0-9a-f]{64}',digest)) or sys.exit('invalid drained DB digest'); print(digest)" legacy-worker-drain-result.json)
candidate_db_sha=$(bounded docker run --rm --network none --env-file /opt/b2b/.env.product "b2b-product-api:$release_sha" python -c "from hashlib import sha256; from product_api.settings import get_settings; print(sha256(str(get_settings().database_url).encode('utf-8')).hexdigest())")
test "$candidate_db_sha" = "$drained_db_sha"
provider_state=$(cat prior-provider-state)
bounded docker run --rm --network none --env-file /opt/b2b/.env.product --env EXPECTED_PROVIDER_STATE="$provider_state" --env PRODUCT_RELEASE_COMMIT="$release_sha" "b2b-product-api:$release_sha" python -c "import os,sys; from product_api.settings import get_settings; s=get_settings(); provider='enabled' if s.datanewton_enabled else 'disabled'; key_ok=provider != 'enabled' or bool((s.datanewton_api_key or '').strip()); checks=(os.environ.get('PRODUCT_RELEASE_COMMIT') == '$release_sha',provider == os.environ.get('EXPECTED_PROVIDER_STATE'),key_ok,not s.company_card_v2_presentations_enabled,not s.company_card_v2_writer_enabled,s.company_card_v2_rollout_generation == 0,s.company_card_v2_allowlist_inns == [],s.company_card_v2_percentage_basis_points == 0,not s.company_card_v2_arbitration_collection_enabled,s.company_card_v2_arbitration_mask_active_key_id is None,s.company_card_v2_arbitration_mask_keyring_json is None,not s.company_card_v2_narrative_enabled,s.company_card_v2_narrative_kill_switch,s.company_card_v2_narrative_daily_limit == 0,s.company_card_v2_narrative_monthly_limit == 0,s.company_card_v2_narrative_concurrency == 0); all(checks) or sys.exit('pre-migration default-off/provider preservation failed')"
marker migration-armed
bounded docker run --rm --network host --env-file /opt/b2b/.env.product "b2b-product-api:$release_sha" python -m alembic -c /app/alembic.ini upgrade head
bounded install -m 640 docker-compose.product.yml /opt/b2b/docker-compose.product.yml
project=$(cat prior-product-compose-project)
printf '%s\n' "$project" | grep -Eq '^[a-z0-9][a-z0-9_-]*$'
cd /opt/b2b
bounded env PRODUCT_ENV_FILE=/opt/b2b/.env.product PRODUCT_IMAGE_TAG="$release_sha" PRODUCT_RELEASE_COMMIT="$release_sha" docker compose -p "$project" --profile company-card-narrative -f "$stage/docker-compose.product.yml" --env-file .env.product up -d --no-build --force-recreate product_api company_report_worker company_card_narrative_worker
for service in product_api company_report_worker company_card_narrative_worker; do
  id=$(bounded env PRODUCT_ENV_FILE=/opt/b2b/.env.product PRODUCT_IMAGE_TAG="$release_sha" PRODUCT_RELEASE_COMMIT="$release_sha" docker compose -p "$project" --profile company-card-narrative -f "$stage/docker-compose.product.yml" --env-file .env.product ps -q "$service")
  test -n "$id"
  test "$(bounded docker inspect --format '{{index .Config.Labels "com.docker.compose.project"}}' "$id")" = "$project"
  test "$(bounded docker inspect --format '{{index .Config.Labels "com.docker.compose.service"}}' "$id")" = "$service"
  test "$(bounded docker inspect --format '{{.Config.Image}}' "$id")" = "b2b-product-api:$release_sha"
  test "$(bounded docker inspect --format '{{.Image}}' "$id")" = "$candidate_image"
  test "$(bounded docker inspect --format '{{.State.Running}}' "$id")" = true
  case "$service" in
    product_api) candidate_product_id=$id ;;
    company_report_worker) candidate_report_id=$id ;;
    company_card_narrative_worker) candidate_narrative_id=$id ;;
  esac
done
collect_ids candidate_global_products bounded docker ps -q --filter label=com.docker.compose.service=product_api
collect_ids candidate_global_reports bounded docker ps -q --filter label=com.docker.compose.service=company_report_worker
collect_ids candidate_global_narratives bounded docker ps -q --filter label=com.docker.compose.service=company_card_narrative_worker
test "${#candidate_global_products[@]}" -eq 1 && test "${candidate_global_products[0]}" = "$candidate_product_id"
test "${#candidate_global_reports[@]}" -eq 1 && test "${candidate_global_reports[0]}" = "$candidate_report_id"
test "${#candidate_global_narratives[@]}" -eq 1 && test "${candidate_global_narratives[0]}" = "$candidate_narrative_id"
test "$(bounded docker port "$candidate_product_id" 8000/tcp)" = 127.0.0.1:8000
bounded curl --connect-timeout 10 --max-time 30 --fail --silent --show-error http://127.0.0.1:8000/health >/dev/null
marker product-complete

# Phase 4: initialize Web under maintenance, verify runtime, then open ingress.
cd "$stage"
marker web-armed
web_sha=$(bounded sha256sum "web-ui-$release_sha.tgz" | cut -d' ' -f1)
bounded python3 install_web_ui_release.sh "web-ui-$release_sha.tgz" "$release_sha" /var/lib/pork/web-ui/v1 "$web_sha" 127.0.0.1:443 https://pork.su
verify_nginx_tree_access /var/lib/pork/web-ui/v1 true
id=$(bounded env PRODUCT_ENV_FILE=/opt/b2b/.env.product PRODUCT_IMAGE_TAG="$release_sha" PRODUCT_RELEASE_COMMIT="$release_sha" docker compose -p "$project" --profile company-card-narrative -f "$stage/docker-compose.product.yml" --env-file /opt/b2b/.env.product ps -q product_api)
bounded docker exec -e EXPECTED_PROVIDER_STATE="$provider_state" "$id" python -c "import os,sys; from product_api.settings import get_settings; s=get_settings(); provider='enabled' if s.datanewton_enabled else 'disabled'; key_ok=provider != 'enabled' or bool((s.datanewton_api_key or '').strip()); checks=(os.environ.get('PRODUCT_RELEASE_COMMIT') == '$release_sha',provider == os.environ.get('EXPECTED_PROVIDER_STATE'),key_ok,not s.company_card_v2_presentations_enabled,not s.company_card_v2_writer_enabled,s.company_card_v2_rollout_generation == 0,s.company_card_v2_allowlist_inns == [],s.company_card_v2_percentage_basis_points == 0,not s.company_card_v2_arbitration_collection_enabled,s.company_card_v2_arbitration_mask_active_key_id is None,s.company_card_v2_arbitration_mask_keyring_json is None,not s.company_card_v2_narrative_enabled,s.company_card_v2_narrative_kill_switch,s.company_card_v2_narrative_daily_limit == 0,s.company_card_v2_narrative_monthly_limit == 0,s.company_card_v2_narrative_concurrency == 0); all(checks) or sys.exit('bootstrap default-off/provider preservation failed')"
test "$(bounded readlink /var/lib/pork/web-ui/v1/current)" = "releases/$release_sha"
bounded install -m 640 product_api.conf /etc/nginx/sites-available/pork.su.conf
bounded nginx -t
bounded systemctl reload nginx
bounded curl --connect-timeout 10 --max-time 30 --fail --silent --show-error --resolve pork.su:443:127.0.0.1 https://pork.su/company/7707079463 >/dev/null
code=$(bounded curl --connect-timeout 10 --max-time 30 --silent --output /dev/null --write-out '%{http_code}' --resolve pork.su:443:127.0.0.1 https://pork.su/api/internal/whoami)
test "$code" = 401
bounded curl --connect-timeout 10 --max-time 30 --fail --silent --show-error --resolve pork.su:443:127.0.0.1 https://pork.su/ >/dev/null
marker bootstrap-success

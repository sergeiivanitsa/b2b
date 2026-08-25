#!/usr/bin/env bash
# Resolved-root guard and lock only; Python is the single installer path.
set -euo pipefail
source_dir=${1:?source release directory required}
target_root=${2:?stable target root required}
loopback_connect=${3:?loopback IP:port required}
public_origin=${4:?public HTTPS origin required}
product_manifest=${5:?candidate Product manifest required}
approved_root=/var/lib/pork/company-public-h2/v1
[[ "$target_root" == "$approved_root" ]] || { echo 'unexpected stable root' >&2; exit 2; }
[[ -d "$target_root" && ! -L "$target_root" ]] || { echo 'stable root missing or symlinked; seed runbook required' >&2; exit 2; }
[[ "$(realpath -e -- "$target_root")" == "$approved_root" ]] || { echo 'resolved stable root mismatch' >&2; exit 2; }
[[ -d "$target_root/assets" && ! -L "$target_root/assets" ]] || { echo 'stable assets missing or symlinked' >&2; exit 2; }
[[ -d "$target_root/manifests/sha256" && ! -L "$target_root/manifests" && ! -L "$target_root/manifests/sha256" ]] || { echo 'stable manifests missing or symlinked' >&2; exit 2; }
[[ -d "$source_dir/assets" && ! -L "$source_dir" && ! -L "$source_dir/assets" && -f "$source_dir/public_h2_asset_manifest.json" && ! -L "$source_dir/public_h2_asset_manifest.json" ]] || { echo 'invalid H2 release artifact' >&2; exit 2; }
[[ -f "$product_manifest" && ! -L "$product_manifest" ]] || { echo 'candidate Product manifest missing or symlinked' >&2; exit 2; }
exec 9>"$target_root/.install.lock"
flock -x 9
script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)
exec python3 "$script_dir/company_public_h2_release.py" install \
  "$source_dir" "$target_root" "$loopback_connect" "$public_origin" \
  "$product_manifest" "$approved_root"

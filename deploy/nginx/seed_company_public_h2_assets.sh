#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 2 ]]; then
  echo 'usage: seed_company_public_h2_assets.sh INVENTORY APPROVED_ROOT' >&2
  exit 2
fi

inventory=$1
approved_root=$2
[[ "$inventory" = /* && "$approved_root" = /* ]] || {
  echo 'inventory and approved root must be absolute paths' >&2
  exit 2
}
[[ -f "$inventory" && ! -L "$inventory" ]] || {
  echo 'seed inventory missing or symlinked' >&2
  exit 2
}
[[ -d "$approved_root" && ! -L "$approved_root" ]] || {
  echo 'approved seed root must already exist' >&2
  exit 2
}
approved_parent=${approved_root%/*}
[[ "$approved_parent" = /* && "$approved_parent" != / ]] || {
  echo 'approved seed parent must be a narrow absolute directory' >&2
  exit 2
}
[[ -d "$approved_parent" && ! -L "$approved_parent" ]] || {
  echo 'approved seed parent missing or symlinked' >&2
  exit 2
}
[[ "$(realpath -e -- "$approved_parent")" == "$approved_parent" ]] || {
  echo 'resolved seed parent mismatch' >&2
  exit 2
}
[[ "$(stat -c '%u:%g:%a' -- "$approved_parent")" == "$(id -u):$(id -g):750" ]] || {
  echo 'seed parent ownership or permissions invalid' >&2
  exit 2
}
[[ "$(realpath -e -- "$approved_root")" == "$approved_root" ]] || {
  echo 'resolved seed root mismatch' >&2
  exit 2
}
[[ "$(stat -c '%u:%g:%a' -- "$approved_root")" == "$(id -u):$(id -g):750" ]] || {
  echo 'seed root ownership or permissions invalid' >&2
  exit 2
}

# Seed publication replaces the final root inode, so seed and normal release
# installers share the canonical parent inode lock across that replacement.
exec 9<"$approved_parent"
flock -n 9 || { echo 'another seed invocation is in progress' >&2; exit 2; }
[[ -d "$approved_root" && ! -L "$approved_root" ]] || {
  echo 'approved seed root changed while waiting for lock' >&2
  exit 2
}
[[ "$(realpath -e -- "$approved_root")" == "$approved_root" ]] || {
  echo 'resolved seed root changed while waiting for lock' >&2
  exit 2
}
script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)
exec python3 "$script_dir/company_public_h2_seed.py" seed-atomic \
  "$approved_root" "$approved_root" "$inventory"

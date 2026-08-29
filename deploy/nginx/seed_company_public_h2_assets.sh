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

# Lock the already validated directory inode.  A sibling lock pathname could
# be a pre-planted symlink and must never be opened with shell redirection.
exec 9<"$approved_root"
flock -n 9 || { echo 'another seed invocation is in progress' >&2; exit 2; }
script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)
exec python3 "$script_dir/company_public_h2_seed.py" seed \
  "$approved_root" "$approved_root" "$inventory"

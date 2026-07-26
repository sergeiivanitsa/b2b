#!/usr/bin/env sh
# Manual production handoff. Run explicitly on the target host only.
set -eu
TARGET="${1:-/etc/nginx/sites-available/pork.su.conf}"
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPO_ROOT=$(git -C "$SCRIPT_DIR" rev-parse --show-toplevel)
SOURCE="$REPO_ROOT/deploy/nginx/product_api.conf"
git -C "$REPO_ROOT" ls-files --error-unmatch -- deploy/nginx/product_api.conf >/dev/null
git -C "$REPO_ROOT" diff --quiet -- deploy/nginx/product_api.conf || { echo "source has uncommitted changes" >&2; exit 1; }
[ -f "$SOURCE" ] || { echo "tracked nginx source not found" >&2; exit 1; }
TARGET_DIR=$(dirname -- "$TARGET")
stage=$(mktemp "$TARGET_DIR/.pork.su.conf.XXXXXX")
test_conf=$(mktemp "${TMPDIR:-/tmp}/pork.su-nginx.XXXXXX")
backup="${TARGET}.bak.$$"
trap 'rm -f "$stage" "$test_conf"' EXIT
cp "$SOURCE" "$stage"
printf 'events {}\nhttp { include %s; }\n' "$stage" > "$test_conf"
nginx -t -c "$test_conf" || { echo "staged config validation failed" >&2; exit 1; }
[ ! -f "$TARGET" ] || cp "$TARGET" "$backup"
mv -f "$stage" "$TARGET"
if ! nginx -t; then
  [ ! -f "$backup" ] || mv "$backup" "$TARGET"
  nginx -t || true
  exit 1
fi
nginx -s reload
rm -f "$backup"

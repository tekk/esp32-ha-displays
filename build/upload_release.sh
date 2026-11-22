#!/usr/bin/env bash
# (Re)upload large files as GitHub Release assets, driven by data/release_assets.json (written by build/offline.py).
# Requires: gh (authenticated: `gh auth login`), jq. Idempotent: assets already present with the same size are skipped.
# Usage: build/upload_release.sh [--force]
#   ONLY_ASSETS="a.zip b.zip"  limit to these asset names (used by build/update.py)
#   Entries whose source file is not on disk (CI runner without the download cache) are skipped
#   when the asset already exists in the release, otherwise reported as failures.
set -euo pipefail
cd "$(dirname "$0")/.."
FORCE=${1:-}
REPO=$(jq -r .repo data/release_assets.json)
TAG=$(jq -r .tag data/release_assets.json)
STAGE=${STAGE_DIR:-../guition-cache/release-staging}
mkdir -p "$STAGE"

if ! gh release view "$TAG" --repo "$REPO" >/dev/null 2>&1; then
  gh release create "$TAG" --repo "$REPO" --title "Offline files ($TAG)" --latest=false \
    --notes "Offline copies of all large files referenced by the catalog (Guition file server archives, Waveshare demos, repository snapshots).
Mapping asset ↔ original name/URL ↔ sha256: data/release_assets.json in the repository. Files > 1 GB are split into .001/.002… parts – rejoin with: cat name.0* > name"
fi

# existing assets: name -> size
declare -A HAVE
while IFS=$'\t' read -r n s; do [ -n "$n" ] && HAVE["$n"]=$s; done < <(gh api --paginate "repos/$REPO/releases/tags/$TAG" --jq '.assets[] | [.name, .size] | @tsv' 2>/dev/null || true)

upload() { # $1 = staged path
  local name; name=$(basename "$1")
  local size; size=$(stat -L -c %s "$1")
  if [ -z "$FORCE" ] && [ "${HAVE[$name]:-}" = "$size" ]; then echo "skip  $name"; return; fi
  echo "up    $name ($((size/1048576)) MiB)"
  for try in 1 2 3; do gh release upload "$TAG" "$1" --repo "$REPO" --clobber && return; echo "retry $try"; sleep 10; done
  echo "FAILED $name" >&2; return 1
}

FAIL=0
n=$(jq '.assets | length' data/release_assets.json)
for i in $(seq 0 $((n-1))); do
  asset=$(jq -r ".assets[$i].asset" data/release_assets.json)
  src=$(jq -r ".assets[$i].src" data/release_assets.json)
  if [ -n "${ONLY_ASSETS:-}" ] && [[ " $ONLY_ASSETS " != *" $asset "* ]]; then continue; fi
  if [ ! -e "$src" ]; then
    first=$(jq -r "(.assets[$i].parts // [.assets[$i].asset])[0]" data/release_assets.json)
    if [ -n "${HAVE[$first]:-}" ]; then echo "keep  $asset (no local source, already released)"; else echo "MISSING source for $asset: $src" >&2; FAIL=1; fi
    continue
  fi
  if jq -e ".assets[$i].parts" data/release_assets.json >/dev/null; then
    bytes=$(jq -r .offline.split_part_bytes build/config.json)
    src_abs=$(realpath "$src")
    if [ ! -f "$STAGE/$asset.001" ] || [ "$(cat "$STAGE/$asset".0* | wc -c)" != "$(stat -L -c %s "$src_abs")" ]; then
      rm -f "$STAGE/$asset".0*
      split -b "$bytes" -d -a 3 --numeric-suffixes=1 "$src_abs" "$STAGE/$asset."
    fi
    for p in $(jq -r ".assets[$i].parts[]" data/release_assets.json); do upload "$STAGE/$p" || FAIL=1; done
  else
    ln -sfn "$(realpath "$src")" "$STAGE/$asset"
    upload "$STAGE/$asset" || FAIL=1
  fi
done
exit $FAIL

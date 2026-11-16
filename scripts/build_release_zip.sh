#!/usr/bin/env bash
# Build the HACS release archive and check it the way HACS will read it.
#
# Usage: scripts/build_release_zip.sh [VERSION]
#
# Writes the archive named by `filename` in hacs.json to the repository root
# and prints its path. With VERSION, the manifest.json inside the archive
# carries that version instead of the one in the repository.
#
# HACS extracts the archive straight into
# `custom_components/wiener_netze_smart_meter/`
# (`zip_file.extractall(self.content.path.local)`), so the integration's files
# must sit at the archive ROOT: a top-level `wiener_netze_smart_meter/`
# directory would land as
# `custom_components/wiener_netze_smart_meter/wiener_netze_smart_meter/`.
# HACS also asks the release for exactly the asset named `filename` and fails
# the download when it is absent. Neither mistake fails the HACS validation
# action, so this script checks both.
set -euo pipefail

fail() {
  echo "error: $*" >&2
  exit 1
}

root=$(cd "$(dirname "$0")/.." && pwd)
src="$root/custom_components/wiener_netze_smart_meter"

[[ "$(jq -r '.zip_release' "$root/hacs.json")" == "true" ]] || fail "hacs.json: zip_release is not true"
asset=$(jq -r '.filename // empty' "$root/hacs.json")
[[ -n "$asset" ]] || fail "hacs.json: filename is not set"

repo_version=$(jq -r '.version' "$src/manifest.json")
version=${1:-$repo_version}

work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
cp -R "$src/." "$work/"
find "$work" -name __pycache__ -type d -prune -exec rm -rf {} +
find "$work" -name '*.pyc' -delete
if [[ "$version" != "$repo_version" ]]; then
  jq --arg version "$version" '.version = $version' "$src/manifest.json" > "$work/manifest.json"
fi

out="$root/$asset"
rm -f "$out"
(cd "$work" && zip -r -q -X "$out" .)

listing=$(unzip -Z1 "$out")
grep -qx 'manifest.json' <<< "$listing" || fail "manifest.json is not at the archive root"
grep -qx '__init__.py' <<< "$listing" || fail "__init__.py is not at the archive root"
if grep -q '__pycache__\|\.pyc$' <<< "$listing"; then
  fail "the archive contains compiled Python files"
fi
zipped_version=$(unzip -p "$out" manifest.json | jq -r '.version')
[[ "$zipped_version" == "$version" ]] || fail "manifest.json in the archive says $zipped_version, expected $version"

unzip -l "$out" >&2
if [[ -n "${GITHUB_OUTPUT:-}" ]]; then
  echo "path=$out" >> "$GITHUB_OUTPUT"
fi
echo "$out"

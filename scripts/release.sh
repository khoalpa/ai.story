#!/usr/bin/env sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$ROOT"
python3 scripts/sync_version.py
python3 scripts/release_smoke.py
python3 scripts/build_dist.py
python3 scripts/make_clean_release.py
echo
echo "Release build completed successfully."

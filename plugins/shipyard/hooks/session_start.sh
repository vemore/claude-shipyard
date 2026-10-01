#!/bin/sh
# SessionStart wrapper of the shipyard plugin: the only hook that can still speak when python3
# is missing. Shell builtins only past this point (PATH may hold neither python3 nor git).
if ! command -v python3 >/dev/null 2>&1; then
  dir=$PWD
  while [ -n "$dir" ]; do
    if [ -f "$dir/scripts/lib/tooling.conf" ]; then
      echo "WARNING: python3 is not installed: every shipyard hook (commit gates, push and merge"
      echo "guards, pull-request check) is OFF in this session. Install Python 3.9+ and restart."
      exit 0
    fi
    dir=${dir%/*}
  done
  echo "shipyard is enabled here, but this repository has no scripts/lib/tooling.conf — run /shipyard:bootstrap in an empty folder, or ignore this message."
  exit 0
fi
exec python3 "$(dirname "$0")/session_start.py"

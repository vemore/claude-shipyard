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
  # Not a shipyard repository: silent, except in an empty folder (where bootstrap belongs).
  empty=1
  for f in "$PWD"/* "$PWD"/.[!.]* "$PWD"/..?*; do
    if [ -e "$f" ] || [ -L "$f" ]; then empty=0; break; fi
  done
  if [ "$empty" = 1 ]; then
    echo "This folder is empty and shipyard is enabled: run /shipyard:bootstrap <what you want to build> to start a project with its tooling."
  fi
  exit 0
fi
exec python3 "$(dirname "$0")/session_start.py"

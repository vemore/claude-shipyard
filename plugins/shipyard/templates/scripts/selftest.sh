#!/usr/bin/env bash
# scripts/selftest.sh — run every selftest of the repository with one command.
#
# Usage: scripts/selftest.sh
#
# Runs `python3 -m unittest discover -s scripts/selftest -p 'test_*.py'`, then the same command
# with `-s` on each .claude/skills/<skill>/scripts/ folder, one process per folder (two skills
# may each hold a test_x.py; one discover over both would import two modules under one name).
# Adds up the "Ran N tests" lines and prints the total last. A folder without any test_*.py file
# is skipped, and said so; a folder whose test files run no test fails (Python 3.9 would call it
# OK, 3.12 exits 5: the same answer on both). The interpreter is python3, or SELFTEST_PYTHON
# when set. Bytecode is not written (PYTHONDONTWRITEBYTECODE=1 unless set), so a run leaves no
# untracked __pycache__.
#
# Exit: 0 every run green and at least one test ran; 1 a run failed, or no test ran at all;
# 2 usage error.
#
# Guarantees: every folder is run even after a failure, so one run reports everything; the
# script finds the repository from its own location (<root>/scripts/selftest.sh), so it works
# from any directory and in any worktree; bash 3.2 (macOS) compatible.
# Does not cover: the gates of the stack (scripts/check.sh), evals (evals/selftest.sh, when the
# project has them, is its own CI step).
#
# Why: `python3 -m unittest discover -s .claude/skills` does not enter a folder without
# __init__.py: Python 3.9 answers "Ran 0 tests, OK" and 3.12 exits 5. A selftest that runs
# nothing passes for green, which is worse than no selftest; this script starts from each
# scripts folder and refuses a total of zero.
set -uo pipefail

usage() { sed -n '2,/^set /{/^#/s/^# \{0,1\}//p;}' "$0"; }
case "${1:-}" in
  -h|--help) usage; exit 0 ;;
  "") ;;
  *) printf 'selftest.sh: unexpected argument: %s (see --help)\n' "$1" >&2; exit 2 ;;
esac

root=$(cd "$(dirname "$0")/.." && pwd -P) || exit 1
cd "$root" || exit 1
py=${SELFTEST_PYTHON:-python3}
command -v "$py" >/dev/null 2>&1 || { printf 'selftest.sh: %s not found\n' "$py" >&2; exit 1; }
export PYTHONDONTWRITEBYTECODE=${PYTHONDONTWRITEBYTECODE:-1}

log=$(mktemp "${TMPDIR:-/tmp}/selftest.XXXXXX") || exit 1
trap 'rm -f "$log"' EXIT

total=0
runs=0
failed=""

run_dir() {   # run_dir <folder, relative to the root>
  local dir=$1 rc n
  set -- "$dir"/test_*.py
  if [ ! -e "$1" ]; then
    printf 'skip %s: no test_*.py\n' "$dir"
    return 0
  fi
  printf '== %s\n' "$dir"
  "$py" -m unittest discover -s "$dir" -p 'test_*.py' 2>&1 | tee "$log"
  rc=${PIPESTATUS[0]}
  n=$(sed -n 's/^Ran \([0-9][0-9]*\) tests\{0,1\} in .*/\1/p' "$log" | tail -n 1)
  total=$((total + ${n:-0}))
  runs=$((runs + 1))
  if [ "${n:-0}" -eq 0 ]; then
    printf 'selftest.sh: %s holds test_*.py files but ran no test\n' "$dir" >&2
    failed="$failed $dir"
  elif [ "$rc" -ne 0 ]; then
    failed="$failed $dir"
  fi
}

if [ -d scripts/selftest ]; then
  run_dir scripts/selftest
else
  printf 'skip scripts/selftest: no such folder\n'
fi
for dir in .claude/skills/*/scripts; do
  [ -d "$dir" ] || continue
  run_dir "$dir"
done

if [ -n "$failed" ]; then
  printf 'selftest.sh: FAILED in%s (%s tests ran in %s folder(s))\n' "$failed" "$total" "$runs" >&2
  exit 1
fi
if [ "$total" -eq 0 ]; then
  printf 'selftest.sh: FAILED: 0 tests ran (%s folder(s)); %s\n' "$runs" \
    "a selftest that runs nothing is not green" >&2
  exit 1
fi
printf 'selftest.sh: OK, %s tests in %s folder(s)\n' "$total" "$runs"
exit 0

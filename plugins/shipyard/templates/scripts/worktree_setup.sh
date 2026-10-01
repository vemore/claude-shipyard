#!/usr/bin/env bash
# scripts/worktree_setup.sh — make any worktree usable: dependencies and code generation.
#
# Usage:
#   scripts/worktree_setup.sh [DIR] [--no-<component>]... [--deploy]
#     DIR              the worktree to set up (default: the current directory)
#     --no-<component> skip one component of COMPONENTS (scripts/lib/tooling.conf); an unknown
#                      component is an error, so a typo never skips an installation
#     --deploy         also symlink DEPLOY_ENV_FILE from the main checkout (deploy worktree only)
#
# Steps: resolve the worktree and the main checkout (the parent of --git-common-dir), read the
# worktree's own scripts/lib/tooling.conf; write <tree>/<SETUP_MARKER> ("pid <pid> started
# <UTC time> branch <branch>") before anything slow; with --deploy, link the deploy file; run
# `scripts/check.sh setup <component>` for each component not excluded; remove the marker; print
# `ready: <tree> (<branch>)` as the last line.
#
# Exit: 0 ready; 2 usage error, DIR outside a git repository, --deploy without a deploy target,
# an incomplete tooling.conf or a missing scripts/check.sh (all checked before the marker exists);
# any other failure exits non-zero and LEAVES THE MARKER on purpose: a half-built worktree is
# exactly the one the cleanup must not delete. To remove a stale marker, check that no setup is
# running (the pid in the file), then by hand: rm <tree>/<SETUP_MARKER>
#
# Guarantees: argument errors are reported before anything is written; the marker exists for the
# whole installation, so scripts/cleanup_local.py keeps the worktree and its branch meanwhile;
# the deploy file is linked, never copied (a rotated secret is seen everywhere, and no copy
# survives in a forgotten worktree), and only with --deploy (an implementing agent does not
# deploy, so its worktree does not reach the target); idempotent (a rerun reinstalls from the
# lock and prints `ready:` again).
# Does not cover: git configuration (core.hooksPath is set once per clone, by hand), anything
# outside the worktree, the installation commands themselves (scripts/check.sh setup owns them).
#
# Why: a fresh worktree has no dependencies and no generated code, so its first commit would be
# refused by a gate for a reason unrelated to the change. The marker exists because a cleanup run
# from another session once deleted a worktree and its branch while code generation was running:
# everything the setup writes is ignored by git, so the tree looked clean, and the branch had no
# commit yet — the two signs of an abandoned worktree. A rule nobody can check protects nothing;
# a marker the cleanup reads does.
set -euo pipefail

usage() { sed -n '2,/^set /{/^#/s/^# \{0,1\}//p;}' "$0"; }
die() { printf 'worktree_setup.sh: %s\n' "$1" >&2; exit "${2:-2}"; }

dir=""
deploy=0
skip=" "
for arg in "$@"; do
  case $arg in
    -h|--help) usage; exit 0 ;;
    --deploy) deploy=1 ;;
    --no-?*) skip="$skip${arg#--no-} " ;;
    -*) die "unknown option: $arg (see --help)" ;;
    *) [ -z "$dir" ] || die "only one DIR is accepted (got '$dir' and '$arg')"; dir=$arg ;;
  esac
done

tree=$(git -C "${dir:-.}" rev-parse --show-toplevel 2>/dev/null) \
  || die "not inside a git repository: ${dir:-.}"
common=$(git -C "$tree" rev-parse --path-format=absolute --git-common-dir) \
  || die "cannot find the main checkout of $tree"
main=$(dirname "$common")

conf="$tree/scripts/lib/tooling.conf"
[ -f "$conf" ] || die "missing scripts/lib/tooling.conf in $tree"
# shellcheck disable=SC1090
. "$conf"
for key in SETUP_MARKER COMPONENTS DEPLOY_ENV_FILE; do
  eval "[ -n \"\${$key+set}\" ]" || die "missing key $key in scripts/lib/tooling.conf"
done
[ -n "$SETUP_MARKER" ] || die "SETUP_MARKER is empty in scripts/lib/tooling.conf"

# Validate every argument before writing anything.
for comp in $skip; do
  case " $COMPONENTS " in
    *" $comp "*) ;;
    *) die "--no-$comp: '$comp' is not a component (COMPONENTS: $COMPONENTS)" ;;
  esac
done
if [ "$deploy" -eq 1 ] && [ -z "$DEPLOY_ENV_FILE" ]; then
  die "this project has no deploy target (DEPLOY_ENV_FILE is empty)"
fi
to_setup=""
for comp in $COMPONENTS; do
  case "$skip" in *" $comp "*) ;; *) to_setup="$to_setup $comp" ;; esac
done
if [ -n "$to_setup" ] && [ ! -x "$tree/scripts/check.sh" ]; then
  die "$tree/scripts/check.sh is missing or not executable (it owns each component's setup)"
fi

branch=$(git -C "$tree" symbolic-ref --quiet --short HEAD 2>/dev/null || echo detached)
marker="$tree/$SETUP_MARKER"

# 1. The marker, before anything slow.
printf 'pid %s started %s branch %s\n' "$$" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$branch" > "$marker"

# 2. The deploy file: linked from the main checkout, only on request.
if [ "$deploy" -eq 1 ]; then
  src="$main/$DEPLOY_ENV_FILE"
  dst="$tree/$DEPLOY_ENV_FILE"
  if [ "$(cd "$tree" && pwd -P)" = "$(cd "$main" && pwd -P)" ]; then
    echo "deploy: $DEPLOY_ENV_FILE is used in place (this is the main checkout)"
  elif [ -e "$src" ]; then
    mkdir -p "$(dirname "$dst")"
    ln -sfn "$src" "$dst"
    echo "deploy: linked $DEPLOY_ENV_FILE from the main checkout"
  else
    echo "warning: $src does not exist; no deploy file linked (create it in the main checkout)" >&2
  fi
fi

# 3. Each component, through the single definition of its installation.
cd "$tree"
for comp in $COMPONENTS; do
  case "$skip" in
    *" $comp "*) echo "skipped: $comp (--no-$comp)"; continue ;;
  esac
  echo "setup: $comp"
  rc=0
  "$tree/scripts/check.sh" setup "$comp" || rc=$?
  if [ "$rc" -ne 0 ]; then
    printf 'worktree_setup.sh: setup of %s failed (exit %s); %s is left in place on purpose.\n' \
      "$comp" "$rc" "$marker" >&2
    printf 'Fix the cause and rerun, or remove the marker by hand once nothing runs: rm %s\n' \
      "$marker" >&2
    exit "$rc"
  fi
done

# 4. Done: remove the marker, last line is the contract.
rm -f "$marker"
echo "ready: $tree ($branch)"

---
name: sync-tooling
description: "Bring the project's vendored copies of the shipyard scripts up to the installed plugin version — check them with bin/vendor.py, explain what is outdated, missing or edited by hand, ask once whether local edits go upstream or are dropped with --force, re-vendor in a fresh worktree, run the selftests and gates, open the pull request and merge it as the project's autonomy allows. Use when the session-start message says the vendored tooling is behind, or after a plugin update. Triggers: \"sync tooling\", \"vendored tooling is behind\", \"vendor.py\", \"VENDORED.json\", \"mets à jour l'outillage\", \"synchronise les scripts\"."
---

# sync-tooling

The scripts that the CI and people run without Claude — `scripts/wip.py`, `scripts/pr_size.py`,
`scripts/owners.py`, `scripts/lane_paths.py`, `scripts/cleanup_local.py`,
`scripts/worktree_setup.sh`, `scripts/selftest.sh`, their selftests, `.githooks/pre-commit`… —
are **copies** of the plugin's templates, identical to the version recorded in
`scripts/lib/VENDORED.json` (the version, and a sha256 per file). A CI runner has no plugin,
so the copies live in the repository; the plugin updates itself, the copies move only through
this skill, as one pull request.

## Read the project's settings

`scripts/lib/tooling.conf`: `DEFAULT_BRANCH` (written `<default>` below), `WORKTREE_PREFIX`,
`AUTONOMY`, `TEAM_MODE`, `SIZE_THRESHOLD`, `LANE_C_RE`, `DEPLOY_PATHS_RE`. No `tooling.conf`: the repository is not set up for
the plugin — say so and stop. `${CLAUDE_PLUGIN_ROOT}` is the plugin's directory — two levels
above this skill's base directory if your shell does not expand it. `ship-parallel` is
`/shipyard:ship-parallel`, from the same plugin.

## The one rule you cannot break

A vendored copy is **never edited in place, and never moves backwards**. An edit to a copy is
drift, not customisation: the next sync either refuses to touch it or, with `--force`, erases
it without a sound — a fix that matters goes to the plugin, where every project gets it. And a
plugin older than `VENDORED.json` (a teammate synced from a newer one) would put older scripts
over newer ones: update the plugin (`/plugin`, then a new session) instead of syncing.

## 1. Check

1. Work from the main checkout, on `<default>`, current:
   `git fetch --prune origin && git merge --ff-only origin/<default>`.
2. `python3 "${CLAUDE_PLUGIN_ROOT}/bin/vendor.py" --check .`

   | Line | Means | Then |
   |---|---|---|
   | `ok` | the copies match the plugin's version (exit 0) | nothing to do: say so and stop |
   | `outdated <from> -> <to>` | `VENDORED.json` records `<from>`, the plugin is `<to>` | sync (§3). `<to>` older than `<from>`: stop — the rule above |
   | `missing <path>` | a vendored file is absent: new in this version, or deleted | sync writes it |
   | `modified <path>` | its content differs from the recorded sha256: edited here | §2 first |

   Exit 1 means something to sync; exit 2 is a usage or configuration error — report its
   message and stop.
3. The target version is `<to>`, or, with no `outdated` line,
   `python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["version"])' "${CLAUDE_PLUGIN_ROOT}/.claude-plugin/plugin.json"`.
4. **Read the changelog** from `<from>` to `<to>`: the plugin's `CHANGELOG.md`
   (`${CLAUDE_PLUGIN_ROOT}/CHANGELOG.md` when the plugin ships one, otherwise in the plugin's
   repository — `/plugin` shows its marketplace). Every version that changes a vendored
   template says so. Note what the project must do besides copying: a new `tooling.conf` key, a
   renamed flag, a wiki page that describes the old behaviour.

## 2. Files modified by hand

Only when §1 printed `modified`. For each such file, the local edit is
`git diff "$(git log -1 --format=%h -- scripts/lib/VENDORED.json)" -- <path>` (the last sync
recorded the file as the template). Explain to the user, file by file, what the edit does,
then ask **once** — one `AskUserQuestion`, one question for all files, its "Other" for a
per-file answer:

- **Upstream it** — the edit is a fix every project should have. Propose it to the plugin,
  with that diff, as an issue or pull request in the plugin's repository (outside this one:
  on the user's go), and write a `wip/todo_nr/` entry (`Area: tooling`) that tracks it. The
  file stays as it is: §3 runs without `--force`, and the session-start warning stays until a
  plugin version carries the fix — then `--force` replaces the local copy with the identical
  upstream one. If `vendor.py` refuses to sync anything while a file is modified, stop after
  the entry: the sync waits for that version.
- **Drop it** — the edit was a workaround, or is already upstream: §3 runs with `--force`,
  which overwrites it with the plugin's version. The edit survives in git history; if it fixed
  something real, write the `wip/` entry first.

Why ask: either default loses something without a sound — the fix (drop) or the update (keep).

## 3. Sync in a fresh worktree

1. `git fetch --prune origin && git worktree add --no-track -b chore/shipyard-sync-<to> <WORKTREE_PREFIX>shipyard-sync-<to> origin/<default>`,
   then `scripts/worktree_setup.sh <that dir>`. Every command below runs in that worktree.
2. `python3 "${CLAUDE_PLUGIN_ROOT}/bin/vendor.py" .` — with `--force` only after §2's "drop".
   Then `git status --short`: only vendored paths and `scripts/lib/VENDORED.json` may have
   changed. `vendor.py` never touches `tooling.conf`, `scripts/check.sh` or any other file.
3. Do what the changelog asked, in this same pull request: a new `tooling.conf` key goes in
   with its comment line above it and is cited in `.llmwiki/Project.md`; a wiki page the new
   version makes false is corrected, with its `Updated:` date and its `INDEX.md` row.
4. `scripts/selftest.sh`, `scripts/check.sh all`, `python3 scripts/wiki_lint.py` and
   `python3 scripts/wip.py check` — what the CI's tooling job and the component jobs run. A
   vendored selftest that fails here is a project value the new version reads differently, or
   a plugin bug: fix the project side (`tooling.conf`, a wiki page), never the vendored copy.
   After three attempts on the same failure, stop: classify it (`TEST_ISSUE`, `IMPL_ISSUE`,
   `DOC_ISSUE`, `UNCLEAR`), report it for the plugin, and leave the pull request unmerged.
5. `git add -A`, `git commit -m "chore: sync shipyard tooling to <to>"`,
   `git push -u origin chore/shipyard-sync-<to>`,
   `gh pr create --base <default> --title "chore: sync shipyard tooling to <to>" --body "<from> -> <to>; the files changed; what the changelog asked and what was done; the decision on modified files"`,
   then `gh pr checks <n> --watch` until every check is green or skipped.

## 4. Merge

Through `ship-parallel` §3, as `AUTONOMY` allows: `pr` — stop at a green pull request, the
user merges; `merge` or `merge-deploy` — update, watch, and
`gh pr merge <n> --squash --match-head-commit <sha>`.

- **Lane A.** The code was reviewed and tested in the plugin's repository, and its selftests
  ran here: `pr_size.py` counting vendored lines over `SIZE_THRESHOLD` does not make it lane
  B — say so in the report. A path matching `LANE_C_RE` still makes it lane C.
- **Team projects:** `scripts/` and `.githooks/` belong to the tooling owners; if you are not
  one of them, the pull request waits for their approval (`ship-parallel` §3b).
- **Deploy:** only if `DEPLOY_PATHS_RE` matches what the squash commit changed
  (`ship-parallel` §4) — it rarely does.

After the merge, in the main checkout: `git fetch --prune origin && git merge --ff-only
origin/<default>`, then `python3 "${CLAUDE_PLUGIN_ROOT}/bin/vendor.py" --check .` prints `ok` —
the session-start warning goes away at the next session — and
`python3 scripts/cleanup_local.py --apply` removes the worktree.

## 5. Report

`<from>` → `<to>`, the files written, what the changelog asked and what was done, the decision
on modified files (and the upstream proposal, if any), the pull request URL and its state, and
the last `--check` output.

## When NOT to use this skill

- To change what a vendored script does: that change is made in the plugin's repository; a
  new plugin version and this skill bring it here.
- The plugin is older than the project's copies: update the plugin first (`/plugin`).
- A project not set up for the plugin (no `scripts/lib/tooling.conf`): `/shipyard:bootstrap`
  starts new projects only.

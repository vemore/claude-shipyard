# Changelog

All notable changes to the `shipyard` plugin are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the plugin follows
[Semantic Versioning](https://semver.org/). A change that modifies a vendored template is at
least a minor version, and its entry says so ("run `/shipyard:sync-tooling`").

Each version is also a git tag `v<version>`, and `plugins/shipyard/.claude-plugin/plugin.json`
carries the same number: an update only reaches users when that field changes.

## [Unreleased]

## [0.1.0] - 2026-10-01

First release.

### Added

- **Marketplace** `claude-shipyard` with one plugin, `shipyard`
  (`/plugin install shipyard@claude-shipyard`).
- **Skills**
  - `/shipyard:bootstrap`: sets up a new project in an empty folder from one questionnaire and
    one go-ahead: GitHub repository, `CLAUDE.md`, LLM wiki (`.llmwiki/`), one-file-per-entry
    backlog (`wip/`), CI scoped by component, branch protection, and the vendored tooling.
  - `/shipyard:join`: lets a team member declare the areas of code they own
    (`.github/CODEOWNERS`, `.llmwiki/Team.md`) through a pull request.
  - `/shipyard:ship-parallel`: implements a set of backlog entries in parallel, one agent and one
    git worktree per theme, then reviews, merges (squash) and deploys each green pull request in
    the lane its risk picked.
  - `/shipyard:wip-refine`: sorts the backlog against the code and proposes what to promote.
  - `/shipyard:sync-tooling`: brings the vendored copies of a project up to the plugin version
    after `/plugin update`.
- **Agents** `shipyard:implementer-simple` (Sonnet, low effort), `shipyard:implementer-complex`
  and `shipyard:reviewer` (Sonnet, high effort), each in its own worktree.
- **Guard hooks**, loaded from the plugin: refusal of force-push, push to the default branch,
  stacked pull requests, non-squash and `--admin` merges, secrets in a commit (by path and by
  content), a commit on the default branch or on a stale branch, and red commit gates; a report
  after each edit; a check that a finished branch has a green pull request; a start-of-session
  briefing (branch, worktrees, vendored version, code ownership). Inert in a repository without
  `scripts/lib/tooling.conf`. See `docs/hooks.md`.
- **Vendored scripts** (`plugins/shipyard/templates/`), copied into each project by
  `bin/vendor.py` with their selftests and a `scripts/lib/VENDORED.json` of checksums:
  `ci_scope.py`, `cleanup_local.py`, `pr_size.py`, `wiki_lint.py`, `wip.py`, `lane_paths.py`,
  `owners.py`, `precommit.py`, `worktree_setup.sh`, `selftest.sh`, and `.githooks/pre-commit`.
  See `docs/scripts.md`.
- **Team mode**: `TEAM_MODE=team` adds code owners, a session-start check that the person is an
  owner, and owner approval before merging a pull request that touches someone else's area.
- **Configuration keys** `TEAM_MODE`, `AUTONOMY`, `RELEASE_MODE` and `COMPONENT_<ID>_RE` in
  `scripts/lib/tooling.conf`.
- Plugin contract (`docs/contrat-plugin.md`), maintainer documentation of the hooks and scripts,
  CI (tests on Linux and macOS, Python 3.9 and 3.12), Dependabot for pinned actions.

[Unreleased]: https://github.com/vemore/claude-shipyard/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/vemore/claude-shipyard/releases/tag/v0.1.0

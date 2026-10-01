---
name: join
description: "Join a team project as a code owner — identify your GitHub login, ask once which components and paths you will be responsible for, add you to .github/CODEOWNERS and .llmwiki/Team.md in a fresh worktree, and open the pull request, which waits for the maintainers' approval. Use when the session-start message says you are not a code owner yet, when someone starts on a team repository, or when a member takes on another area. Triggers: \"join the team\", \"add me to CODEOWNERS\", \"make me a code owner\", \"I will own the api\", \"shipyard join\", \"rejoindre l'équipe\", \"ajoute-moi aux owners\", \"je m'occupe du front\", \"je suis responsable de\"."
---

# join

In a team project, `.github/CODEOWNERS` says who answers for which part of the code: GitHub
asks them to review any pull request that touches their part, and `ship-parallel` merges such
a pull request only once they approved it (`ship-parallel` §3b). This skill adds you to that
map and to `.llmwiki/Team.md` through **one pull request**, which the maintainers approve. It
never merges past them.

## Read the project's settings

- `scripts/lib/tooling.conf`: `TEAM_MODE`, `DEFAULT_BRANCH` (written `<default>` below),
  `WORKTREE_PREFIX`, `AUTONOMY`, `COMPONENTS` and, for each component, `COMPONENT_<ID>_RE`
  (`<ID>` is the id in capitals, `-` turned into `_`).
- `.llmwiki/Project.md` § Components (each component's directories) and `.llmwiki/Team.md`.

No `tooling.conf`: the repository is not set up for the plugin — say so and stop.

**`TEAM_MODE` is `solo` or absent: stop here.** Tell the user, in their language: "join is for
team projects. This one is set up solo (`TEAM_MODE=solo` in `scripts/lib/tooling.conf`):
nobody owns a part of it, and no pull request waits for an owner's approval. Moving it to team
mode is a decision for its maintainers, not something this skill does."

## The one rule you cannot break

In CODEOWNERS the **last** matching pattern wins. A line added below an existing one, for the
same path or a wider one, silently takes those files away from their owners: nothing fails,
GitHub just stops asking them. **Joining adds you; it removes nobody.** Add your login to the
existing line of a pattern someone already owns; write a new line only for a pattern nobody
owns, and place it above every narrower pattern it contains. §4.4 proves it with a before and
after of every file's owners.

## 1. Who you are

1. `gh api user --jq .login` — this is `<login>`. If `gh` is not signed in, the user runs
   `! gh auth login` and you start again.
2. Work from the main checkout, on `<default>`, current:
   `git fetch --prune origin && git merge --ff-only origin/<default>`.
3. `python3 scripts/owners.py --who <login> </dev/null`:
   - exit 0: it prints what you already own — show it in §3's question;
   - exit 1: you own nothing yet;
   - exit 2: there is no CODEOWNERS file (`.github/CODEOWNERS`, `CODEOWNERS`, `docs/CODEOWNERS`
     — GitHub's order). If `Team.md` lists members, the file was lost: stop and tell the user,
     restoring it is the maintainers' call. If it lists nobody, you are the first member: §4
     creates `.github/CODEOWNERS`, and you also own the tooling paths (`/.claude/`,
     `/scripts/`, `/.github/`, `/CLAUDE.md`) until the team decides otherwise. Never give
     `wip/` or `.llmwiki/` an owner: almost every pull request touches them.

## 2. What there is to own

Read CODEOWNERS (the first that exists, in the order above — edit that one) and
`.llmwiki/Team.md`. Then list the candidates:

- each component of `COMPONENTS`: its directories from `Project.md` § Components, checked
  against `COMPONENT_<ID>_RE`, and its current owners —
  `git ls-files -- <dir> | python3 scripts/owners.py | cut -f2 | sort -u`;
- each CODEOWNERS pattern that no component covers (the tooling paths, docs, CI…), with its
  owners.

## 3. Ask once

**One** `AskUserQuestion` call:

- the areas, `multiSelect: true`: one option per candidate — label the component id or the
  pattern, description its paths, its current owners, and "you already own this" where §1.3
  says so. A question holds at most four options: spread the candidates over up to three
  questions of the same call, components first, the tooling paths grouped into one option.
  The automatic "Other" takes free text: paths or globs;
- last, header "Login": "Join as @<login>, the account `gh` is signed in with?" — "Yes" /
  "No — I will switch accounts first (`gh auth switch`)".

"No", or nothing ticked: stop. Everything ticked already yours: say so and stop.

## 4. Write it in a fresh worktree

1. `git fetch --prune origin && git worktree add --no-track -b docs/join-<login> <WORKTREE_PREFIX>join-<login> origin/<default>`
   (`<login>` in lower case in both names), then `scripts/worktree_setup.sh <that dir>`:
   `.github/CODEOWNERS` is not documentation, so the commit gates run for every component.
   Every command below runs in that worktree.
2. Before you edit: `before=$(mktemp) && git ls-files | python3 scripts/owners.py > "$before"`
   (no CODEOWNERS yet: it stays empty, and §4.4's comparison has nothing to protect).
3. Turn each choice into CODEOWNERS patterns: a component becomes `/<dir>/` for each of its
   directories, plus any single file its `COMPONENT_<ID>_RE` names outside them; free text is
   taken as written, anchored with a leading `/` when it means "from the root". CODEOWNERS
   takes gitignore-style patterns without `!` or `[ ]`.
4. Edit CODEOWNERS. A pattern already present: append ` @<login>` to its line. A new pattern:
   a new line, above every narrower pattern it contains and below the wider ones. Keep the
   header comment (the file is maintained by `/shipyard:join` and read by
   `scripts/owners.py`); write it if you create the file. Then
   `after=$(mktemp) && git ls-files | python3 scripts/owners.py > "$after" && diff "$before" "$after"`:
   every changed line must **gain** `@<login>` and lose nobody. A line that lost an owner is a
   misplaced pattern — fix the placement, never accept the diff.
5. `.llmwiki/Team.md`: your row — login, areas, since `<today>` — added, or extended if you
   are already listed, in the page's own format. Its `> Updated:` line becomes `<today>`, the
   same date goes on Team's row in `.llmwiki/INDEX.md` (the wiki lint compares them), and
   `Decisions & History` gets one line:
   `- **@<login> joins (<today>).** Owns <patterns>.`
   If `Team.md` does not exist, write it with the header every other page of `.llmwiki/` has,
   and add its row to `INDEX.md`. Then `python3 scripts/wiki_lint.py` exits 0.
6. `git add .github/CODEOWNERS .llmwiki/Team.md .llmwiki/INDEX.md` (or the CODEOWNERS path
   you edited), `git commit -m "docs: join as @<login>"`,
   `git push -u origin docs/join-<login>`, then
   `gh pr create --base <default> --title "docs: join as @<login>" --body "<the areas and their patterns, what the owners diff showed, why>"`.
   `gh pr checks <n> --watch` until every check is green or skipped; after three failed fixes
   of the same check, stop and report it.

## 5. The approval

Who must approve: `printf '%s\n' .github/CODEOWNERS | python3 scripts/owners.py` on the main
checkout (or the CODEOWNERS path you edited) — the owners of the ownership map. GitHub has
already asked them for a review.

- **You are not among them**: the pull request waits for one of them to approve it. Do not
  merge it yourself, even if GitHub would let you: an ownership map its new member approves
  alone is no map. Tell the user who will be asked. Work can start meanwhile: pull requests
  simply wait for the owners of what they touch, and the session-start message keeps saying
  @<login> is not an owner until this one merges.
- **You are among them** (you already own `/.github/`), or the file is new and has no other
  owner: it is your own area — it merges through `ship-parallel` §3 as `AUTONOMY` allows
  (lane A, nothing to deploy; under `AUTONOMY=pr` the user merges it).

## 6. Report

The pull request URL and its check state, the patterns you will own, who must approve, and
what the owners diff showed. The worktree stays until the merge;
`python3 scripts/cleanup_local.py --apply` removes it afterwards.

## When NOT to use this skill

- A solo project (§ Read the project's settings).
- Removing someone, or handing an area from one owner to another: a team decision, made by a
  pull request the maintainers write and approve, recorded in `Team.md` § Decisions & History.
- Leaving an area: the same kind of pull request, by you; check that no pattern is left
  without an owner unless the team means it.

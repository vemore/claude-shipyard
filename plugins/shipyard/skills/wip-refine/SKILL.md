---
name: wip-refine
description: "Refine the wip/ backlog — check every open entry against the code, sort it into already fixed, obsolete, merge, needs detail, ready or promote, rank what is ready by cost of delay, propose what moves from wip/todo_nr/ to wip/todo/ (to their owners in a team project), and run the periodic pruning pass; the user decides, one pull request applies it. Use after a release or milestone, when wip/todo_nr/ passes its threshold, or when the user asks what to work on next. Triggers: \"refinement\", \"grooming\", \"backlog\", \"what's next\", \"promote to todo\", \"pruning pass\", \"fais le tri dans wip\", \"trier le backlog\", \"qu'est-ce qui passe en todo\", \"élagage\"."
---

# wip-refine

The move of an entry from `wip/todo_nr/` to `wip/todo/` is the **commitment point**: before it,
entries are options — cheap to write, cheap to drop; after it, they are the release in
progress. This skill prepares that decision and proposes it. **The user decides.** It
implements nothing.

## Read the project's settings

Read `scripts/lib/tooling.conf` once, then each value at the step that uses it — never copy
one into a file: `DEFAULT_BRANCH` (written `<default>` below), `WORKTREE_PREFIX`,
`REFINE_THRESHOLD`, `STALE_DAYS`, `CROWDED_THEME`, `WIP_LIMIT`, `PRUNE_EVERY_MERGES`,
`CLAUDE_MD_BUDGET`, `WIKI_PAGE_BUDGET`, `TOOLING_LEVEL`, `TEAM_MODE`, `RELEASE_MODE`,
`AUTONOMY`. `.llmwiki/Project.md` § Delivery names the release or milestone `wip/todo/` holds.
No `tooling.conf`: the repository is not set up for the plugin — say so and stop. A key an
older project lacks: `TEAM_MODE` is `solo`; `RELEASE_MODE` is what `Project.md` says, else
`planned` if `.claude/skills/release/` exists, else `continuous`.

| Setting | What changes below |
|---|---|
| `RELEASE_MODE=planned` | `wip/todo/` is the release in progress; the pruning pass (§8) runs before each release |
| `RELEASE_MODE=continuous` | `wip/todo/` is the milestone in progress; §8 runs every `PRUNE_EVERY_MERGES` merges |
| `TEAM_MODE=team` | decisions on entries outside your areas go to their owners (§6, §7.5) |
| `TOOLING_LEVEL=complet` | §8 adds metrics and evals |
| `AUTONOMY` | how §7's pull request merges (`ship-parallel` §3) |

`ship-parallel` is `/shipyard:ship-parallel`, from the same plugin.

**When:** after each release or milestone, when `wip/todo_nr/` passes `REFINE_THRESHOLD`
entries, when §8 is due, or on request. Keep a pass short.

## The trap

An entry that *reads* ready is not ready until it has been checked against today's code. Half
of a stale backlog is already fixed, refactored away or superseded; ranking it before clearing
it wastes the user's attention on items that should not exist.

## 1. Mechanical signals

`python3 scripts/wip.py refine all` and `python3 scripts/wip.py check`. Flags:

| Flag | Means | Usual action |
|---|---|---|
| `stale` | no commit on the entry for over `STALE_DAYS` days | revalidate or drop — an idea that matters will come back |
| `dead-path:[…]` | a backticked path no longer exists | refactored away, or a file the fix proposes to create: read the sentence |
| `links-closed:[…]` | links an entry already in `done/` | maybe already fixed, or to merge |
| `no-fix` / `no-acceptance` | a section is missing | candidate for *needs detail* |
| `open-question` | waiting on the user | ask it this pass |
| `crowded theme` | more than `CROWDED_THEME` open entries on one theme | candidates to *merge* |
| `BLOCKS-RELEASE` | `Blocks release: yes` | always **promote** |

## 2. Check each entry against the code

Read-only. For each entry: grep the files it names, `git log --oneline -- <path>` since its
`Noted` date, and look for a merged pull request that fixed it without closing it. **Every
verdict carries one piece of evidence**: a line, a commit, a command output.

Over 15 entries: split them by theme across 2–3 `Explore` agents, each returning one line per
entry — `still-true | fixed-by <sha/#PR> | changed <what>` plus the evidence. **Never ask an
agent to judge priority**: ranking is the user's call, prepared by you.

## 3. Six bins, in this order

Hygiene before prioritisation: what goes away is cleared first, so it is never ranked.

1. **Already fixed** → `done/` with `**Status:** done (date) — fixed by <sha/#PR>`.
2. **Obsolete** → `done/` with `**Status:** dropped (date) — <why>`.
3. **Merge** → the survivor absorbs the others' evidence; each other one goes to `done/` with
   `**Status:** dropped (date) — merged into [[<survivor>]]`.
4. **Needs detail** → give the **exact question** that would make it ready. "Needs more
   thought" is not an answer.
5. **Ready** → meets §4.
6. **Promote** → ready, and in the top of §5's ranking, up to `WIP_LIMIT` entries in
   `wip/todo/`.

## 4. Definition of ready — all six must hold

1. **Still true**, with the evidence from §2.
2. **One pull request**: a concrete `**Fix:**`, about a day of work, one reason to revert.
   Bigger gets split into several entries.
3. **Testable**: `**Acceptance:**` holds 2–5 checkable statements. You draft them; the user
   validates them. Never a criterion that needs hardware or an account nobody here has.
4. **Unblocked**: no open question, no dependency on an entry not yet done.
5. **Themed** with an existing tag (`python3 scripts/wip.py themes all`); a new tag only when
   none fits.
6. **Grounded, if the subject is common.** An entry about a problem that is not specific to
   this project (backups, deploy ordering, migrations, caching, CI metrics, auth flows) needs
   a `**State of the art:**` section: you run the search yourself (`WebSearch`/`WebFetch`)
   and write current practice, the sources, the date consulted, and where the proposed fix
   departs from it and why.

Ready is required for **promotion**, not for writing an entry.

## 5. Prioritise

No scoring formula: at this size, RICE or WSJF cost more than they decide. Rank by
**cost-of-delay class** first:

| Class | What |
|---|---|
| Expedite | blocks the release, security, crash, data loss |
| Fixed date | a deadline outside the project (a policy date, an event) |
| Standard | user-visible value |
| Intangible | tooling, docs, debt |

Then, within a class, value (H/M/L) against cost (S/M/L). Entries that would share a pull
request are ranked together. One line of reason each. `wip/todo/` holds at most `WIP_LIMIT`
entries — about one `ship-parallel` run.

## 6. Propose

One table per non-empty bin: entry, verdict, evidence, and for *needs detail* the question.
Then one **multi-select** `AskUserQuestion` per non-empty bin (at most four questions per
call; the needs-detail questions go in the same rounds). Unticked entries stay where they are.

In a team project, sort the entries by owner first. An entry's owners:
`python3 scripts/owners.py` fed the paths it names in backticks, one per line — or, if it
names none, a file in its `Area` component's directory (`.llmwiki/Project.md` § Components);
for an `Area` that is not a component, the owners of `wip/`. Your areas:
`python3 scripts/owners.py --who "$(gh api user --jq .login)" </dev/null`. An entry outside
your areas gets its verdict like any other, in its own table, but the user does not decide
it alone: ticking it means "propose it to its owners" (§7.5). Why: the owner answers for that
part of the code; a promotion or a drop they learn about after the merge is a decision taken
over their head.

## 7. Apply in one pull request

1. `git fetch --prune origin && git worktree add --no-track -b chore/refine-<date> <WORKTREE_PREFIX>refine-<date> origin/<default>`.
2. Every move is a `git mv`; a file name never changes. The `**Status:**` line goes directly
   under the title. Answers and approved criteria are written into the entries; deferred
   questions become `**Open question:**` lines.
3. `python3 scripts/wip.py check` green, commit, push, pull request (`gh pr create --base
   <default>`), merged through `ship-parallel` §3 as `AUTONOMY` allows — lane A, nothing to
   deploy; under `AUTONOMY=pr` the user merges it.
4. Report: counts per bin, the pull request, and what is now in `wip/todo/`.
5. Team projects, entries outside your areas: never in the first pull request — your own
   decisions would wait on theirs. A second one, `chore/refine-<date>-owners`, in its own
   worktree the same way, with every move listed in its body with its evidence, opened with
   `gh pr create --base <default> --reviewer <owner>,<owner>`: `wip/` belongs to whoever owns
   it, so GitHub would not ask the entries' owners by itself. It merges only once each owner
   it names has approved — the check of `ship-parallel` §3b, with these owners. A move an
   owner turns down is undone in a new commit (`git mv` back); the rest goes ahead.

## 8. Pruning pass

`RELEASE_MODE=continuous`: run it every `PRUNE_EVERY_MERGES` merges, or at a refinement pass
if that comes first. Count the merges since the last pass — every squash merge is one commit
on `<default>`: `git log -1 --format='%h %ad %s' --date=short -i --grep=prune origin/<default>`
finds the last pass, `git rev-list --count <that sha>..origin/<default>` counts since (no pass
yet: `git rev-list --count origin/<default>`). `RELEASE_MODE=planned`: it runs before each
release, from the project's `release` skill (§3b); run it here only when asked.

Why it exists: without it every incident adds a rule and none is ever removed; one project's
`CLAUDE.md` had reached 204 lines, 40 % of them process, before a budget was set.

The process gets pruned, not only grown. This pass **proposes**; the removals are their own
pull request (`chore/prune-<date>`), decided by the user in one `AskUserQuestion`.

1. List every hook refusal (`.llmwiki/Hooks.md` § What is refused) and every rule line of
   `CLAUDE.md`.
2. For each, look for evidence it fired or mattered since the last pass: a refusal in recent
   sessions (with `TOOLING_LEVEL=complet`:
   `python3 scripts/agent_metrics.py --since <date> --by hook`), a `wip/` entry or a commit
   that cites it, a fix it would have prevented. No evidence → candidate for removal, or for
   merging into another rule. Prefer replacing a rule to adding one next to it. The hooks
   live in the plugin, not in this repository: a hook refusal to remove is a `wip/` tooling
   entry that proposes the change upstream, not an edit here.
3. `wc -l CLAUDE.md` against `CLAUDE_MD_BUDGET`: anything past it moves to the wiki page that
   owns it.
4. `python3 scripts/wiki_lint.py`; fold old `Status: Outdated` blocks into the facts they
   correct; split pages over `WIKI_PAGE_BUDGET`.
5. Only when `TOOLING_LEVEL=complet` and the script exists: `python3 scripts/delivery_metrics.py`
   against the baseline in `.llmwiki/ParallelDelivery.md`; update the baseline row.
6. Only when `TOOLING_LEVEL=complet` and `evals/` exists: run the evals on
   `origin/<default>`, then with `--ref HEAD` on the pruning branch: a case that passes before
   and fails after is evidence that the removed rule was carrying weight — put it back.

## When the tool itself fights you

A flag that fires on the wrong thing, a bin that does not fit, a limit that is always wrong:
record it as a `wip/` tooling entry (`CLAUDE.md`). Do not bend the pass around it. When the
tool is the plugin's (a hook, this skill, a vendored script such as `scripts/wip.py`), the
entry proposes the change upstream: a vendored copy is never edited in place (`sync-tooling`).

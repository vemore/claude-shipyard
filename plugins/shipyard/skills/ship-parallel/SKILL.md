---
name: ship-parallel
description: "Implement a set of wip/ entries in parallel — one pull request per theme, each rated for risk and difficulty and built by one agent in its own git worktree; then review, update and squash-merge each green pull request one at a time, deploy and smoke-test what each merge changed when the project deploys, wait for code owners' approval in a team project, and clean up. Use when the user lists tasks to implement, asks to work through wip/todo or in parallel, or asks to merge or deploy finished pull requests. Triggers: \"implement these\", \"work in parallel\", \"ship the todo\", \"merge and deploy\", \"gh pr merge\", \"implémente ces tâches\", \"attaque en parallèle\", \"lance les PR\", \"fusionne et déploie\"."
---

# ship-parallel

One theme → one worktree → one agent → one pull request → squash-merged into `<default>` →
deployed, when the project deploys. You are the **orchestrator**: you plan, launch, review,
merge, deploy and verify, as far as the project's `AUTONOMY` lets you. The agents implement.
The facts and the reasoning behind every step are in `.llmwiki/ParallelDelivery.md` — read it
once per session before §1.

## Read the project's settings

This skill serves every project that enables the plugin; what differs is in two files of the
project. Read them before §0, and again at the step that uses a value — never copy one into a
file.

- `scripts/lib/tooling.conf`: `DEFAULT_BRANCH` (written `<default>` below), `PROJECT_SLUG`,
  `WORKTREE_PREFIX`, `SIZE_THRESHOLD`, `LANE_C_RE`, `DEPLOY_PATHS_RE`, `CONCURRENCY_CAP`,
  `WIP_LIMIT`, `PRUNE_EVERY_MERGES`, `TOOLING_LEVEL`, `TEAM_MODE`, `AUTONOMY`, `RELEASE_MODE`.
- `.llmwiki/Project.md`: the silent-failure classes (§ Risk), the agents (§ Agents), the
  documents that move together.

No `scripts/lib/tooling.conf`: this repository is not set up for the plugin — say so and stop.
A key an older project lacks: `TEAM_MODE` is `solo`; `AUTONOMY` and `RELEASE_MODE` are what
`Project.md` § Delivery says, else `pr`, and `planned` if `.claude/skills/release/` exists,
else `continuous`.

| Setting | What changes below |
|---|---|
| `DEPLOY_PATHS_RE` empty | nothing deploys: skip §0.4, §1.6 and §4 |
| `LANE_C_RE` empty | no lane C: skip every sentence about it |
| `AUTONOMY=merge-deploy` | you merge and deploy |
| `AUTONOMY=merge` | you merge; the user deploys (§4 lists what) |
| `AUTONOMY=pr` | you open, review and update pull requests; the user merges (end of §3); no §4 |
| `TEAM_MODE=team` | owners in the plan (§1.7); another owner's area waits for their approval (§3b) |
| `TOOLING_LEVEL=complet` | delivery metrics in the report (§6.5) |
| `RELEASE_MODE=planned` | releases are the project's `release` skill, on request only |
| `RELEASE_MODE=continuous` | the pruning pass is `wip-refine` §8, every `PRUNE_EVERY_MERGES` merges |

Skills of this plugin go by their short name (`wip-refine` is `/shipyard:wip-refine`);
`deploy` and `release` are the project's own skills, in `.claude/skills/`.
`${CLAUDE_PLUGIN_ROOT}` is the plugin's directory — two levels above this skill's base
directory if your shell does not expand it.

## The one rule you cannot break

`<default>` only moves through a squash-merged pull request whose required checks are green on
an up-to-date branch. No push to it, no `--admin`, no force-push, no stacked pull request. The
hooks refuse each of these; a refusal is information about your plan, never an obstacle to
route around (another command shape, a script, the API). A stacked pull request once merged
into its parent's branch after the parent had landed: both read "merged", and the child's work
reached nothing.

## 0. Where you stand

1. Work from the **main checkout, on `<default>`**, current:
   `git fetch --prune origin && git merge --ff-only origin/<default>`. Every worktree is cut
   from `origin/<default>`, and the plugin's hooks judge each command against the
   `tooling.conf` and `scripts/check.sh` of the repository it runs in: a stale main checkout
   plans and gates with stale values.
2. If the main checkout is on another branch with work in it, it belongs to another session:
   do not switch it — ask the user.
3. The session-start report lists worktrees and branches whose remote is gone. A worktree whose
   pull request is still open is work in flight: resume it, never start the same theme twice.
   Leftovers of a finished loop: run §6's cleanup before planning anything new. If it says the
   vendored tooling is behind the plugin, put that in the plan: the sync is its own pull
   request (`sync-tooling`), never folded into a theme.
4. Skip unless `DEPLOY_PATHS_RE` is set and `AUTONOMY=merge-deploy`. An open
   `wip/todo/*-merged-not-deployed.md` entry means an earlier session merged without
   deploying. Once §1.6 says the target is reachable, deploy `origin/<default>` (§4) and close
   that entry before anything else.
5. Skip unless `TEAM_MODE=team`. You are `gh api user --jq .login`; your areas are
   `python3 scripts/owners.py --who <login> </dev/null`. Exit 1 — you own nothing yet — means
   every pull request will wait for someone else's approval: suggest `join` first.

## 1. Plan the pull requests

1. **Read the entries.** `git fetch --prune origin`, `python3 scripts/wip.py list all`, then
   read every entry the user named in full. A task with no entry gets one written first
   (`wip/README.md`). A `todo_nr/` entry that is not *ready* (`wip-refine` §4) goes through
   `wip-refine` first — implementing an unready entry is how a pull request ends up proving
   nothing.
2. **Group by `Theme`, then split or merge on files.** The tag is a first guess; the files
   decide:
   - two groups that will edit the same file in a way that cannot merge cleanly — a shared
     migration head, the same generated file, the same central module or registry, the same
     screen — become one pull request, or two **waves**;
   - a group that needs another's result (a schema, an endpoint, a new module) goes in a later
     wave, launched after the first one merges. Never a stacked pull request.
   - one pull request stays reviewable: about a day of work, one reason to revert, under
     `SIZE_THRESHOLD` counted lines (§3.1).
3. **Merge order.** Schema and backend first, then the code that uses them, then docs. A pull
   request touching `.claude/` (settings, project skills or agents), `scripts/lib/tooling.conf`
   or `scripts/check.sh` merges **last in its wave**, once every agent of the wave has
   reported: fast-forwarding the main checkout changes the settings, values and gates under
   the sessions still running.
4. **Lane — the risk to production, decided now, from what the change will touch:**

   | Lane | When | Before merging |
   |---|---|---|
   | A | everything else | checks green or skipped, you read the diff |
   | B | over `SIZE_THRESHOLD` counted lines; or a failure that would be **silent** (the classes listed in `.llmwiki/Project.md` § Risk: data migrations, persisted formats, contracts with other systems…); or a call site many features depend on | A + acceptance criteria in the entry + an independent review (§3.2) |
   | C | a diff matching `LANE_C_RE` (none when it is empty) | B + the user's explicit go-ahead for that merge — or, in a team project, the owner's approval for the paths they own (§3b) |
   | D | an experiment written to learn, not to ship | a branch with `git config branch.<name>.noPullRequest true`; never merged as is; what it taught becomes a `wip/` entry |

   Lanes B and C **require acceptance criteria in the entry**; if an entry has none, write
   them with the user now — §3 refuses the merge without them, because they are what the
   reviewer judges the tests against. **In doubt, the stricter lane**: raising a lane costs
   one review, missing one costs a production fix.
5. **Rating — the difficulty, which picks the implementer:**

   | Rating | When | Launched as |
   |---|---|---|
   | complex | a design choice is open, several subsystems move together, the root cause is unknown, or the lane is B or C | `subagent_type: "shipyard:implementer-complex"` |
   | simple | the entry's fix is explicit and local, and its acceptance is mechanical | `subagent_type: "shipyard:implementer-simple"` |
   | bulk | many independent, mechanical, well-specified units (translations of a master text, a sweep over files) | one `general-purpose` agent per unit, `model: "haiku"`, launched by **you** (§2.3) |

   A project that defines its own agents in `.claude/agents/` names them in `Project.md`
   § Agents: launch those names instead. **In doubt, complex**: an under-rated change costs a
   rework, an over-rated one only tokens.
6. **Can this session deploy?** Skip unless `DEPLOY_PATHS_RE` is set and
   `AUTONOMY=merge-deploy`. Run `.claude/skills/deploy/scripts/probe.sh`. It prints a verdict
   and never a host. Anything but `deploy: reachable` becomes the plan's first line: "this
   session cannot deploy — merges will land *merged, not deployed* (§4)". The user then
   chooses between merging anyway and leaving the pull requests for a session that can deploy.
7. **One approval.** Present the whole plan in **one** `AskUserQuestion`: for each pull request
   its branch name, entries, lane, acceptance criteria (B, C), rating (and bulk units), likely
   files, wave and merge order, plus the deploy verdict when §1.6 ran. In a team project, add
   each pull request's owners — `printf '%s\n' <likely files> | python3 scripts/owners.py` —
   and mark the ones that touch an area you do not own: they will wait for that owner (§3b),
   so order the others so that none depends on them, and keep a foreign part in its own pull
   request when that lets the rest go ahead. The go-ahead covers the whole loop below — every
   merge and deploy `AUTONOMY` allows. It does **not** stand in for lane C's per-merge
   go-ahead (§3.2), nor for another owner's approval (§3b). At most `CONCURRENCY_CAP`
   implementers run at once; a bigger wave is split.

## 2. Launch one agent per pull request

1. All agents of a wave in **one message**, each with `isolation: "worktree"` and the
   `subagent_type` its rating picks. Pass **no** `model`: a per-call model overrides the
   definition's, and the effort level exists only in the definition. If the session does not
   list `shipyard:implementer-*` (the plugin was enabled after the session started), launch
   `general-purpose` with `model: "sonnet"` and `isolation: "worktree"`, and say so in the
   report.
2. The tool creates the worktree under `.claude/worktrees/<name>` on a branch
   `worktree-<name>`; the agent's first step moves it to the real branch.
3. **Bulk units are yours** — an implementer has no `Agent` tool. Its prompt says to stop
   before its first commit and report what is left. You then write the master (the reference
   text, the first instance of the sweep) in its worktree; launch one `general-purpose` agent
   per unit with `model: "haiku"`, all in one message, **no** isolation, each given the
   worktree's absolute path, the one file it owns, the same guardrails list, and no commit;
   review the results on form (structure, markers, numbers, names copied byte for byte); then
   `SendMessage` the implementer to commit and carry on. A pull request that is nothing but
   bulk you hold yourself, in a worktree of your own.
4. Fill in this prompt for each agent (`<project>` is `PROJECT_SLUG`; drop the lines that do
   not apply). **Do not shorten the rules.**

```text
You implement one pull request of <project>, in the git worktree you start in.

Pull request: <type>/<topic> — <one-line goal>
Entries to close: <wip/todo/....md paths>
Lane: <A | B | C>. <For B and C: another agent reviews this change before it merges; the
acceptance criteria below are what that review judges your tests against.>
Acceptance criteria (B and C): <the entries' criteria, one per line>
Files you will likely touch: <list>. Other agents are working in parallel on: <other pull
requests and their files> — stay out of those files; if you cannot, say so in your report.
Owners (team projects): <path → @owner, for the areas the user does not own>. Those owners
must approve this pull request before it merges: write its body for them — what changes in
their area, and why.

Rules:
1. First: `git fetch --prune origin && git switch --no-track -c <type>/<topic> origin/<default>`,
   then `scripts/worktree_setup.sh` (add `--no-<component>` for each component the change does
   not touch). `--no-track`: a branch tracking origin/<default> would push and pull there; the
   first `git push -u` gives it its own upstream.
2. Read CLAUDE.md, .llmwiki/INDEX.md and the pages the change touches. Use the project skills
   that cover the work.
3. Implement, with tests. Update, in this pull request, every wiki page, README.md or other
   document the change makes false.
4. Close each entry in this pull request: `git mv wip/todo/X.md wip/done/X.md` (same name),
   and add directly under its title:
   `**Status:** done (YYYY-MM-DD) — closed by <type>/<topic>. <one or two sentences>`.
   A problem you find but were not asked to fix becomes a new entry in wip/todo_nr/ (or
   wip/todo/ if it blocks the release: security, crash, data loss) — never fix it inline,
   never edit an entry another pull request owns.
5. Commit (the hook runs the fast gates in this worktree), `git push -u origin <type>/<topic>`,
   `gh pr create --base <default>` with a body saying what changed and why.
6. Watch `gh pr checks <n> --watch` and fix what fails until every check is green or
   skipped — the Scope job skips the components the change does not touch, and a skipped
   job counts as passing. A push rejected because the remote branch moved (the orchestrator
   merged <default> into it on GitHub): `git pull --no-rebase origin <type>/<topic>`, then
   push — never rebase, never force.
   Circuit breaker: after three fix attempts on the same failing check (or the same failing
   test locally), stop — no fourth attempt, no loosened assertion, no skipped test. Report
   the failure as one of TEST_ISSUE (the test is wrong or asks for something the entry does
   not), IMPL_ISSUE (the code cannot meet the test as far as you can tell), DOC_ISSUE (a doc,
   wiki page or entry contradicts another and you cannot tell which side to trust) or
   UNCLEAR, with the check name, the last error and what the three attempts tried.
7. Never merge, never deploy, never force-push, never push to <default>.
8. Report, briefly: pull request URL and number, check state, files touched, migrations
   added, generated files regenerated, anything the orchestrator must know to merge or
   deploy (environment variables, manual steps), entries you created, and — if the circuit
   breaker tripped — its class. On lanes B and C, map each acceptance criterion to the test
   that covers it, by name.
```

5. **When an agent reports.** The `SubagentStop` hook refuses to let an agent finish while its
   commits have no pull request or its checks are red; a report without a green pull request
   therefore means the agent was blocked twice — read why before doing anything. A report
   carrying a circuit-breaker class is acted on by class, **never** by relaunching the same
   prompt unchanged:

   | Class | What you do |
   |---|---|
   | `TEST_ISSUE` | Read the test against the entry's acceptance. Test wrong → `SendMessage` the agent (or a fresh one on the same branch) the correction. Test right → treat as `IMPL_ISSUE`. |
   | `IMPL_ISSUE` | Read the last error and the three attempts yourself; relaunch with your diagnosis in the prompt, or narrow the pull request and move the rest to a new `wip/` entry. |
   | `DOC_ISSUE` | Decide which side is true — ask the user if the answer changes what the entry asks for — and relaunch with that answer. |
   | `UNCLEAR` | Ask the user, with the agent's evidence. The pull request waits and merges after its wave. |

   An implementer rated simple that stops to say the change is not simple is re-rated complex
   and relaunched as `shipyard:implementer-complex` — it is the rating that was wrong, not the
   agent.

## 3. Merge, one pull request at a time

Merges are serial: `<default>` requires an up-to-date branch, so every merge makes every other
open pull request stale. Take them in the planned order. Under `AUTONOMY=pr`, steps 1–5 only
(see the end of this section).

1. **Read it and size it.** `gh pr view <n> --json state,mergeable,mergeStateStatus,headRefName`
   and `gh pr diff <n>` — you are the only reader before the merge. Check that it closes its
   entries and touches what its report says. Then `python3 scripts/pr_size.py <n>`: above
   `SIZE_THRESHOLD` the pull request is lane B whatever the plan said. The count is the
   **backstop** for a lane misjudged at planning, not the gate itself; it counts added or
   modified lines of code only (no docs, tests, lock or generated files), because a cap that
   counts tests pushes against the tests. In an earlier project a +6 900-line pull request
   merged on the day it opened needed six fix pull requests the same day.
   Unless `LANE_C_RE` is empty: `gh pr diff <n> --name-only | python3 scripts/lane_paths.py lane-c`
   — any path printed makes it lane C whatever the plan said.
2. **Apply the lane.** Lane A: nothing more. Lanes B and C:
   - each acceptance criterion maps to a named test in the agent's report — otherwise back to
     the agent;
   - launch a **fresh** agent, `subagent_type: "shipyard:reviewer"` — never the implementing
     one: the agent that wrote the change also wrote the tests that judge it. Give it the pull
     request number, the entries and their acceptance criteria. Its definition carries the
     calibration rules and the report format. Fallback when the session does not list it:
     `general-purpose`, `model: "sonnet"`, `isolation: "worktree"`, with the body of
     `${CLAUDE_PLUGIN_ROOT}/agents/reviewer.md` pasted in — never without isolation: a
     reviewer that detaches HEAD would move the main checkout;
   - report **every** finding to the user, whatever its severity, with what you intend to do
     about it: fixed in this pull request (by the implementer, via `SendMessage`), a new
     `wip/` entry, or dismissed and why. In an earlier project the first planned review
     found a data repair that green checks had passed and that would have been undone by the
     next sync.
   - lane C only: ask an explicit `AskUserQuestion` go-ahead **for this merge**, after the
     findings. The plan approval in §1 does not cover it. In a team project, the approval of
     the owner of a lane-C path someone else owns stands in for it on that path (§3b); paths
     you own, or nobody owns, still need the user's go-ahead.
   - in a team project, §3b decides whether it may merge yet. A pull request waiting there
     leaves the queue: go on with the next one, and come back to it.
3. **Update the branch.** Only when it is behind (`mergeStateStatus` `BEHIND`; `DIRTY` means
   conflicts: step 4 first). Note `gh pr view <n> --json headRefOid --jq .headRefOid`, then
   `gh api -X PUT repos/{owner}/{repo}/pulls/<n>/update-branch`. It merges `<default>` into
   the branch on GitHub — no rebase, no force-push, and the agent's worktree stays valid.
   (Rebasing would need a force-push, which destroys the review history and the commits of a
   worktree an agent may still hold.) The update is **asynchronous**: wait until `headRefOid`
   changes before step 5, or `--watch` reports the old head's green checks. The branch on
   GitHub is now ahead of the agent's worktree: anyone who touches that worktree again first
   runs `git -C <worktree> pull --no-rebase`.
4. **Conflicts** are resolved in that pull request's worktree:
   `git -C <worktree> pull --no-rebase && git -C <worktree> fetch origin && git -C <worktree> merge origin/<default>`,
   fix, commit, push. Recipes:
   - generated files: merge the **sources**, then regenerate; never hand-merge generated
     output — take either side and rerun the generator;
   - migrations: two revisions on the same parent → re-chain the later one onto the other so
     there is one head;
   - wiki pages: keep both facts, and the later `Updated:` date; same for the `INDEX.md` row;
   - lockfiles: take `<default>`'s, then re-lock with the package manager;
   - `wip/`: two branches never touch the same entry; a conflict there means one of them
     edited an entry it did not own — keep the owner's version;
   - a real semantic clash between two themes: **stop and ask the user**.
5. `gh pr checks <n> --watch` on the updated head: every check green or `skipping`. Note
   that head: `gh pr view <n> --json headRefOid --jq .headRefOid`.
6. In a team project, run §3b's check once more first: updating a branch can dismiss an
   approval. Then `gh pr merge <n> --squash --match-head-commit <that sha>` (the hook refuses
   `--admin`, `--merge`, `--rebase`; `--match-head-commit` refuses to merge a head nobody
   watched), then in the main checkout
   `git fetch --prune origin && git merge --ff-only origin/<default>`. No `--delete-branch`:
   gh would try to switch a worktree to `<default>`, which the main checkout already holds,
   and fail after a successful merge — the repository setting deletes the remote branch, and
   §6's cleanup the local one.
7. The next pull request is now behind `<default>`: back to step 3 for it.

**`AUTONOMY=pr`: you do not merge.** Run steps 1–5 for each pull request (lane review
included), then stop: list the pull requests that are green, up to date and reviewed, in merge
order — and, in a team project, the owners each one still waits for — for the user to merge.
Updating one after the user merges another is your job when asked. Skip §4.

## 3b. Another owner's area (team projects)

Skip when `TEAM_MODE` is `solo`. Why: in a team, the owner answers for their area in
production; a merge they never saw is how a team stops trusting the process.

1. `gh pr diff <n> --name-only | python3 scripts/owners.py` prints each changed path with its
   owners. A path whose owners do not include you is a **foreign area**. An owner written
   `@org/team` includes you when
   `gh api orgs/<org>/teams/<team>/memberships/<login> --jq .state` says `active`. A path
   with no owner is nobody's area: no approval needed.
2. GitHub has already asked those owners for a review (CODEOWNERS). Name them in your report.
3. `gh pr view <n> --json latestReviews --jq '.latestReviews[] | [.author.login, .state] | @tsv'`:
   the pull request may merge once **each** foreign area has an `APPROVED` review from one of
   its owners. A `CHANGES_REQUESTED` from an owner goes back to the implementer
   (`SendMessage`), and the wait starts again.
4. Until then it waits, and the others go on in the planned order. Look again before each
   later merge. At the end of the loop, a pull request still waiting is reported as open,
   with the owners it waits for; its worktree stays (§6's cleanup keeps it).
5. The owner's approval is lane C's go-ahead for the lane-C paths they own (§3.2).
6. **Never bypass**: no merge before the approval, no `--admin`, no approval from someone who
   does not own the area, no removing the foreign paths from the pull request without the
   user's say, no edit of CODEOWNERS to make yourself the owner (that is `join`, and its own
   pull request).

## 4. Deploy what the merge changed

Skip this section when `DEPLOY_PATHS_RE` is empty or `AUTONOMY=pr`. Under `AUTONOMY=merge`,
run step 1 only and list in the report what each merge would deploy: the user deploys.

After **each** merge, so that a regression in production points at one pull request.

1. What changed: `git diff --name-only <sha>^ <sha> | python3 scripts/lane_paths.py deploy`
   on the squash commit. Nothing printed → nothing to deploy.
2. Deploy from a clean tree at the merged commit, **never from an agent's worktree**:
   `git worktree add --detach <WORKTREE_PREFIX>deploy origin/<default>` (or
   `git -C <it> switch --detach origin/<default>` if it exists), then
   `scripts/worktree_setup.sh <WORKTREE_PREFIX>deploy --deploy` — the only worktree that gets
   the deploy secrets. Then the project's `deploy` skill.
3. Smoke-test: the health or version endpoint **read for its content** (the build id is the
   merged sha), then the path the pull request changed, driven for real. Record what you
   checked. A health endpoint answering "ok" proves the process is up, not that it works.
4. **Merged, not deployed — never a silent success.** When the deploy cannot run (§1.6 said
   unreachable, or it fails before changing anything), say so for that pull request, and
   write **one** `wip/todo/<date>-merged-not-deployed.md` for the loop (`Theme: deploy-safety`,
   `Area: infra`, `Blocks release: yes`), one line per squash sha with what it needs. Its fix
   is "deploy `origin/<default>`": one deploy covers every sha listed. It goes in through its
   own `docs/` pull request after the loop's last merge. In an earlier project a session that
   could not reach the deploy host merged five pull requests and ended as if all was well;
   production kept running code from five days earlier until a real client hit a missing
   endpoint.
5. A deploy that ran and **broke** production is not that case: roll back first (the
   `deploy` skill's rollback section), then fix through §5.

## 5. Follow-up fixes

A problem found after a merge is a **new** pull request, never a commit on the merged branch
(it is gone, and the hook refuses commits on it): write the entry in `wip/todo/`, launch one
agent with the same prompt, then §3 (and §4 when it applies).

## 6. Clean up and report

1. Wait until **every** agent has reported: a clean worktree on a branch with no commit yet
   looks abandoned to the cleanup script.
2. `python3 scripts/cleanup_local.py` (dry run), then `--apply`. Read the `keep` lines and
   never force one away — each names its reason (a live session's lock, a setup in progress,
   recent changes, uncommitted work, commits GitHub cannot prove were merged).
3. `git worktree list` and `git branch -vv` should then show `<default>` and work in flight
   only.
4. Report: each pull request (URL, merged or not, lane, rating); each deploy and its smoke
   test, and any *merged, not deployed* sha, when §4 ran; in a team project, the pull requests
   still waiting and for whom; the entries created; and what is left
   (`python3 scripts/wip.py list`). If `wip/todo/` now holds fewer entries than `WIP_LIMIT`
   and `todo_nr/` is large, say that a `wip-refine` pass is due. Under
   `RELEASE_MODE=continuous`, if `PRUNE_EVERY_MERGES` merges have landed since the last
   pruning pass (`wip-refine` §8 says how to count), say that the pass is due.
5. Only when `TOOLING_LEVEL=complet` and `scripts/delivery_metrics.py` exists: paste its output
   as printed. Name any figure worse than the baseline in `.llmwiki/ParallelDelivery.md`
   (rework rate, change failure rate, first-run green); do not act on it here — the pruning
   pass does (the `release` skill §3b under `RELEASE_MODE=planned`, `wip-refine` §8
   otherwise).

## When NOT to use this skill

- One small change: do it yourself on a fresh branch in a worktree (`CLAUDE.md` § Git).
- An experiment: lane D, by hand, on a `noPullRequest` branch.
- Sorting or promoting the backlog: `wip-refine`.
- Becoming the owner of an area, in a team project: `join`.
- Updating the vendored scripts to the plugin's version: `sync-tooling`.
- Cutting a release (`RELEASE_MODE=planned`): the project's `release` skill, on the user's
  request only.

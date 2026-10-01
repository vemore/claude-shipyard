# Annexe 4 — Faits pour le wiki : hooks, outillage, livraison

> Lue par **WP-D**, qui écrit `.llmwiki/Hooks.md`, `Testing.md` et `ParallelDelivery.md`, et les
> compléments de `Security.md`, `Deployment.md` et `Documentation.md` (§5). Elle dit ce que le
> plugin `shipyard` fait **vu du projet** : le projet ne contient ni les hooks, ni les skills de
> livraison, ni cette annexe, et ses agents n'auront que ces pages pour savoir ce qui les juge et
> pourquoi. Gabarit de page et titres `###` fixes : annexe 06 §1-§2. Raisons à semer : annexe 01
> §9 ; les graines ci-dessous les rendent concrètes page par page.

## 1. Comment écrire ces pages

- **Une version.** Les faits décrivent la version du plugin enregistrée dans
  `scripts/lib/VENDORED.json` (champ `shipyard`). Chaque page qui décrit le plugin le dit en une
  ligne, en tête de `## Facts` : « Behaviour of the shipyard plugin <version>, the version
  recorded in `scripts/lib/VENDORED.json`; `/plugin` shows the one installed in a session. »
  Après une mise à jour du plugin, `/shipyard:sync-tooling` relit ces pages contre la nouvelle
  version.
- **Le comportement, pas le code.** Un hook se décrit par ce qu'il refuse, sur quelle preuve,
  avec quel remède ; jamais par du code recopié (convention 10 de l'annexe 06). Il se cite par
  son nom (« the plugin's `guard_bash.py` hook ») : il n'a pas de chemin dans le dépôt, donc pas
  de `chemin:ligne`. Un script vendorisé, lui, a un chemin (`scripts/cleanup_local.py`), et se
  cite ainsi.
- **Les valeurs en clair**, avec le nom de leur clé : « `SIZE_THRESHOLD` = 1500 lines
  (`scripts/lib/tooling.conf`) », jamais « environ ».
- **En cas de doute**, la source est le plugin installé : le dossier trois niveaux au-dessus de
  celui de ces annexes, ses `hooks/*.py` et ses `templates/scripts/`, dont chaque en-tête dit
  usage, garanties, limites et raison. Ce qu'il dit gagne sur cette annexe ; l'écart va dans le
  rapport de WP-D.
- **Blocs conditionnels** : *(équipe)* seulement si `TEAM_MODE=team` ; *(si cible)* seulement si
  `DEPLOY_PATHS_RE` n'est pas vide ; *(Complet)* seulement si `TOOLING_LEVEL=complet` — jamais
  en shipyard 0.1, où ces blocs cèdent la place à un lien vers l'entrée `wip/todo_nr/` qui
  attend l'élément. Un bloc qui ne s'applique pas disparaît sans laisser de trace.
- **Graines de `Decisions & History`** : en anglais (ou traduites dans la langue de la doc),
  datées du jour du bootstrap, marquées « inherited at bootstrap », génériques (« an earlier
  project… ») : jamais un incident inventé dans ce projet. Format : annexe 01 §9.

## 2. `Hooks.md`

**Scope** : what the shipyard plugin's hooks refuse in this repository, on what evidence, what
they leave alone, and why the project relies on them. Related : `[[Testing]]` ·
`[[ParallelDelivery]]` · `[[Security]]` <· `[[Team]]` (équipe)>.

### What is configured

- **D'où ils viennent.** Du plugin `shipyard` (marketplace `claude-shipyard`), activé pour ce
  dépôt par `.claude/settings.json` (`enabledPlugins`). Ce fichier n'a **pas** de bloc `hooks`,
  exprès : les hooks du plugin s'y ajouteraient en double. Ils se chargent au démarrage de la
  session (`/hooks` les montre) : une mise à jour du plugin vaut à la session suivante.
- **Tableau** Event | Matcher | Plugin script | Role :

  | Event | Matcher | Plugin script | Role |
  |---|---|---|---|
  | `SessionStart` | — | `session_start.sh` → `session_start.py` | what the session must know before it works (below) |
  | `PreToolUse` | `Bash` | `guard_bash.py` (with `parse_command.py`) | refuses the command shapes of § What is refused; at `git commit`, also secrets, `wip/` rules, branch discipline and the fast gates |
  | `PostToolUse` | `Edit\|Write\|MultiEdit` | `post_edit.py` | runs `scripts/check.sh edit <file>` in the file's repository and reports to the model; never blocks |
  | `Stop`, `SubagentStop` | — | `require_pull_request.py` | no end of turn with commits that no pull request covers, or with a red pull request; blocks once per turn |

- **Ce qu'ils lisent du projet** : `scripts/lib/tooling.conf` et `scripts/check.sh` **du dépôt
  jugé** (une branche est jugée sur ses propres valeurs et ses propres gates) ; les clés
  `git config` `<GIT_CONFIG_NS>.*` et `branch.<b>.noPullRequest` ; GitHub par `gh`, en lecture
  seule, sous délai, muet hors ligne ou sans authentification.
- **Inertes sans `tooling.conf`.** Dans un dépôt sans `scripts/lib/tooling.conf`, chaque hook
  sort 0 sans rien dire — le plugin est souvent installé pour tout l'utilisateur, donc actif
  dans tous ses dépôts. Seule exception : `SessionStart` dans un dossier vide suggère
  `/shipyard:bootstrap`.
- **Ce que dit `SessionStart`**, seulement quand c'est pertinent, en quinze lignes au plus :
  dépendances manquantes (Python < 3.9, `git`, `tooling.conf`, `gh` absent ou non authentifié :
  « degraded ») ; `Branch: <b> (N ahead, M behind origin/<D>)`, avec la recette du worktree sur
  la branche par défaut et « not safe to commit on » sur une branche périmée ; les autres
  worktrees et le nombre de branches `[gone]`, avec le renvoi à `scripts/cleanup_local.py` ; les
  PR mergées depuis 14 jours dans une autre base que `<D>` dont GitHub ne retrouve pas le travail
  sur `<D>` ; **l'outillage vendorisé** — « vendored tooling is <x>, plugin is <y> — run
  /shipyard:sync-tooling » quand `VENDORED.json` est plus ancien que le plugin ou qu'une copie a
  été modifiée ; *(équipe)* l'identité — « You (@login) are not a code owner of this repository
  yet — run /shipyard:join… » ou « You own: <patterns> » (login lu par `gh api user`, gardé une
  journée en cache, rien sans `gh`) ; *(Complet)* les workflows planifiés, une fois par jour.
- **Commits humains.** `.githooks/pre-commit` (vendorisé) lance `scripts/precommit.py`
  (vendorisé) : secrets (chemin et contenu, clés `SECRET_*`) et `scripts/check.sh fast
  --paths-from` sur les fichiers indexés ; sortie 1 = refus. Il sort 0 tout de suite sous
  `CLAUDECODE=1` : le commit de Claude a déjà passé le garde du plugin. Activé une fois par
  clone : `git config core.hooksPath .githooks` (README). `--no-verify` reste l'échappatoire
  humaine assumée.
- **Réglages.** `.claude/settings.json` partagé (activation du plugin + allowlist) contre
  `.claude/settings.local.json` personnel ; la posture de permissions choisie et pourquoi
  (`Project.md`) — la posture large **suppose le plugin actif** ; l'absence volontaire de
  `defaultMode` dans le fichier partagé ; la proposition `autoMode` faite (ou non) à
  l'utilisateur.

### Which repository a hook judges

- Le **code** du hook vient du plugin installé ; le **dépôt jugé** est celui où la commande
  s'exécute : le `cwd` du payload ; pour le garde Bash, le dossier suivi à travers `cd`,
  `pushd`, `git -C`, les sous-shells, `bash -c` et `eval` déroulés ; pour `post_edit.py`, le
  dépôt du fichier édité ; pour `Stop` et `SubagentStop`, le dossier de la session ou le
  worktree de l'agent.
- **Quand il ne peut pas savoir** (un `cd "$VAR"` hérité de l'environnement, un `$(…)`, une
  ligne illisible qui contient `cd`), il refuse le commit ou le push nu avec `unknown-repo` et le
  remède `git -C <absolute path> …`, au lieu de juger le checkout de lancement.
- Le checkout principal ne décide plus des règles (ce sont celles du plugin) ; il reste sur
  `<D>` pour les raisons de `[[ParallelDelivery]]` § Worktrees.

### What is refused

Chaque refus commence par `BLOCKED (<rule>)`, puis la raison et le remède. Une ligne par règle,
**règle | déclencheur | preuve utilisée** :

| Rule | Trigger | Evidence |
|---|---|---|
| `force-push` | `git push` with `--force`, `-f`, a short group containing `f`, `--force-with-lease`, `--force-if-includes`, `--mirror`, or a `+` refspec | parsed flags |
| `push-main` | a push whose destination is `<D>`, `--all`, `--branches`, `--delete <D>`, or a bare / `HEAD` push while on `<D>` | parsed refspecs, current branch of the judged repository |
| `stacked-pr` | `gh pr create` with a base other than `<D>` | parsed `--base`; lifted only by the user's `<ns>.allowStackedPr` |
| `merge-admin` · `merge-squash` · `merge-api` | `gh pr merge --admin`; `gh pr merge` without `--squash` or with `--merge`/`--rebase`; `gh api -X PUT …/pulls/<n>/merge` | parsed flags, method and path |
| `user-only-config` | an agent writing `<ns>.allowStackedPr` or `<ns>.deliveryAcknowledged` | parsed `git config` |
| `unknown-repo` | a commit, bare push or `HEAD` push whose repository cannot be determined | the parser's own verdict |
| `secret-path` · `secret-content` | a staged path matching `SECRET_PATH_RE` and not `SECRET_ALLOW_RE`; staged content matching `SECRET_CONTENT_RE` | staged path list and staged blob content |
| `wip-shared-list` · `wip-entry-deleted` | a root `TODO.md`/`DONE.md` added; a `wip/` entry deleted without the same name added elsewhere under `wip/` | staged statuses |
| `detached-head` · `default-branch` | a commit on a detached HEAD; a commit on `<D>` | `git symbolic-ref` |
| `stale-branch` · `already-on-default` | a branch whose upstream is gone (its pull request merged); commits already on `<D>` | `%(upstream:track)`, then `git cherry` |
| `gates` · `gates-tool-missing` · `gates-error` | `scripts/check.sh fast --paths-from` exits 1, 3, or anything else / times out | exit code of the judged repository's `check.sh` |
| `bad-config` | a `*_RE` value of `tooling.conf` that does not compile | Python `re` |

Puis, en prose : l'ensemble des chemins jugés au commit (l'index, les fichiers suivis modifiés
sous `-a`, ceux de `HEAD` sous `--amend`, les pathspecs, les chemins d'un `git add`/`rm`/`mv`
placé avant sur la même ligne ; pendant un merge, le diff contre `MERGE_HEAD`) ; « run the
install as its own Bash call, then commit again » pour `gates-tool-missing` ; la recette d'une
branche périmée (`git fetch --prune origin && git switch -c <type>/<topic> origin/<D>`, puis
cherry-pick des commits `+` de `git cherry -v`). Le message d'un refus de secret nomme le chemin
et le **type** de motif, jamais la correspondance.

**Escape hatches** (paragraphe à part, dans cette section) : `branch.<b>.noPullRequest true`
(un agent peut la poser, lane D, et le dit à l'utilisateur) ; `<ns>.allowStackedPr` et
`<ns>.deliveryAcknowledged` (l'utilisateur seulement, dans son propre terminal) ; le marqueur
`secret-scan: fixture` dans les cinq premières lignes d'une fausse clé de test ;
`git commit --no-verify` (humain, hook git seulement).

### What the hooks do not cover

- **Ce qu'écrit une commande Bash** : `PostToolUse` ne se déclenche pas ; la garantie est le
  gate de commit.
- **Un merge par l'interface web**, ou par une API autre que celles lues ci-dessus : seule la
  protection de branche se tient derrière.
- **`git merge`, `git rebase --continue`, `git revert`, `git cherry-pick`**, et tout commit fait
  *à l'intérieur* d'un script lancé : le garde ne voit que la ligne qu'on lui donne.
- **Les commits humains au-delà des secrets et des gates** : `scripts/precommit.py` ne juge ni la
  branche, ni `wip/`, ni la forme d'un push ou d'un merge ; et rien sous `--no-verify`.
- **La fraîcheur d'`origin`** : les hooks ne fetchent jamais ; un silence n'est pas une preuve.
- **Publier** : le hook de PR lit GitHub, il ne pousse ni n'ouvre rien.
- **Une session sans le plugin** : aucun hook du tout. Le README demande de l'installer d'abord ;
  la CI et la protection de branche restent les derniers filets.
- **Deux versions du plugin** : chacun est jugé par la sienne jusqu'à la mise à jour.
- **L'exécution elle-même** : sans `python3`, seul l'avertissement de `SessionStart` reste ; un
  hook qui dépasse son délai ne bloque pas. Les hooks réduisent une classe d'erreurs, ils ne la
  rendent pas impossible.
- **Leur propre évolution** : changer un hook est une version du plugin, pas une PR de ce
  projet. Un hook qui a refusé à tort ou laissé passer est une entrée `wip/` (`Area: tooling`)
  qui nomme la version du plugin et la commande.

### Self-test

- Les hooks sont testés **dans le dépôt du plugin** (tables de cas, `gh` factice, dépôts bac à
  sable), à chaque changement du plugin ; ce projet ne porte pas ces tests.
- Ce que ce projet teste de la chaîne : `scripts/selftest/test_precommit.py` (vendorisé : le
  chemin des commits humains) et `scripts/selftest/test_check.py` (les gates que les hooks
  appellent), lancés par `scripts/selftest.sh` dans le job CI `tooling` (`[[Testing]]`).
- Vérification à la main après une mise à jour du plugin, dans une session neuve : le message de
  `SessionStart` apparaît ; `git push --force origin HEAD` est refusé.

### Decisions & History à semer

- **Why hooks at all** — a rule a script can decide becomes a refusal; a judgement rule stays in
  prose, because a guard that cries wolf teaches the agent to route around it.
- **Why the hooks live in the plugin, not in this repository** — one tested copy serves every
  project and a fix reaches all of them at the next update; no pull request of a project can
  weaken a guard on the way. The cost, accepted: changing a hook is a plugin release, and two
  people on different plugin versions are judged by different rules until both update.
- **Why the plugin is enabled at project scope, and inert without `tooling.conf`** — its guards
  must not reach the user's other repositories, and a repository that was never bootstrapped
  must not be judged on another project's defaults; one `SessionStart` line says so.
- **Why the guard judges the repository where the command runs, and reads its `tooling.conf`
  and `check.sh` there** — the commit happens in a worktree; a branch that changes a gate is
  judged on its own gates.
- **Why a parser rather than a grep** — quoting, `echo`, and heredocs that document a forbidden
  command made a grep refuse the very file describing the rule.
- **Why "could not tell" rather than judging the launch checkout** — in an earlier project,
  unparseable lines and unexpanded variables made work in a worktree look like commits on the
  default branch, three sessions in one day.
- **Why `[gone]` and not only `git cherry`** — a squash merge changes the patch-id; `git cherry`
  sees nothing.
- **Why fast gates at commit and tests in CI** — tests at commit were paid twice; nothing ships
  red, because the Stop hook refuses to end a turn on a red pull request.
- **Why Stop and SubagentStop** — an unpushed commit is not delivered; the hook blocks once per
  turn, and asks for every pull-request state because an open-only query once blocked forever
  after a merge.
- **Why stacked pull requests are refused** — a child merged into an already-squashed parent
  reached nowhere while both read as merged and green.
- **Why force-push, pushes to the default branch and `--admin` are refused even with branch
  protection** — the agent merges its own pull requests, and an owner token can bypass a
  protection: two lines of defence.
- **Why secrets are matched by content too** — downloaded keys are named after account and key
  ids, not after their role; no path rule catches them once renamed.
- **Why PostToolUse reports instead of blocking** — a multi-file edit is inconsistent midway; a
  block tells the model to undo good work.
- **Why a git pre-commit hook as well, silent under `CLAUDECODE=1`** — commits made in a terminal
  or an IDE would otherwise reach CI ungated; Claude's own commits are already gated once.
- **Why the hook tests run with a fake `gh`** — the only GitHub answer a guard had never seen
  was the one that broke it; a broken guard looks exactly like a passing one.
- **Considered and not adopted** — a `WorktreeCreate` hook (it replaces worktree creation, so
  one bug blocks every isolated agent); `permissionDecision: "allow"` for commands judged safe
  (the parser would become a security boundary, which it is not); refusing a formatter (format
  is checked by a gate instead); a blocking PostToolUse; heuristic guards for judgement rules
  (they would cry wolf).

## 3. `Testing.md` — gates, selftests, CI

**Scope** : what each test and selftest covers, the gates and where they are defined, how CI
scopes its jobs. Related : `[[Hooks]]` · `[[ParallelDelivery]]` · `[[Architecture]]`.

### What each test file covers

Une ligne par fichier, jamais un compte (les comptes dérivent). Les fichiers de la stack
viennent du rapport de WP-A (marqueur `<!-- FILL: … -->` si WP-D ne les connaît pas encore). Les
fichiers d'outillage :
- `scripts/selftest/test_check.py` (écrit pour ce projet) : les codes de sortie de
  `scripts/check.sh`, la ligne `SETUP:`, le choix des composants par `--paths-from`, `edit`.
- un `scripts/selftest/test_<script>.py` par script vendorisé — la liste exacte est celle de
  `scripts/lib/VENDORED.json` ; pour chacun, recopier la première ligne de son en-tête ;
- `.claude/skills/<skill>/scripts/test_*.py` : les scripts locaux des skills du projet (la
  sonde de `deploy`, par exemple).

### Gates

- `scripts/check.sh` est **la seule définition des gates** ; ses cibles et qui les appelle :
  `fast --paths-from` (le garde de commit du plugin et `scripts/precommit.py`), `edit` (le hook
  post-édition), `ci <component>` (le job CI du composant), `setup <component>`
  (`scripts/worktree_setup.sh`), `all` (l'humain), `test`. La table par composant réellement
  installée (rapport de WP-A).
- Gates statiques au commit, tests en CI ; un outil absent est un refus (code 3, `SETUP:`),
  jamais un gate sauté ; les drapeaux `<NAME>_REQUIRED=true` des tests qui dépendent d'un
  service.
- `fast --paths-from` choisit les composants avec `scripts/ci_scope.py`, la même table que la
  CI, décrite par les clés `COMPONENT_<ID>_RE` de `tooling.conf` : la documentation seule ne
  lance aucun gate de composant, un chemin inconnu les lance tous, un `ci_scope.py` en échec
  aussi (avec un avertissement). Plus les contrôles d'outillage par chemin (`py_compile`,
  `bash -n`, `wiki_lint.py` pour `.llmwiki/`, `wip.py check` pour `wip/`).

### CI

- Les jobs de `.github/workflows/ci.yml` et leurs `name:` exacts : `Scope` (non requis),
  `Tooling — selftests, wiki, wip` (requis, toujours), un job requis par composant qui n'appelle
  que `scripts/check.sh ci <component>`.
- Le job `tooling`, dans l'ordre : les empreintes des copies vendorisées contre
  `scripts/lib/VENDORED.json` (la CI n'a pas le plugin), `scripts/selftest.sh`,
  `scripts/wiki_lint.py` (sortie 1 sur constat seulement, les `note:` ne font pas échouer),
  `scripts/wip.py check`.
- La mécanique du scope : drapeaux par composant, événements autres que `pull_request` = tout,
  3000 fichiers ou plus = tout, renommages comptés des deux côtés (`previous_filename`) ; la
  condition `if: ${{ !cancelled() && needs.scope.outputs.<c> != 'false' }}` et ses trois
  détails (`!cancelled()`, `!= 'false'`, l'enveloppe `${{ }}`) ; rejouer le scope d'une branche :
  `git diff --name-only origin/<D>...HEAD | scripts/ci_scope.py`.
- Déclencheurs, `concurrency` (les runs de PR remplacés sont annulés, jamais ceux de `<D>`), run
  hebdomadaire complet, caches clés sur les verrous, actions épinglées par SHA.
- Hygiène des dépendances : Dependabot (cadence, groupes, merge manuel par l'orchestrateur),
  l'audit de chaque composant (dans `check.sh ci`) et comment il est épinglé, la politique
  d'ignore (seulement sans correctif, avec expiration et entrée `wip/`) ; *(Complet)*
  `deps.yml`, qui pousse une branche et n'ouvre pas la PR.

### Selftests

- **Une commande** : `scripts/selftest.sh` (vendorisé) lance `python3 -m unittest discover -s
  scripts/selftest`, puis la même chose dans chaque `.claude/skills/*/scripts/`, et échoue si un
  lancement échoue **ou si le total de tests est zéro**.
- **Copies vendorisées** : `scripts/lib/VENDORED.json` liste chaque fichier copié du plugin avec
  son empreinte sha256 et la version du plugin ; la CI les compare ; `SessionStart` signale un
  plugin plus récent ou une copie modifiée ; `/shipyard:sync-tooling` les met à jour par une PR.
  Une copie ne s'édite jamais : un selftest vendorisé qui échoue ici est un défaut du plugin
  (entrée `wip/`, `Area: tooling`), pas un test à corriger sur place — et encore moins à
  assouplir.

### Known gaps

- Les hooks ne sont pas testés dans ce projet (`[[Hooks]]` § Self-test).
- Les parties du lint wiki qui demandent du jugement (contradictions, `Updated:` plus ancien que
  les sources citées) ne sont pas scriptées (`[[Documentation]]` § Lint).
- Ce que les tests de la stack ne couvrent pas encore (rapport de WP-A).
- *(niveau Essentiel)* pas de harnais d'evals : renvoi à l'entrée `wip/todo_nr/` qui l'attend.

### Decisions & History à semer

- **One definition of the gates** — written three times (hook, CI, a sub-folder's instructions)
  they diverged in an earlier project, and a commit green locally turned red in CI.
- **Tests out of the commit** — paid twice per change, and they forced a half-installed worktree
  to install everything to commit a one-line conflict resolution.
- **A missing tool refuses** — a skipped gate is an invisible regression.
- **Selftests with a stubbed `gh`** — GitHub-dependent cases were skipped wherever `gh` was not
  authenticated; the only answer never seen was the one that broke.
- **`selftest.sh` refuses zero tests** — `unittest` does not descend into a folder without
  `__init__.py`: Python 3.9 reports "Ran 0 tests, OK", 3.12 exits 5. A selftest that runs nothing
  passes for green.
- **The scope's catch-all** — getting the scope wrong must cost a slow run, never an untested
  merge: a rule too narrow turns nothing red, it lets through what nothing tested.
- **The scope table is configuration, not code** — `COMPONENT_<ID>_RE` in `tooling.conf`, so
  `ci_scope.py` stays the plugin's generic copy instead of becoming this project's variant.
- **Vendored copies identical to their template, checked in CI** — a copy edited locally would
  never receive another fix; drift is reported, not absorbed.
- **No path filter on a required workflow** — a filtered workflow reports no status, and a
  documentation-only pull request waited forever; scoping is per job.
- **A new check is a step, not a job** — a new job is not required until the protection is
  edited, and a renamed one blocks every open pull request.
- **`Scope` is not required** — required, it adds nothing when it fails (every job runs) and
  blocks everything if it never starts.
- **`!cancelled()` rather than `always()`; `!= 'false'` rather than `== 'true'`.**
- **A vulnerability is ignored only with no fixed release, with an expiry and a `wip/` entry.**
- *(Complet)* **`deps.yml` pushes a branch rather than opening the pull request** — a pull
  request opened with `GITHUB_TOKEN` triggers no workflow, so its required checks never report.

## 4. `ParallelDelivery.md`

**Scope** : how several changes are built at once and reach `<D>` — worktrees, one pull request
per theme, lanes, model routing, serial squash merges, deploy after each merge, cleanup.
Procedure : `/shipyard:ship-parallel`. Related : `[[Hooks]]` · `[[Project]]` ·
`[[Documentation]]` <· `[[Deployment]]` (si cible)> <· `[[Team]]` (équipe)>.

### Protection of the default branch

Les valeurs **attendues** (l'orchestrateur relit la protection après le merge du bootstrap et
ne corrige la page que si la relecture diffère) :

| Setting | Value | Consequence |
|---|---|---|
| repository merge settings | squash only, title = pull request title; `delete_branch_on_merge`; no auto-merge | one commit per pull request on `<D>`; a merged branch reads `[gone]` locally and the commit hook stops you; merges stay the orchestrator's, after reading the diff |
| `strict` | `true` | serial merges: each merge makes the other pull requests stale; update them with `update-branch` |
| required checks | `Tooling — selftests, wiki, wip` + every component job; **not** `Scope` | a failed `Scope` already runs every job; a `Scope` that never starts would block everything |
| `enforce_admins` | `true` | the owner token the agent uses cannot merge a red pull request nor push to `<D>`; an urgent fix goes through a pull request too |
| `required_pull_request_reviews` | `null` <— *(équipe, si choisi)* code-owner reviews, one approval, stale approvals kept> | see § Lanes and `[[Team]]` |
| `required_linear_history` | `true` | squash only |
| `allow_force_pushes` / `allow_deletions` | `false` | shared history is never rewritten |

Si la protection est indisponible (dépôt privé sans offre payante) : le dire ici, dire que les
hooks sont alors **la seule garde** (y compris contre `--admin` et le push direct), et lier
l'entrée `wip/todo_nr/` qui porte la décision.

### Worktrees

- Le checkout principal reste sur `<D>`, avance en fast-forward et ne commite jamais : les
  worktrees partent de lui, le déploiement part de lui, il porte les secrets que `--deploy` lie,
  le nettoyage le juge. Les règles, elles, sont celles de la version du plugin (`[[Hooks]]`).
- Travail dans `<WORKTREE_PREFIX><topic>` (à la main) ou `.claude/worktrees/<name>` (agents).
- `scripts/worktree_setup.sh [DIR] [--no-<component>]… [--deploy]` (vendorisé) : valide ses
  arguments avant d'écrire quoi que ce soit ; écrit le marqueur `<SETUP_MARKER>` (pid, date de
  début, branche) **avant** tout ce qui est lent et le retire à la fin ; lance
  `scripts/check.sh setup <component>` pour chaque composant non exclu ; dernière ligne
  `ready: <tree> (<branch>)`. Un échec laisse le marqueur, exprès, sans `trap`. Un marqueur
  périmé se retire à la main après vérification : `rm <tree>/<SETUP_MARKER>`.
- `--deploy` lie `<DEPLOY_ENV_FILE>` depuis le checkout principal (lien, jamais copie), pour le
  seul worktree de déploiement ; aucun secret par défaut.

### Cleanup

- `scripts/cleanup_local.py [--apply]` (vendorisé) : dry run par défaut, sortie toujours 0, seul
  script qui fetch.
- Une branche est supprimable si elle n'a aucun commit d'avance sur `origin/<D>`, ou si une PR
  mergée existe dont la tête, comparée par GitHub au tip local, est `identical` ou `behind`.
- Les gardes d'un worktree, dans l'ordre — verrou d'une session vivante (pid et heure de
  démarrage), verrou manuel, marqueur de setup, modification depuis moins de
  `CLEANUP_IDLE_MINUTES` minutes, modifications non commitées, HEAD détachée hors de
  `origin/<D>`, règle de branche ; chacune garde aussi la branche. Verrou périmé : supprimé avec
  `-f -f`, et dit. `git branch -D`, parce qu'une branche squash-mergée n'est jamais « mergée »
  pour git.
- **La limite honnête** : aucune garde ne rend `--apply` sûr pendant que des agents travaillent ;
  d'où la règle d'usage : `--apply` seulement une fois que tous les agents ont rendu leur
  rapport.

### Lanes

- Le tableau A/B/C/D de `/shipyard:ship-parallel` §1, avec les classes d'échec silencieux du
  projet (`Project.md` § Risk) et `LANE_C_RE` en clair. « In doubt, the stricter lane. » Rien de
  mécanique n'impose les lanes : c'est l'étape de planification de l'orchestrateur.
- Lanes B et C : critères d'acceptation dans l'entrée **avant** le lancement, revue par un agent
  frais. Lane C : feu vert explicite de l'utilisateur pour chaque merge.
- Filets au moment du merge : `scripts/pr_size.py <n>` (lignes de code ajoutées hors
  `SIZE_EXCLUDE_RE`) au-delà de `SIZE_THRESHOLD` → lane B quoi qu'ait dit le plan ;
  `scripts/lane_paths.py lane-c` sur le diff → lane C.
- L'autonomie (`AUTONOMY`) : ce que `ship-parallel` fait d'une PR verte — merge et déploie,
  merge seulement, ou s'arrête à la PR.
- *(équipe)* Le plan montre, pour chaque PR, les owners des chemins qu'elle touchera
  (`scripts/owners.py`). Une PR qui touche une zone dont l'utilisateur de la session n'est pas
  owner reçoit la demande de revue de GitHub et **ne se merge qu'après l'approbation** d'un owner
  de chaque zone étrangère ; en attendant, les autres PR avancent. Cette approbation tient lieu
  du feu vert de la lane C pour ses chemins. Jamais de contournement.

### Reviewer calibration

Les quatre règles que porte l'agent `shipyard:reviewer` (lanes B et C) :
- vérifier chaque constat contre la **tête** de la PR, pas contre sa description ni un commit
  antérieur ;
- une page wiki, le README ou un document de conformité que le changement rend faux est au
  moins **Medium** — la doc fait partie du changement ;
- lire le `Decisions & History` d'une page avant de déclarer quelque chose redondant ;
- juger les tests contre les **critères d'acceptation** de l'entrée, pas contre la couverture.
Chaque constat va à l'utilisateur avant le merge, quelle que soit sa sévérité, avec l'action
prévue.

### Model routing

| Rating | Agent | Model, effort |
|---|---|---|
| complex — an open design choice, several subsystems, an unknown cause, lane B or C | `shipyard:implementer-complex` | sonnet, high |
| simple — an explicit, local fix with mechanical acceptance | `shipyard:implementer-simple` | sonnet, low |
| bulk — many independent mechanical units | `general-purpose`, one per unit, launched by the orchestrator | haiku |
| review (lanes B, C) | `shipyard:reviewer` | sonnet, high |

- Modèles fixés par le plugin. « In doubt, complex. » Aucun `model` par appel (il écraserait
  celui de la définition, et l'effort n'existe que dans une définition) ; repli
  `general-purpose` + `model: "sonnet"` si les définitions ne sont pas chargées, dit dans le
  rapport. Un projet qui veut d'autres modèles écrit ses propres agents dans `.claude/agents/`
  et les inscrit dans `Project.md` § Agents.
- **Disjoncteur** : trois tentatives sur un même check, puis un rapport classé `TEST_ISSUE`,
  `IMPL_ISSUE`, `DOC_ISSUE` ou `UNCLEAR`, et l'action de l'orchestrateur pour chaque classe
  (`/shipyard:ship-parallel` §2).
- **Capacité** : `CONCURRENCY_CAP` implémenteurs simultanés, `WIP_LIMIT` entrées dans
  `wip/todo/`.

### Merges

- En série, dans l'ordre planifié ; une branche se met à jour en y mergeant `<D>`
  (`gh api -X PUT repos/{owner}/{repo}/pulls/<n>/update-branch`, asynchrone : attendre la
  nouvelle tête), jamais par rebase.
- `gh pr merge <n> --squash --match-head-commit <sha>`, **sans** `--delete-branch` : avec des
  worktrees, `gh` essaie de passer une branche sur `<D>`, déjà prise par le checkout principal,
  et échoue après un merge réussi ; le réglage du dépôt supprime la branche distante, le
  nettoyage la locale.
- Une PR qui touche `.claude/` merge en dernier dans sa vague ; un correctif après merge est une
  nouvelle PR.

### Merged, not deployed

*(si cible)* Après chaque merge, depuis un worktree propre au sha mergé
(`<WORKTREE_PREFIX>deploy`, préparé avec `--deploy`), le skill `deploy`, puis la vérification du
contenu réel. La sonde `.claude/skills/deploy/scripts/probe.sh` est lancée à la planification.
Une session qui ne peut pas déployer écrit **une** entrée `wip/todo/<date>-merged-not-deployed.md`
qui liste les shas : jamais un succès silencieux.

### Measuring delivery

*(Complet)* Seulement si des métriques de livraison sont installées : leurs définitions et une
ligne de **baseline** à mesurer après les 20 premières PR mergées, vide au bootstrap. Sinon, la
section n'existe pas et l'entrée `wip/todo_nr/` qui les attend est liée depuis
`[[KnownLimits]]`.

### Decisions & History à semer

- **Lanes chosen at planning, not after the diff** — a size cap applied afterwards was the only
  brake; a +6 900-line pull request merged and deployed on its first day needed six fix pull
  requests the same day. Size stays a backstop.
- **A fresh reviewer for lanes B and C** — the agent that writes a change also writes the tests
  that judge it, and the Stop hook refuses to let it finish on red: together they reward the
  shortest path to green. A planned review once found a migration that left the database
  unopenable behind six green checks.
- **A three-attempt circuit breaker** — without it, an agent loops on the same failure or
  weakens the assertion.
- **Squash, and updates by merging `<D>` in** — linear history; one commit per theme, revertible
  at once, which the deploy keys on. A rebase needs a force-push that destroys the review history
  and the commits of a worktree an agent still holds.
- **Serial merges, a deploy after each** — `strict` makes merges serial anyway; deploying after
  each merge points a regression at one pull request.
- **One file per `wip/` entry** — a shared `TODO.md` made every pair of pull requests conflict,
  the one conflict parallel work could not avoid. No index file, for the same reason.
- **The main checkout stays on `<D>`** — worktrees and deploys start from it, and a cleanup
  judges against it; asleep on an old branch, it sends new work off a stale base. The rules
  themselves come from the plugin version.
- **Pull requests touching `.claude/` merge last in their wave** — fast-forwarding the main
  checkout changes the settings and project skills under agents still running.
- **Worktree secrets on demand only** — an implementer neither deploys nor signs; what an agent
  can reach is limited to what its task needs.
- **A setup in progress is visible to the cleanup** — a cleanup run from another session deleted
  a worktree and its branch mid-setup: the tree looked clean (everything a setup writes is
  ignored) and the branch had no commit yet. A rule the operator must remember protects nothing;
  hence the marker and the recent-change guard.
- **Merges proved by GitHub's compare** — `git cherry` reports every squash-merged branch as
  unmerged, a local comparison fails on heads never fetched, and `merge-tree` reports old versions
  of rewritten lines; proving twenty stale branches took three attempts before this. Each guard
  keeps the branch too.
- **Size counts added lines of code only** — counting tests made a well-tested pull request
  "bigger" than an untested one, and counting docs and deletions taxed clean-ups.
- **Model routing by a rating made at planning**, visible in the approved plan, rather than an
  implicit router: the rating can be read and challenged. Models are fixed by the plugin, so
  every project routes the same way; a project that needs otherwise defines its own agents.
- **`enforce_admins: true`** — two lines of defence, the hooks on the agent's side and the
  server on GitHub's; in an earlier project it was off, and the hooks alone refused `--admin` and
  direct pushes.
- **Protection applied after the bootstrap merge**, its contexts copied from the checks that
  actually reported — a misspelt context is a required check that never reports.
- **No required approval** — a solo developer cannot approve their own pull request; the
  independent review is an agent. *(équipe)* Owner approval is a process run by `ship-parallel`,
  not a branch rule, unless every area has several owners (`[[Team]]`).
- **No `--delete-branch` on merge** — with worktrees it fails after a successful merge.
- *(si cible)* **"Merged, not deployed" is never silent** — a session without access to the
  target merged five pull requests and ended as if all was well; production ran five-day-old
  code until a real client hit a missing endpoint. Hence the probe at planning, which tests the
  deploy's own routes rather than the public URL, and the `wip/todo/` entry naming the shas.

## 5. Compléments pour d'autres pages

### `Security.md`

- **Secrets détectés par chemin et par contenu** : `SECRET_PATH_RE` / `SECRET_ALLOW_RE` et
  `SECRET_CONTENT_RE` (`tooling.conf`), appliqués au commit de Claude par le garde du plugin et
  au commit humain par `scripts/precommit.py` ; fichiers de 1 Mo au plus, non binaires ; les
  motifs courts sont bornés à gauche, pour qu'un slug en kebab-case ne passe pas pour une clé ;
  le message nomme le chemin et le type de motif, jamais la valeur ; le marqueur
  `secret-scan: fixture` pour une fausse clé de test. Remède : désindexer, déplacer la valeur
  dans un fichier non suivi, et la **révoquer** si elle a déjà été poussée.
- Les secrets ne sont liés dans un worktree que par `scripts/worktree_setup.sh --deploy`.
- Audit des dépendances : dans `scripts/check.sh ci <component>` ; ignores seulement sans
  correctif publié, avec expiration et entrée `wip/` ; les alertes Dependabot ne font échouer
  aucun build.
- Graines : **matched by content too** (`[[Hooks]]`) ; **short patterns left-bounded** — task
  names and `wip/` slugs in kebab-case looked like keys ; **secrets on demand only**
  (`[[ParallelDelivery]]` § Worktrees).

### `Deployment.md`

*(si cible)* La topologie en une ligne, sans hôte ; ce qu'un merge déploie (`DEPLOY_PATHS_RE` en
clair, vérifié par `scripts/lane_paths.py deploy`) ; le skill `deploy` et sa sonde ; le rollback
en une commande ; les migrations de données qui ne reviennent pas avec le code (restaurer la
sauvegarde prise avant) ; « merged, not deployed ». Jamais d'hôte, d'URL ni de chemin réel.
Graines : principes 5.2 à 5.4 de l'annexe 01, et le « health check that answered ok for two days
while every real request failed ».

### `Documentation.md`

- § Budgets : `CLAUDE_MD_BUDGET` et `WIKI_PAGE_BUDGET` en clair ; ce qui reste dans `CLAUDE.md`
  (ce dont chaque session a besoin) et ce qui part au wiki. Graine : « A budget, because every
  incident tends to become a rule and none gets removed; the pruning pass is where rules
  leave. »
- Le reste de la page : annexe 06 §3.

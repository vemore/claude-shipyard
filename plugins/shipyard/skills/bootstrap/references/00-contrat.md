# Annexe 0 — Contrat d'un projet shipyard

> Lu par l'orchestrateur **et par chaque lot (WP)** avant d'écrire une ligne. C'est ce qui
> permet à plusieurs agents d'écrire en même temps des fichiers qui s'appellent les uns les
> autres sans se contredire : les noms, les signatures et les codes de sortie sont fixés ici,
> une fois. Un lot qui a besoin d'une interface absente d'ici le dit dans son rapport au lieu
> de l'inventer. Le contrat du plugin lui-même (ce qui vit dans le plugin, ce qui est
> vendorisé) est `docs/contrat-plugin.md` du dépôt `claude-shipyard`.

## 1. Les fichiers qui portent les valeurs

L'orchestrateur les écrit **avant** le fan-out ; aucun lot ne les modifie (un lot qui trouve
une valeur fausse le signale).

| Fichier | Contenu | Lu par |
|---|---|---|
| `scripts/lib/tooling.conf` | Valeurs machine, une par ligne `CLE=valeur` (§2) | hooks du plugin, scripts vendorisés, CI, skills |
| `.llmwiki/Project.md` | Les décisions du questionnaire, en prose, avec leur raison (annexe 02 §6) | tous les agents, à chaque tâche |
| `.claude/settings.json` | Activation du plugin au niveau du projet, marketplace, permissions (annexe 03 §2) | Claude Code |
| `.github/CODEOWNERS` | En équipe : qui possède quels chemins (`/shipyard:join` le tient ensuite) | `scripts/owners.py`, GitHub, hooks, `ship-parallel` |

**Pourquoi un fichier de configuration unique.** Dans un projet antérieur, le nom du marqueur
de setup, la regex d'exclusion du comptage de taille et la liste des gates vivaient chacun dans
deux ou trois fichiers, gardés synchrones par des selftests qui grepaient les autres fichiers.
Une seule source supprime cette classe de dérive au lieu de la surveiller — et c'est ce qui
permet au code du plugin d'être le même pour tous les projets.

## 2. `scripts/lib/tooling.conf`

Format : `CLE=valeur` ou `CLE='valeur avec espaces ou métacaractères'`, commentaires `#` sur
leur propre ligne (jamais en fin de ligne : le shell le retire, le lecteur Python le garderait
dans la valeur), pas d'interpolation, pas d'`export`. **Chaque clé est précédée d'une ligne de
commentaire** qui dit son sens : le projet ne contient pas cette annexe, c'est donc
`tooling.conf` qui se documente lui-même. Toute regex (`*_RE`) est évaluée par le module `re`
de Python.

Exemple complet (valeurs par défaut ; l'orchestrateur remplace ce qui vient du questionnaire) :

```sh
# scripts/lib/tooling.conf — single source for the values shared by the shipyard hooks,
# the vendored scripts, CI and skills. Written at bootstrap from .llmwiki/Project.md.
# Change a value here, never a copy elsewhere. One comment line per key, no trailing comments.
# Project slug, prefix of every local name.
PROJECT_SLUG=acme-api
# The only protected branch.
DEFAULT_BRANCH=main
# Namespace of the project's git config keys (<ns>.allowStackedPr, <ns>.deliveryAcknowledged — user-only).
GIT_CONFIG_NS=acme-api
# Marker written by scripts/worktree_setup.sh while it runs; cleanup_local.py keeps such a worktree.
SETUP_MARKER=.acme-api-setup-in-progress
# Once-a-day stamp of the scheduled-workflow check (complet level).
SCHEDULED_STAMP=.acme-api-scheduled-check
# Manual worktrees live at <prefix><topic>.
WORKTREE_PREFIX=../acme-api-
# Stack components, in CI job order.
COMPONENTS='api web'
# Paths of each component (COMPONENT_<ID>_RE, ID upper-cased, '-' -> '_').
COMPONENT_API_RE='^api/|^pyproject\.toml$|^uv\.lock$'
COMPONENT_WEB_RE='^web/|^package\.json$|^package-lock\.json$'
# solo or team (team: CODEOWNERS and /shipyard:join).
TEAM_MODE=solo
# What Claude does with a green pull request: merge-deploy, merge or pr.
AUTONOMY=merge-deploy
# continuous (the default branch is production) or planned (tagged releases).
RELEASE_MODE=continuous
# Added or modified lines of code above which a pull request is lane B.
SIZE_THRESHOLD=1500
# Paths not counted by pr_size.py: docs, wip, wiki, tests, locks, generated, snapshots.
SIZE_EXCLUDE_RE='\.md$|^wip/|^\.llmwiki/|^docs/|(^|/)tests?/|(^|/)__snapshots__/|\.lock$|-lock\.json$|\.snap$|^generated/'
# Sensitive paths: a diff touching one is lane C. Empty: no lane C.
LANE_C_RE='^api/auth/|^migrations/|PRIVACY\.md$'
# What a merge deploys. Empty: nothing is deployed.
DEPLOY_PATHS_RE='^api/|^web/'
# Untracked file holding the deploy targets; linked only by worktree_setup.sh --deploy. Empty: no deploy.
DEPLOY_ENV_FILE=deploy.env
# Paths refused at commit (always includes DEPLOY_ENV_FILE), and their template exceptions.
SECRET_PATH_RE='(^|/)\.env$|(^|/)\.env\.|\.pem$|\.key$|\.p12$|\.pfx$|\.jks$|\.keystore$|(^|/)id_(rsa|ed25519|ecdsa)$|(^|/)deploy\.env$'
SECRET_ALLOW_RE='\.example$|\.template$|\.sample$'
# Content refused in any committed file; short patterns are left-bounded so kebab-case words pass.
SECRET_CONTENT_RE='-----BEGIN [A-Z ]*PRIVATE KEY-----|"type"[ \t]*:[ \t]*"service_account"|AKIA[0-9A-Z]{16}|ghp_[A-Za-z0-9]{36}|github_pat_[A-Za-z0-9_]{22,}|xox[baprs]-[A-Za-z0-9-]{10,}|(?<![A-Za-z0-9_-])sk-[A-Za-z0-9_-]{20,}'
# Max entries in wip/todo/.
WIP_LIMIT=12
# Size of wip/todo_nr/ above which a refinement pass is proposed.
REFINE_THRESHOLD=30
# An entry with no commit for this many days is flagged stale.
STALE_DAYS=60
# More open entries than this on one theme: candidates for merging.
CROWDED_THEME=4
# Max lines of a wiki page, and of CLAUDE.md.
WIKI_PAGE_BUDGET=400
CLAUDE_MD_BUDGET=120
# A worktree modified more recently than this is kept by cleanup (0 disables this guard).
CLEANUP_IDLE_MINUTES=30
# Roots whose backticked paths the lints check (include every component directory).
DEAD_PATH_ROOTS='api|web|tests|scripts|docs|\.claude|\.llmwiki|\.github|wip'
# Max implementer agents at once.
CONCURRENCY_CAP=4
# Pruning pass cadence in continuous delivery: every N merged pull requests.
PRUNE_EVERY_MERGES=30
# essentiel (complet: metrics, cron check, evals — not shipped by shipyard 0.1).
TOOLING_LEVEL=essentiel
```

| Clé | Sens et règle |
|---|---|
| `COMPONENTS`, `COMPONENT_<ID>_RE` | les composants et leurs chemins ; `ci_scope.py` (donc la CI et `check.sh fast`) n'a pas d'autre table : un chemin qu'aucune regex ne couvre et qui n'est pas de la documentation lance **tous** les composants |
| `TEAM_MODE` | `team` : `.github/CODEOWNERS` et `.llmwiki/Team.md` existent, les hooks rappellent `/shipyard:join` à qui n'est pas owner, `ship-parallel` attend l'owner d'une zone étrangère |
| `AUTONOMY` | `merge-deploy` · `merge` · `pr` ; avec `DEPLOY_PATHS_RE` vide, `merge-deploy` équivaut à `merge` |
| `RELEASE_MODE` | `planned` : skill `release` du projet, élagage avant chaque release ; `continuous` : élagage toutes les `PRUNE_EVERY_MERGES` PR |
| `SECRET_PATH_RE` | inclut toujours le nom de `DEPLOY_ENV_FILE` |
| `DEAD_PATH_ROOTS` | inclut le répertoire de chaque composant |
| `TOOLING_LEVEL` | `essentiel` seulement en shipyard 0.1 ; les éléments du niveau complet deviennent des entrées `wip/todo_nr/` |
| les autres | sens donné par leur ligne de commentaire ci-dessus |

Ajouter une clé au bootstrap = la documenter ici d'abord ; plus tard, dans le projet, = la
commenter dans `tooling.conf` et la citer dans `.llmwiki/Project.md`.

## 3. Arborescence cible et propriété des fichiers

Un fichier a **un seul** propriétaire. Un lot n'écrit jamais hors de sa ligne ; s'il a besoin
d'une ligne ailleurs (un `.gitignore`, une entrée de README, une entrée `wip/`), il la décrit
dans son rapport et l'orchestrateur l'écrit à l'intégration.

| Chemin | Propriétaire |
|---|---|
| `.gitignore`, `LICENSE`, `scripts/lib/tooling.conf`, `.llmwiki/Project.md`, `.claude/settings.json`, `.github/CODEOWNERS` | orchestrateur (avant le fan-out) |
| les fichiers listés dans `scripts/lib/VENDORED.json` (scripts de §4, `scripts/selftest/test_*.py` vendorisés, `.githooks/pre-commit`) | **personne** : copiés par `bin/vendor.py`, jamais édités à la main |
| code de la stack (`src/`, `tests/`, manifestes, verrous, configs de lint/format/types), `scripts/check.sh`, `scripts/selftest/test_check.py`, `.env.example` | **WP-A** stack |
| `CLAUDE.md` (racine **et** de composant, même dans un dossier de WP-A), `README.md`, `.llmwiki/**` sauf `Project.md`, `wip/**`, `.claude/rules/**` | **WP-D** connaissance |
| `.github/**` sauf `CODEOWNERS` | **WP-F** CI |
| `.claude/skills/{deploy,release}/**`, `<DEPLOY_ENV_FILE>.example` (seulement s'il y a une cible ou des releases planifiées) | **WP-E** skills de projet |

## 4. Interfaces des scripts

Tous : exécutables, `--help` qui imprime l'usage et le pourquoi, chargent
`scripts/lib/tooling.conf` à la racine du dépôt où ils s'exécutent
(`git rev-parse --show-toplevel`), messages en anglais, aucun accès réseau sauf mention.
**Code 2 = erreur d'usage ou de configuration**, pour tous ; un appelant traite tout code non
prévu comme un échec (le hook de commit : comme un refus).

**Écrit par WP-A** (propre à la stack ; spécification : annexe 05) :

| Script | Signature | Sortie | Codes |
|---|---|---|---|
| `scripts/check.sh` | `fast [--paths-from FILE]` | gates statiques rapides des composants touchés (choisis par `scripts/ci_scope.py`) ; sans `--paths-from`, tous | 0 vert · 1 un gate échoue (40 dernières lignes + « Reproduce with: ») · 3 outil absent : dernière ligne stderr `SETUP: <commande>` |
| | `test [COMPONENT]` · `all` · `ci COMPONENT` · `setup COMPONENT` | tests ; tout ; exactement le job CI du composant ; installation verrouillée et codegen | 0 / 1 / 3 |
| | `edit FILE` | contrôle rapide d'un fichier, rapport seulement | 0 rien · 1 rapport sur stdout |

**Vendorisés par le plugin** (comportement : annexe 04 ; en cas de doute, le code de la copie fait foi) :

| Script | Signature | Sortie | Codes |
|---|---|---|---|
| `scripts/worktree_setup.sh` | `[DIR] [--no-<component>]… [--deploy]`, ordre libre | `check.sh setup` par composant ; marqueur `SETUP_MARKER` pendant ; `--deploy` lie `DEPLOY_ENV_FILE` | dernière ligne `ready: <tree> (<branch>)` ; ≠ 0 laisse le marqueur exprès |
| `scripts/cleanup_local.py` | `[--apply]` | `keep … — <raison>`, `would remove …`, `removed …`, `FAILED …` | toujours 0 |
| `scripts/ci_scope.py` | chemins sur stdin | `<component>=true\|false`, une ligne par composant | 0 ; 2 conf illisible |
| `scripts/pr_size.py` | `<n>` ou `-` | lignes de code ajoutées hors `SIZE_EXCLUDE_RE` | 0 ; 2 `gh` indisponible |
| `scripts/wip.py` | `list\|themes\|check\|refine [todo\|todo_nr\|done\|all]` | annexe 06 §5 | `check` : 0 / 1 ; autres : 0 |
| `scripts/wiki_lint.py` | `[WIKI_DIR]` | constats `page[:ligne]: …`, remarques `note: …` | 0 aucun constat · 1 constats · 2 pas d'`INDEX.md` |
| `scripts/lane_paths.py` | `lane-c\|deploy`, un chemin par ligne sur stdin | les chemins qui correspondent | 0 un au moins · 1 aucun · 2 conf illisible |
| `scripts/owners.py` | `[--who LOGIN]`, chemins sur stdin | `chemin<TAB>@owner …` ; avec `--who`, les motifs de LOGIN | 0 ; 1 LOGIN ne possède rien ; 2 pas de CODEOWNERS |
| `scripts/precommit.py` | — (`.githooks/pre-commit`) | secrets + `check.sh fast` sur l'index | 0 · 1 refus ; 0 tout de suite si `CLAUDECODE=1` |
| `scripts/selftest.sh` | — | tous les selftests du projet ; échec si zéro test | 0 · 1 |

**Écrit par WP-E** (s'il existe) : `.claude/skills/deploy/scripts/probe.sh` — une ligne
`deploy: reachable` ou `deploy: <raison>`, n'imprime **jamais** d'hôte ; 0 joignable · 1 sinon.

## 5. Ce qui vient du plugin

Rien de ce qui suit ne s'écrit dans le projet ; le projet l'active par `.claude/settings.json`.

| Élément | Nom | Rôle |
|---|---|---|
| Hooks | `SessionStart`, `PreToolUse(Bash)`, `PostToolUse(Edit\|Write\|MultiEdit)`, `Stop`, `SubagentStop` | état de branche, rappels (version vendorisée, `/shipyard:join`), refus et gates au commit, PR verte obligatoire — détail : annexe 04 |
| Agents | `shipyard:implementer-simple` (Sonnet, effort low), `shipyard:implementer-complex` (Sonnet, effort high), `shipyard:reviewer` (Sonnet, effort high) | lancés par `ship-parallel` ; le volume reste `general-purpose` + Haiku |
| Skills | `/shipyard:ship-parallel`, `/shipyard:wip-refine`, `/shipyard:join`, `/shipyard:sync-tooling` | livraison, backlog, équipe, mise à jour des copies |

Les skills lisent `tooling.conf` et `Project.md` au début de chaque exécution : un projet
règle leur comportement par ses valeurs, jamais en éditant le plugin. Un projet qui veut
d'autres modèles définit ses agents dans `.claude/agents/` et le dit dans `Project.md`.

## 6. CI (WP-F)

| Job id | `name:` (= contexte du check requis) | Requis | Quand |
|---|---|---|---|
| `scope` | `Scope` | **non** | toujours ; drapeaux via `scripts/ci_scope.py` |
| `tooling` | `Tooling — selftests, wiki, wip` | oui | **toujours** : `scripts/selftest.sh`, `wiki_lint.py`, `wip.py check`, empreintes de `VENDORED.json` |
| `<component>` pour chaque id de `COMPONENTS` | `<Component> — <ce qu'il vérifie>` | oui | `if: ${{ !cancelled() && needs.scope.outputs.<component> != 'false' }}` |

Le job d'un composant appelle `scripts/check.sh ci <component>` et rien d'autre. Les noms
exacts sont écrits dans `.llmwiki/Project.md` par l'orchestrateur ; WP-F les recopie,
l'orchestrateur les donne à la protection de branche.

## 7. Nommage

- Branches : `<type>/<topic>` avec `type` ∈ `feat fix refactor docs chore` ; créées
  `--no-track` puis poussées avec `-u` ; worktrees d'agents sous `.claude/worktrees/`, manuels
  sous `WORKTREE_PREFIX<topic>`.
- Commits : Conventional Commits, `<type>: <sujet>` ; PR squash-mergée sous ce même titre.
- Entrées `wip/` : `wip/<dossier>/YYYY-MM-DD-<slug>.md`, nom définitif dès la création.
- Pages wiki : `.llmwiki/<PascalCase>.md`, lien `[[PascalCase]]`.
- Skills de projet : `.claude/skills/<kebab-case>/SKILL.md`.
- Langue : la doc (CLAUDE.md, wiki, wip, skills de projet, README) dans la langue choisie au
  questionnaire ; messages des scripts, noms de fichiers, identifiants et commits en anglais.

## 8. Règles d'écriture (scripts écrits par le projet)

- **Python 3.9+, bibliothèque standard seulement** pour toute logique non triviale ; shell
  réservé aux enveloppes et à ce qui lance les outils de la stack. Raison : pas de `jq`, pas de
  `date -d` ni de `timeout` GNU, absents de macOS.
- Shell : `#!/usr/bin/env bash`, `set -uo pipefail`, compatible bash 3.2 (pas de tableau
  associatif, pas de `mapfile`).
- Toute lecture réseau sous délai, muette en cas d'échec.
- Une fausse clé de test porte `secret-scan: fixture` dans ses cinq premières lignes : c'est la
  seule façon de commiter un contenu qui correspond à `SECRET_CONTENT_RE`.
- Chaque script porte en tête : usage, ce qu'il garantit, ce qu'il ne couvre pas, et pourquoi
  il existe.

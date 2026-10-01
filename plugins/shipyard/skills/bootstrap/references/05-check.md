# Annexe 5 — `scripts/check.sh` et les scripts écrits par le projet

> Lue par **WP-A**, qui écrit `scripts/check.sh` et `scripts/selftest/test_check.py`. Ce sont
> les seuls scripts de process propres au projet : les autres (`ci_scope.py`, `worktree_setup.sh`,
> `cleanup_local.py`, `pr_size.py`, `wiki_lint.py`, `wip.py`, `lane_paths.py`, `owners.py`,
> `precommit.py`, `selftest.sh`, `lib/conf.py`, `lib/dead_paths.py`) sont **vendorisés** depuis le
> plugin avant le fan-out, listés dans `scripts/lib/VENDORED.json`, et ne s'éditent jamais. Les
> noms, signatures et codes de sortie viennent de l'annexe 00 §4 ; cette annexe dit *ce que
> `check.sh` fait, dans quels cas limites, et pourquoi*. Ce que le wiki en dit : annexe 04 §3.

## 1. Règles des scripts écrits par le projet

Elles valent pour `check.sh`, pour son selftest, et pour tout script que le projet ajoutera
plus tard (dans `scripts/` ou sous `.claude/skills/<skill>/scripts/`).

- **Python 3.9+, bibliothèque standard seulement** pour tout script de logique ; shell seulement
  pour ce qui lance les outils de la stack (`check.sh`). Pourquoi : pas de `jq`, pas de `date -d`
  ni de `timeout` GNU, absents de macOS ; un script qui casse sur une dépendance absente fait
  taire le garde-fou qu'il alimente.
- **Racine et configuration.** Chaque script trouve sa racine par
  `git rev-parse --show-toplevel` dans le répertoire courant (donc la racine du *worktree*, pas
  du checkout principal) et lit `scripts/lib/tooling.conf` de cette racine. En shell :
  `. scripts/lib/tooling.conf`. En Python : importer le lecteur vendorisé plutôt que d'en écrire
  un autre —
  `sys.path.insert(0, os.path.join(<racine>, "scripts", "lib"))`, `import conf`,
  `cfg = conf.load_conf(conf.repo_root())`. Une clé absente est une erreur explicite
  (`missing key X in scripts/lib/tooling.conf`), jamais une valeur par défaut silencieuse : un
  défaut caché est exactement la dérive que le fichier unique supprime.
- **Codes de sortie.** **2 = erreur d'usage ou de configuration**, pour tous (`tooling.conf`
  absent, clé manquante, argument inconnu). Un appelant traite tout code non prévu comme un échec.
- **En-tête et `--help`.** Chaque script commence par un commentaire anglais : usage, ce qu'il
  garantit, ce qu'il ne couvre pas, pourquoi il existe (une ou deux phrases). `--help` l'imprime.
  Messages en anglais.
- **Réseau.** Aucun accès sauf mention dans l'en-tête ; tout appel externe passe par
  `subprocess.run(..., timeout=N, capture_output=True, text=True)` ; un délai dépassé ou un `gh`
  non authentifié dégrade la sortie, ne la fait pas planter.
- **Jamais un nom de script vendorisé**, et jamais une modification d'une copie vendorisée : un
  besoin qu'elle ne couvre pas est une clé de `tooling.conf` ou une entrée `wip/`
  (`Area: tooling`). `bin/vendor.py` ne touche à aucun fichier qu'il ne liste pas : `check.sh`,
  `test_check.py` et les scripts du projet sont à l'abri d'une synchronisation.
- **Selftests.** Un fichier `test_<script>.py` (`unittest` stdlib) par script, piloté par des
  tables de cas, dans un bac à sable `tempfile.mkdtemp()` (dépôt + remote nu `git init --bare`),
  `gh` bouchonné par un exécutable placé en tête de `PATH`. Les bacs à sable fixent
  `GIT_AUTHOR_NAME/EMAIL`, `GIT_COMMITTER_NAME/EMAIL`, `GIT_CONFIG_GLOBAL=/dev/null` et
  `GIT_CONFIG_NOSYSTEM=1` : un test qui hérite de la config de l'utilisateur (signature GPG,
  `init.defaultBranch`, hooks globaux) n'est pas reproductible. Ils se lancent par une seule
  commande, `scripts/selftest.sh` (vendorisé), que la CI exécute à chaque push.

## 2. `scripts/check.sh` — la seule définition des gates

**Pourquoi.** Dans un projet antérieur, les gates étaient écrits trois fois : dans le hook de
commit, dans le YAML de la CI et dans un CLAUDE.md de sous-dossier. Ils ont divergé, et un commit
vert localement devenait rouge en CI. Ici, une commande, un endroit à modifier :

| Appelant | Commande |
|---|---|
| le garde de commit du plugin (commits de Claude) | `scripts/check.sh fast --paths-from <fichier>` |
| `scripts/precommit.py` vendorisé (commits humains, via `.githooks/pre-commit`) | `scripts/check.sh fast --paths-from <fichier>` |
| le hook post-édition du plugin | `scripts/check.sh edit <fichier>` |
| le job CI d'un composant | `scripts/check.sh ci <component>` |
| `scripts/worktree_setup.sh` vendorisé | `scripts/check.sh setup <component>` |
| l'humain | `scripts/check.sh all` |

Les hooks du plugin appellent la copie **du dépôt jugé** : une branche qui change ses gates est
jugée sur ses propres gates. C'est aussi là que vont les règles de contenu propres au projet
(fichiers générés à jour, clés de traduction cohérentes…) : le garde du plugin reste générique
et ne connaît que cette interface.

**Cibles** (annexe 00 §4) :

| Cible | Fait | Codes |
|---|---|---|
| `fast [--paths-from FILE]` | gates **statiques** (lint, format `--check`, types) des composants que les chemins touchent, plus les contrôles d'outillage (ci-dessous) ; sans `--paths-from` : tous les composants | 0 / 1 / 3 |
| `test [COMPONENT]` | suites de tests d'un composant ou de tous | 0 / 1 / 3 |
| `all` | `fast` puis `test`, tout | 0 / 1 / 3 |
| `edit FILE` | contrôle d'un seul fichier, < 5 s, **rapport seulement** | 0 rien · 1 rapport sur stdout |
| `ci COMPONENT` | exactement le contenu du job CI : installation verrouillée, `fast`, `test`, build/packaging, audit de dépendances | 0 / 1 / 3 |
| `setup COMPONENT` | installe les dépendances (verrou exact) et lance la génération de code du composant | 0 / 1 / 3 |

Plus `--help` (0) et toute erreur d'usage ou de configuration (2).

**Quels composants pour `fast --paths-from`.** Le fichier contient un chemin par ligne. Le
script les passe à `python3 scripts/ci_scope.py` (vendorisé) et lance les gates des composants
marqués `true`. `ci_scope.py` ne contient aucune table en dur : chaque composant y est décrit par
sa clé `COMPONENT_<ID>_RE` de `tooling.conf` (`<ID>` = l'id de `COMPONENTS` en majuscules, `-`
→ `_`) ; la documentation seule (`\.md$`, `^wip/`, `^\.llmwiki/`, `^docs/`) ne lance rien, et
tout autre chemin lance tout (fourre-tout). Ainsi le commit vérifie exactement les composants
dont la CI tournera, et `check.sh` n'a pas de table chemins → composants à lui. Si
`ci_scope.py` est absent ou échoue, `fast` lance **tous** les composants, avec un avertissement
sur stderr : un sur-ensemble coûte des secondes, un gate sauté est une régression invisible.

**Contrôles d'outillage de `fast`**, décidés par chemin, indépendamment des composants
(quelques secondes au total) :
- un `*.py` sous `scripts/` ou `.claude/skills/*/scripts/` → `python3 -m py_compile` sur ces
  fichiers ;
- un `*.sh` sous `scripts/` ou `.claude/` → `bash -n` sur ces fichiers ;
- un chemin sous `.llmwiki/` → `python3 scripts/wiki_lint.py` (sortie 1 sur constat seulement ;
  ses lignes `note:` — lien pendant, bloc `Outdated`/`Contradicted` — ne bloquent pas) ;
- un chemin sous `wip/` → `python3 scripts/wip.py check`.
Pourquoi : ces deux derniers bloquent le job `tooling` en CI ; les lancer au commit évite une PR
rouge pour une date d'`Updated:` oubliée. Les selftests, eux, restent en CI (ce sont des tests).

**Sortie et codes.**
- Chaque gate est lancé, sa sortie capturée. En échec : les 40 dernières lignes, puis
  `Reproduce with: <commande exacte>` ; le script continue les autres gates pour tout rapporter
  en une fois, puis sort en 1.
- Outil absent (`command -v` échoue, ou l'environnement du composant n'est pas installé — pas
  de `.venv`, pas de `node_modules`) : message `<tool> is not installed for <component>`, et en
  **dernière ligne de stderr** `SETUP: <commande d'installation>` (typiquement
  `scripts/worktree_setup.sh` ou `scripts/check.sh setup <component>`), sortie 3. Jamais un gate
  sauté en silence : un gate sauté est une régression invisible. Si un outil manque *et* qu'un
  autre gate échoue, sortie 3 (il faut d'abord installer pour savoir). Le garde du plugin
  transforme ce code en refus qui cite la ligne `SETUP:`.
- `edit FILE` : si l'outil manque, sortie 0 sans rien dire (le hook post-édition est un confort,
  la garantie est au commit).

**Structure du script** (gabarit à adapter, anglais) :

```bash
#!/usr/bin/env bash
# scripts/check.sh — the single definition of every quality gate.
# Used by the commit gates (fast --paths-from), by CI (ci <component>) and by humans (all).
# Fast = static checks only (seconds); tests run in CI and in `test`/`all`.
# Exit: 0 green, 1 a gate failed, 3 a tool is missing (last stderr line: "SETUP: <cmd>"),
#       2 usage or configuration error.
set -uo pipefail
ROOT=$(git rev-parse --show-toplevel) || exit 2
cd "$ROOT" || exit 2
[ -f scripts/lib/tooling.conf ] || { echo "check.sh: missing scripts/lib/tooling.conf" >&2; exit 2; }
. scripts/lib/tooling.conf

status=0                       # 0, 1 or 3; 3 wins over 1
setup_hint=""
run_gate() {                   # run_gate <component> <cmd...>
  local comp=$1; shift
  local out; out=$("$@" 2>&1); local rc=$?
  if [ $rc -ne 0 ]; then
    printf '%s\n' "$out" | tail -n 40 >&2
    printf 'FAILED (%s): %s\nReproduce with: %s\n' "$comp" "$*" "$*" >&2
    [ $status -eq 3 ] || status=1
  fi
}
need() {                       # need <component> <tool> <setup command>
  command -v "$2" >/dev/null 2>&1 && return 0
  printf '%s is not installed for %s\n' "$2" "$1" >&2
  status=3; setup_hint=$3; return 1
}
# One block per component id of COMPONENTS: fast_<id>, test_<id>, setup_<id>, ci_<id>.
fast_api()  { need api uv "scripts/check.sh setup api" || return
              [ -d api/.venv ] || { need api api/.venv "scripts/check.sh setup api"; return; }
              run_gate api uv run --no-sync ruff check api
              run_gate api uv run --no-sync ruff format --check api
              run_gate api uv run --no-sync mypy api; }
# ... test_api, setup_api, ci_api; then the dispatcher on "$1" ...
# fast --paths-from: python3 scripts/ci_scope.py < FILE  ->  "<id>=true|false" lines
# At exit: [ -n "$setup_hint" ] && printf 'SETUP: %s\n' "$setup_hint" >&2; exit $status
```

Exemples par écosystème (lignes `fast` / `test` / `setup` ; choisir selon les outils retenus au
questionnaire, préférer la variante qui lit le verrou sans le modifier) :

| Écosystème | `fast` (statique) | `test` | `setup` |
|---|---|---|---|
| Python (uv) | `uv run --no-sync ruff check <dirs>` · `uv run --no-sync ruff format --check <dirs>` · `uv run --no-sync mypy <pkg>` (ou `pyright`) — `.venv` absent → code 3 | `uv run --no-sync pytest -q` | `uv sync --locked` |
| Node / TS (npm) | `npx --no-install eslint .` · `npx --no-install prettier --check .` · `npx --no-install tsc --noEmit` | `npm test` (vitest/jest, mode non interactif : `vitest run`) | `npm ci` (pnpm : `pnpm install --frozen-lockfile`) |
| Go | `test -z "$(gofmt -l .)"` · `go vet ./...` · `staticcheck ./...` | `go test ./...` | `go mod download` |
| Rust | `cargo fmt --check` · `cargo clippy --locked --all-targets -- -D warnings` | `cargo test --locked` | `cargo fetch --locked` |
| JVM (Gradle) | `./gradlew --offline spotlessCheck` (ou `checkstyleMain`) · `./gradlew compileJava` | `./gradlew test` | `./gradlew --no-daemon dependencies` |
| JVM (Maven) | `mvn -q -o spotless:check` · `mvn -q -o compile` | `mvn -q test` | `mvn -q dependency:go-offline` |
| Site statique / docs | lien interne et build sans réseau (`<générateur> build --strict`) | — | installation du générateur |

Pourquoi `uv run --no-sync` : `uv run` seul synchronise l'environnement avant de lancer l'outil,
donc installe ou modifie en silence pendant un gate qui ne doit que vérifier ; `--no-sync` fait
d'un `.venv` absent un outil manquant (code 3), qui dit quoi installer.

Règles :
- **Les outils de la stack ne visent que les dossiers de leur composant** (`ruff check src tests`,
  pas `ruff check .`), dans `check.sh` comme dans la configuration (`include`, `files`). Le
  dépôt contient aussi les scripts de l'outillage, écrits pour Python 3.9 et contrôlés par
  `py_compile` : un linter de la stack réglé sur une version plus récente les casserait, et un
  formateur qui les réécrirait les ferait diverger de leur empreinte dans
  `scripts/lib/VENDORED.json` — la CI les refuserait. Certains formateurs réécrivent aussi le
  Markdown du wiki.
- **`fast` reste statique et rapide** (cible : < 30 s à chaud). Pourquoi : les tests au commit
  étaient payés deux fois par changement (au commit puis en CI) et forçaient un worktree à moitié
  installé à tout installer pour résoudre un conflit d'une ligne. La CI les exécute, et le hook
  `Stop` du plugin refuse de finir un tour sur une PR rouge, donc rien n'est livré rouge.
- **Le formatage est vérifié (`--check`), jamais imposé par un refus de lancer le formateur** :
  le formateur est sûr à lancer ; c'est du code non formaté qu'on refuse.
- `ci <component>` n'utilise que des installations verrouillées (`--locked`, `npm ci`,
  `--frozen-lockfile`) : un verrou désynchronisé doit rendre la CI rouge, pas être réparé en
  silence. Il lance aussi l'audit de dépendances du composant (`Project.md` § Components ;
  annexe 08 §5).
- Un test qui se saute quand une variable d'environnement manque (service externe, conteneur)
  reçoit un drapeau `<NAME>_REQUIRED=true` positionné par `ci <component>` : en CI il échoue au
  lieu de passer vert sans avoir rien exécuté.

**Selftest de `check.sh`** (`scripts/selftest/test_check.py`, WP-A) : dans un dépôt bac à sable
avec des outils bouchonnés sur `PATH` et un `scripts/lib/tooling.conf` de test, un gate qui
échoue → 1 avec « Reproduce with: » ; outil absent → 3 et `SETUP:` en dernière ligne de stderr ;
outil absent + gate rouge → 3 ; `--paths-from` documentation seule → aucun gate de composant ;
un chemin d'un composant → ses seuls gates ; `ci_scope.py` absent ou en échec → tous, avec
l'avertissement ; `tooling.conf` absent → 2 ; `edit` sur un fichier propre → 0 sans sortie. Le
bac à sable reçoit une copie de `scripts/ci_scope.py` et de `scripts/lib/conf.py` du dépôt (ou
leur absence, pour le cas du repli) : le test juge `check.sh`, pas le script vendorisé, qui a
ses propres selftests.

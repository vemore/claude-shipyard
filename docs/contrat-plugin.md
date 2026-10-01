# Contrat du plugin `shipyard`

> Pour qui construit ou maintient le plugin. Il fixe les noms, les fichiers, les interfaces et
> la répartition entre ce qui vit **dans le plugin** et ce qui vit **dans chaque projet**. Il
> complète `plugins/shipyard/skills/bootstrap/references/00-contrat.md` (le contrat *d'un
> projet*), qu'il ne contredit pas : quand ce document ajoute une clé ou un script, l'annexe 00
> est mise à jour dans le même changement.

## 1. Le principe de partage

| Vit dans le plugin (mis à jour par `/plugin update`) | Vit dans le projet (versionné dans son git) |
|---|---|
| Les hooks Claude Code et leur parseur | `scripts/lib/tooling.conf` — **toutes** les valeurs propres au projet |
| Les agents `implementer-simple`, `implementer-complex`, `reviewer` | `.claude/settings.json` : activation du plugin, marketplace, permissions |
| Les skills `bootstrap`, `join`, `ship-parallel`, `wip-refine`, `sync-tooling` | Les **copies vendorisées** des scripts que la CI et l'humain lancent sans Claude, et leurs selftests, avec `scripts/lib/VENDORED.json` |
| Les gabarits de ces copies (`templates/`) et `bin/vendor.py` | `scripts/check.sh` (propre à la stack), le code, la CI, le wiki, `wip/` |
| | En équipe : `.github/CODEOWNERS` et `.llmwiki/Team.md` |

Pourquoi : le code générique est écrit et testé **une fois**, et un correctif atteint tous les
projets à la mise à jour du plugin, au lieu d'être régénéré (et de varier) à chaque bootstrap.
Ce que la CI exécute reste dans le dépôt, parce qu'un runner GitHub n'a pas le plugin. Les
copies sont **identiques** au gabarit de leur version (empreintes dans `VENDORED.json`) : une
copie modifiée localement est une dérive signalée, pas une personnalisation silencieuse.

## 2. Noms

- Marketplace `claude-shipyard` (dépôt `vemore/claude-shipyard`), plugin `shipyard`
  (`plugins/shipyard/`). Installation : `shipyard@claude-shipyard`.
- Skills : `/shipyard:bootstrap`, `/shipyard:join`, `/shipyard:ship-parallel`,
  `/shipyard:wip-refine`, `/shipyard:sync-tooling`. Seul `bootstrap` porte
  `disable-model-invocation: true` (il crée un dépôt distant).
- Agents (`subagent_type`) : `shipyard:implementer-simple`, `shipyard:implementer-complex`,
  `shipyard:reviewer`. Le volume (« bulk ») reste `general-purpose` avec `model: "haiku"`,
  lancé par l'orchestrateur.
- Modèles, **fixés par le plugin** (décision de l'utilisateur, 2026-10-01) :

  | Agent | `model` | `effort` | `isolation` |
  |---|---|---|---|
  | `implementer-complex` | `sonnet` | `high` | `worktree` |
  | `implementer-simple` | `sonnet` | `low` | `worktree` |
  | `reviewer` | `sonnet` | `high` | `worktree` |

  Un projet qui veut autre chose définit ses propres agents dans `.claude/agents/` et le dit
  dans `Project.md` ; `ship-parallel` utilise alors leurs noms.
- Champs interdits dans un agent de plugin : `permissionMode`, `hooks`, `mcpServers`,
  `initialPrompt`.

## 3. Arborescence et propriétaires (construction en parallèle)

```
claude-shipyard/
  .claude-plugin/marketplace.json                 B5
  plugins/shipyard/
    .claude-plugin/plugin.json                    B5
    hooks/hooks.json, hooks/*.py, *.sh            B1
    agents/*.md                                   B3
    skills/bootstrap/SKILL.md                     orchestrateur
    skills/bootstrap/references/00, 02            orchestrateur
    skills/bootstrap/references/01, 03, 06, 07, 08  B5
    skills/{join,ship-parallel,wip-refine,sync-tooling}/  B3
    bin/vendor.py                                 B2
    templates/githooks/pre-commit                 B1
    templates/scripts/precommit.py (+ selftest/test_precommit.py)   B1
    templates/scripts/** (le reste)               B2
  tests/test_hooks.py (+ tests/_hooks_*.py)       B1
  tests/test_vendor.py                            B2
  docs/contrat-plugin.md                          orchestrateur
  docs/** (le reste : hooks.md, scripts.md)       B5
  README.md, CHANGELOG.md, LICENSE, .github/**    B5
```

Aucun lot n'écrit hors de sa ligne ; un besoin ailleurs se signale dans le rapport.

## 4. `tooling.conf` : clés ajoutées par le plugin

En plus des clés de l'annexe 00 §2 :

| Clé | Valeurs | Lue par |
|---|---|---|
| `TEAM_MODE` | `solo` · `team` | hooks (`session_start`), `ship-parallel`, `join` |
| `AUTONOMY` | `merge-deploy` · `merge` · `pr` | `ship-parallel` §3-4 |
| `RELEASE_MODE` | `continuous` · `planned` | `ship-parallel`, `wip-refine` (élagage) |
| `COMPONENT_<ID>_RE` | une regex par composant (`<ID>` = id de `COMPONENTS` en majuscules, `-` → `_`) : les chemins qui le concernent | `ci_scope.py` (donc `check.sh fast` et la CI) |

`ci_scope.py` n'a **aucune** table de chemins en dur. Pour chaque chemin, dans cet ordre : tout
composant dont `COMPONENT_<ID>_RE` correspond est marqué (plusieurs possibles) ; sinon un chemin de
documentation (`\.md$`, `^wip/`, `^\.llmwiki/`, `^docs/`) ne lance rien ; sinon tout est lancé
(fourre-tout). Les composants passent avant la documentation pour qu'un composant de
documentation (un site) s'exprime par sa seule clé ; un `.md` dans le dossier d'un composant lance
donc ce composant — l'erreur va du côté sûr. Le reste des copies vendorisées est aussi
générique : une valeur propre au projet est une clé de `tooling.conf`, jamais une ligne de code.

## 5. Copies vendorisées

Copiées par `bin/vendor.py` depuis `plugins/shipyard/templates/`, à l'identique :

| Gabarit | Destination dans le projet |
|---|---|
| `templates/scripts/{ci_scope,cleanup_local,pr_size,wiki_lint,wip,lane_paths,owners,precommit}.py` | `scripts/` |
| `templates/scripts/worktree_setup.sh`, `selftest.sh` | `scripts/` |
| `templates/scripts/lib/{conf,dead_paths}.py` | `scripts/lib/` |
| `templates/scripts/selftest/test_*.py` | `scripts/selftest/` |
| `templates/githooks/pre-commit` | `.githooks/pre-commit` |

`bin/vendor.py <racine-du-projet> [--check] [--force]` :
- écrit les fichiers, les rend exécutables, et `scripts/lib/VENDORED.json` :
  `{"shipyard": "<version de plugin.json>", "files": {"<chemin>": "<sha256>"}}` ;
- refuse d'écraser un fichier vendorisé dont le contenu diffère de l'empreinte enregistrée
  (modifié à la main), sauf `--force`, et liste ces fichiers ;
- `--check` n'écrit rien : imprime `ok`, `outdated <from> -> <to>`, `modified <chemin>`,
  `missing <chemin>` ; sortie 0 rien à faire, 1 quelque chose à synchroniser, 2 usage ;
- ne touche jamais à `tooling.conf`, `check.sh` ni à un fichier non listé ci-dessus.

Scripts nouveaux par rapport à l'annexe 00 :

| Script | Signature | Sortie | Codes |
|---|---|---|---|
| `scripts/owners.py` | `[--who LOGIN]`, chemins sur stdin | sans `--who` : `chemin<TAB>@owner …` (sémantique CODEOWNERS : dernier motif qui correspond) ; avec `--who` : les motifs que possède `@LOGIN` | 0 ; 1 avec `--who` si LOGIN ne possède rien ; 2 pas de CODEOWNERS ou usage |
| `scripts/lane_paths.py` | `lane-c\|deploy`, un chemin par ligne sur stdin | les chemins qui correspondent | 0 un au moins · 1 aucun · 2 conf illisible |
| `scripts/precommit.py` | — (appelé par `.githooks/pre-commit`) | contrôle des secrets (chemin et contenu, `SECRET_*`) et `scripts/check.sh fast --paths-from` sur les fichiers indexés | 0 · 1 refus ; sort 0 tout de suite si `CLAUDECODE=1` |
| `scripts/selftest.sh` | — | `python3 -m unittest discover -s scripts/selftest`, puis chaque `.claude/skills/*/scripts/` du projet ; échoue si zéro test | 0 · 1 |

`CODEOWNERS` est cherché dans `.github/CODEOWNERS`, puis `CODEOWNERS`, puis `docs/CODEOWNERS`
(l'ordre de GitHub).

## 6. Hooks : différences avec l'annexe 04

- Commandes dans `hooks/hooks.json` : `python3 "${CLAUDE_PLUGIN_ROOT}/hooks/<fichier>.py"`
  (sauf `session_start.sh`). `CLAUDE_PROJECT_DIR` reste disponible.
- **Projet non bootstrappé** (pas de `scripts/lib/tooling.conf` dans le dépôt jugé) : tous les
  hooks sont inertes (sortie 0, rien imprimé). Seule exception : `SessionStart` dans un dossier
  **vide** imprime « This folder is empty and shipyard is enabled: run /shipyard:bootstrap
  <what you want to build> to start a project with its tooling. » Pourquoi : pour lancer
  `/shipyard:bootstrap` dans un dossier vide, le plugin doit être installé pour l'utilisateur,
  donc actif dans tous ses dépôts ; il ne doit y dire un mot que là où il sert.
- `SessionStart` ajoute :
  - **version vendorisée** : si `scripts/lib/VENDORED.json` est plus ancien que
    `${CLAUDE_PLUGIN_ROOT}/.claude-plugin/plugin.json`, ou si `bin/vendor.py --check` voit un
    fichier modifié : « vendored tooling is <x>, plugin is <y> — run /shipyard:sync-tooling » ;
  - **équipe** (`TEAM_MODE=team`) : le login GitHub de la session (`gh api user --jq .login`,
    mis en cache une journée dans `<git-common-dir>/shipyard/identity`) est cherché dans
    CODEOWNERS via `scripts/owners.py --who`. Absent : « You (@login) are not a code owner of
    this repository yet — run /shipyard:join before starting work: the team records who owns
    which part of the code. » Présent : « You own: <motifs> ». Sans `gh` : rien.
- Le checkout principal reste sur la branche par défaut (fast-forward, déploiement, worktrees
  d'agents), mais les règles en vigueur sont désormais **celles de la version du plugin**,
  plus celles du checkout : une PR qui modifie les hooks n'existe plus côté projet.
- `.githooks/pre-commit` n'appelle plus les hooks (absents du dépôt) : il lance
  `scripts/precommit.py`, vendorisé.
- Les tests des hooks vivent dans le dépôt du plugin (`tests/test_hooks.py`), plus dans le
  projet.

## 7. Équipe et code owners

- Le questionnaire demande `solo` ou `team`. En `team`, la personne qui bootstrappe déclare sa
  zone (composants, chemins) ; elle est aussi owner des chemins d'outillage
  (`/.claude/`, `/scripts/`, `/.github/`, `/CLAUDE.md`) tant que l'équipe n'en décide pas
  autrement. `wip/` et `.llmwiki/` n'ont pas d'owner : presque chaque PR les touche, et leur
  owner devrait approuver toutes les PR de l'équipe.
- `.github/CODEOWNERS` : un motif par ligne, owners en `@login` ; en tête, un commentaire qui
  dit que ce fichier est tenu par `/shipyard:join` et lu par `scripts/owners.py`.
- `.llmwiki/Team.md` : une ligne par membre (login, zones, depuis quand), comment rejoindre,
  qui relit quoi, et ses `Decisions & History`.
- `/shipyard:join` : demande à la personne de quelles zones elle sera responsable
  (`AskUserQuestion` multi-choix sur les composants et les chemins de CODEOWNERS, plus
  « autre »), confirme son login, met à jour CODEOWNERS et Team.md dans un worktree neuf
  (`docs/join-<login>`), ouvre la PR. Cette PR touche CODEOWNERS, possédé par les mainteneurs :
  elle attend leur approbation, comme toute PR qui touche la zone d'un autre.
- `ship-parallel` en équipe :
  - le plan montre, pour chaque PR, les owners des chemins probables (`owners.py`) ;
  - une PR dont le diff touche une zone dont l'utilisateur de la session n'est pas owner reçoit
    automatiquement la demande de revue (CODEOWNERS) et **ne se merge qu'après l'approbation**
    d'un owner de chaque zone étrangère (`gh pr view <n> --json latestReviews`) ; en attendant,
    les autres PR avancent ; jamais de contournement ;
  - l'approbation de l'owner tient lieu du feu vert de la lane C pour ses chemins.
- Protection GitHub : l'approbation des owners est un **process**, pas une règle de branche.
  `require_code_owner_reviews` (annexe 08 §7.3) n'est jamais appliqué au bootstrap ni proposé
  par le questionnaire : un owner seul de sa zone ne pourrait plus merger ses propres PR. C'est
  une décision d'équipe, plus tard, quand chaque zone a au moins deux owners.

## 8. Lots du bootstrap (projet)

| Lot | Écrit | Modèle |
|---|---|---|
| orchestrateur | `.gitignore`, `LICENSE`, `tooling.conf`, `Project.md`, `.claude/settings.json`, `.github/CODEOWNERS` (équipe) ; lance `bin/vendor.py` | — |
| WP-A stack | code, tests, configs, `scripts/check.sh`, `scripts/selftest/test_check.py` | sonnet |
| WP-D connaissance | `CLAUDE.md`, `README.md`, `.llmwiki/**` sauf Project.md (dont `Team.md` en équipe), `wip/**`, `.claude/rules/**` | sonnet |
| WP-F CI | `.github/**` sauf CODEOWNERS | sonnet |
| WP-E skills de projet | `.claude/skills/{deploy,release}/**` seulement si une cible de déploiement ou des releases planifiées | sonnet |

## 9. CI du dépôt du plugin

`.github/workflows/ci.yml` : matrice `ubuntu-24.04` × Python 3.9 et 3.12, plus `macos-latest` ×
3.12 (la portabilité est une promesse du plugin) ; `python -m unittest discover -s tests` et
`-s plugins/shipyard/templates/scripts/selftest` ; validation du manifeste par
`claude plugin validate plugins/shipyard` si le CLI s'installe sans authentification (sinon une
validation JSON des deux manifestes). Actions épinglées par SHA.

## 10. Versions

`plugin.json` porte `version` (semver) : une mise à jour n'est distribuée qu'en changeant ce
champ. Chaque version a une section dans `CHANGELOG.md`, et un tag `v<version>`. Un
changement qui modifie un gabarit vendorisé est au moins mineur, et son entrée de changelog le
dit (« run /shipyard:sync-tooling »).

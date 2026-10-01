# Annexe 2 — Questionnaire

> Lu par l'orchestrateur à SKILL.md §2 et §4. Le but n'est pas de tout demander : c'est de
> ne **plus rien** avoir à demander ensuite. Chaque question qui reste après la description
> libre doit changer ce que le bootstrap construit ; le reste est déduit et affiché au
> récapitulatif, où l'utilisateur peut encore le changer.

## 1. Règles

- **Déduire d'abord.** La description libre, le pré-vol (`gh api user`, organisations, plan,
  mode de permissions) et le bon sens fixent la plupart des valeurs (§4). Une valeur déduite
  avec confiance n'est pas une question : elle va au récapitulatif.
- **Trois rondes au plus**, quatre questions au plus par ronde, puis **un récapitulatif**.
  Une ronde dont toutes les réponses sont déduites est sautée.
- **Le défaut d'abord**, libellé suivi de « (Recommandé) », avec dans `description` la
  conséquence concrète du choix (ce qui sera installé ou pas). « Autre » existe toujours :
  ne l'ajoute pas comme option.
- **Aperçu** (`preview`) quand l'utilisateur compare des ensembles : une stack, un jeu de
  gates, le récapitulatif.
- Pose les questions dans la langue de l'utilisateur ; les libellés ci-dessous sont des
  modèles.
- Chaque réponse s'écrit dans `.llmwiki/Project.md` avec sa raison : les mots de
  l'utilisateur s'il en a donné, sinon « default: <pourquoi ce défaut> ».

## 2. Étape 0 — la description libre

Si l'argument du skill ne la contient pas, un seul message, sans `AskUserQuestion` :

> Décris le projet en quelques lignes :
> 1. ce qu'il fait et pour qui ;
> 2. la stack que tu as en tête, s'il y en a une ;
> 3. où il tournera (rien, ton serveur, un cloud, un store, un registre de paquets…) ;
> 4. les 3 à 8 premières fonctionnalités, une ligne chacune ;
> 5. seul ou en équipe — et, en équipe, la partie du code dont tu seras responsable ;
> 6. les contraintes : données personnelles, langues de l'interface, licence, organisation GitHub.

Les fonctionnalités deviennent le backlog initial (`wip/todo/`, annexe 06 §7) : garde leurs
mots.

## 3. Les rondes

### Ronde 1 — Projet

| id | header | Question | Options (ordre : défaut d'abord) | Alimente |
|---|---|---|---|---|
| `stack` | Stack | « Quelle stack pour <projet> ? » | 2 ou 3 combinaisons cohérentes avec la description, chacune avec un aperçu (ci-dessous) | `COMPONENTS`, WP-A, `check.sh`, jobs CI |
| `name` | Nom | « Nom du projet et du dépôt ? » | 2 ou 3 slugs déduits de la description (kebab-case, ≤ 30 caractères) | `PROJECT_SLUG`, `GIT_CONFIG_NS`, marqueurs, nom du dépôt |
| `doc_language` | Langue doc | « Langue de la documentation (CLAUDE.md, wiki, backlog, skills) ? » | English (Recommandé) · la langue de l'utilisateur | WP-D, WP-E ; les messages des scripts restent en anglais |
| `i18n` | Langues UI | seulement si l'interface est destinée à des humains et que la description ne tranche pas : « L'interface doit-elle être traduite ? » | Non, une langue (Recommandé) · Oui : lesquelles (via Autre) | règle non négociable de CLAUDE.md, entrée `todo_nr` pour l'outillage i18n |

Aperçu d'une option `stack` :

```
Composants (COMPONENTS='api web')
  api  Python 3.12 · FastAPI · uv
       commit : ruff check, ruff format --check, mypy
       CI     : + pytest, audit des dépendances
  web  TypeScript · Vite + React · npm
       commit : eslint, prettier --check, tsc --noEmit
       CI     : + vitest, audit des dépendances
Dossiers   api/  web/
Jobs CI    "API — lint, types, tests"   "Web — lint, types, tests"
```

### Ronde 2 — Forge et livraison

| id | header | Question | Options | Alimente |
|---|---|---|---|---|
| `forge` | Dépôt | « Où créer le dépôt GitHub ? » | `<login>` privé (Recommandé) · `<login>` public · `<org>` privé (une option par organisation probable). Si le plan est gratuit ou inconnu, la description de l'option privée dit : « en offre gratuite, pas de protection de branche sur un dépôt privé : seuls les hooks protégeront la branche par défaut » | owner, visibilité, protection disponible, licence par défaut |
| `deploy` | Déploiement | « Qu'est-ce qu'un merge déploie ? » | Rien (bibliothèque, outil local) · Conteneur sur ton serveur (ssh) · Plateforme managée (PaaS, cloud) · Hébergement statique ; « Registre de paquets » ou « store » passent par Autre ou par `release` | `DEPLOY_PATHS_RE`, `DEPLOY_ENV_FILE`, skill `deploy` et sa sonde, §4 de `ship-parallel` |
| `autonomy` | Autonomie | « Une fois une PR verte, que fait Claude ? » | Il merge et déploie (Recommandé) · Il merge, tu déploies · Il ouvre la PR, tu merges | CLAUDE.md § Workflow, `ship-parallel` §3-4 |
| `release` | Releases | « Comment le projet sort-il des versions ? » | En continu : la branche par défaut est la production (Recommandé pour un service) · Versions planifiées : tags, registre, store (Recommandé pour une bibliothèque, un CLI, une app mobile) | sens de `wip/todo/` (release ou jalon en cours), skill `release`, déclencheur de la passe d'élagage |

### Ronde 3 — Qualité, risque, équipe

| id | header | Question | Options | Alimente |
|---|---|---|---|---|
| `gates` | Gates | « Quel niveau de contrôle ? » (aperçu par option : ce qui tourne au commit, ce qui tourne en CI) | Standard (Recommandé) : lint, format, types au commit ; tests et audit des dépendances en CI · Strict : + seuil de couverture, typage strict, avertissements = erreurs · Léger : lint et format au commit, tests en CI | `check.sh`, configs de la stack, `ci.yml` |
| `lane_c` | Zones sensibles | « Quelles zones exigent ton feu vert explicite avant chaque merge ? » (`multiSelect: true`) | Authentification et droits · Données personnelles et documents de confidentialité · Schéma et migrations de données · Paiements ou contrat d'API publique ; les zones déduites de la description portent « (Recommandé) » | `LANE_C_RE` (traduit en chemins par l'orchestrateur, §5), classes d'échec silencieux dans Project.md |
| `team` | Équipe | « Ce projet sera-t-il développé seul ou en équipe ? » | Seul (Recommandé si la description ne parle pas d'équipe) : pas de CODEOWNERS · En équipe : chacun déclare sa zone de code, versionnée dans `.github/CODEOWNERS` et `.llmwiki/Team.md` ; une PR qui touche la zone d'un autre attend son approbation (process, pas règle de branche : annexe 08 §7.3) | `TEAM_MODE`, CODEOWNERS, `Team.md` |
| `ownership` | Ta zone | « En équipe : de quelles parties du code seras-tu responsable ? » (`multiSelect: true` ; ignorée si `team` = seul) | une option par composant de la stack choisie en ronde 1 (« api/ », « web/ »…) · « L'outillage (scripts/, .claude/, .github/, CLAUDE.md) » (Recommandé : la personne qui bootstrappe le tient jusqu'à ce que l'équipe en décide autrement ; `wip/` et `.llmwiki/` restent sans owner) · « Tout le dépôt pour l'instant » ; une zone plus fine passe par « Autre » | `.github/CODEOWNERS`, `Team.md` |

### Récapitulatif — feu vert unique

Une question, header « Feu vert », avec le récapitulatif complet en aperçu (le même pour
chaque option) :

| Option | Effet |
|---|---|
| Go (Recommandé) | tout SKILL.md §3 à §9 s'exécute sans autre question |
| Go, et ajouter ce dépôt à `autoMode.environment` | idem, plus le paragraphe de l'annexe 03 §2 ajouté à `~/.claude/settings.json` à la fin. **Proposée seulement** si le pré-vol a vu `defaultMode: auto` |
| Ajuster | l'utilisateur écrit ce qui change (via Autre ou cette option) ; ne repose que ce qui change, puis le récapitulatif mis à jour |

Aperçu du récapitulatif (remplir chaque valeur ; une ligne par sujet) :

```
Projet       acme-api — « API de réservation pour clubs sportifs »
Dépôt        github.com/<owner>/acme-api · privé · licence : propriétaire
             protection de branche : indisponible (offre gratuite) → hooks seuls
Stack        api : Python 3.12 / FastAPI / uv      web : TypeScript / Vite / npm
Gates        commit : lint, format, types · CI : tests, audit des dépendances
Livraison    merge → déploiement conteneur (ssh) · Claude merge et déploie ses PR vertes
Releases     continu (la branche par défaut est la production)
Risque       lane C : src/api/auth/, migrations/ · seuil lane B : 1500 lignes
Équipe       en équipe · @alice : api/ et l'outillage (CODEOWNERS, Team.md) · revue par process
Agents       plugin shipyard <version> : complexe Sonnet (high) · simple Sonnet (low) · volume Haiku · 4 en parallèle
Outillage    copies vendorisées de shipyard ; différé en backlog : métriques, contrôle des crons, evals
Docs         anglais · interface : une langue
Backlog      5 entrées dans wip/todo/ : réservation, auth, …
Permissions  allowlist large protégée par les hooks ; plugin activé pour ce projet seulement

Actions sortantes autorisées par ce feu vert :
  • créer le dépôt GitHub et y pousser
  • régler le dépôt (squash seul, suppression des branches mergées)
  • ouvrir, puis merger en squash, la PR de bootstrap une fois verte
  • protéger la branche par défaut
```

## 4. Déductions

| Signal dans la description ou le pré-vol | Défaut proposé |
|---|---|
| « API », « service », « backend », « bot », « serveur » | une stack service ; `deploy` = conteneur ou plateforme managée ; `release` = continu |
| « site », « landing », « documentation » | stack statique ; `deploy` = hébergement statique |
| « CLI », « outil », « script » | Python + uv ou Go ; `deploy` = rien ; `release` = versions planifiées |
| « bibliothèque », « SDK », « package » | `deploy` = rien ; `release` = versions planifiées (registre) |
| « app mobile », « Android », « iOS » | `release` = versions planifiées (store) ; aucune stack imposée : demande |
| comptes, connexion, rôles | lane C « Authentification et droits » |
| données personnelles, santé, RGPD, mineurs | lane C « Données personnelles » ; une page `Privacy`-like à garder vraie (annexe 06) |
| base de données, SQL, migrations | lane C « Schéma et migrations » ; classe d'échec silencieux « migration » |
| paiement, facturation, API publique | lane C « Paiements ou contrat d'API publique » |
| plusieurs langues citées, « multilingue » | `i18n` = oui, ces langues |
| « open source », « public » | `forge` public ; licence MIT |
| organisation citée ou une seule organisation au pré-vol | l'organisation comme owner proposé |
| stack nommée explicitement | cette stack, sans question (l'aperçu va au récapitulatif) |
| « équipe », « nous », des coéquipiers ou une organisation cités | `team` = en équipe (option recommandée) ; `ownership` proposé d'après le rôle décrit |

Une déduction n'impose rien : elle choisit l'option marquée « (Recommandé) » ou la valeur du
récapitulatif.

## 5. Valeurs fixées sans question (affichées au récapitulatif)

| Sujet | Défaut | Raison |
|---|---|---|
| Branche par défaut | `main` | convention de la forge |
| Licence | MIT si public ; propriétaire (pas de fichier `LICENSE`, « All rights reserved » dans le README) si privé | une licence se choisit pour publier |
| `SIZE_THRESHOLD` | 1500 | la quantité de code de production qu'une revue peut tenir ; au-delà, revue indépendante |
| `WIP_LIMIT` / `REFINE_THRESHOLD` | 12 / 30 | environ une passe de `ship-parallel` ; tri quand le backlog suivant déborde |
| `CONCURRENCY_CAP` | 4 | au-delà, la CI des runners gratuits sature et les merges en série attendent |
| Permissions | allowlist large protégée par les hooks (annexe 03 §2) | les hooks refusent les formes dangereuses, l'allowlist peut donc être large : moins d'interruptions |
| Hook git `pre-commit` pour les commits humains | oui | sans lui, un commit fait hors de Claude Code échappe aux gates jusqu'à la CI |
| Dependabot, audit des dépendances, CI hebdomadaire | oui | les dépendances vieillissent même quand personne ne touche au code |
| `LANE_C_RE` | traduit par l'orchestrateur depuis `lane_c` et la structure de la stack (`src/<pkg>/auth/`, `migrations/`, `PRIVACY.md`…), même si les dossiers n'existent pas encore | le risque se fixe à la planification, pas une fois le code écrit |
| Classes d'échec silencieux (lane B) | migration de données, contrat entre composants, tout ce qui est persisté ou envoyé à un autre système | ce sont les changements dont la CI peut être verte et la production cassée |

## 6. Gabarit de `.llmwiki/Project.md`

L'orchestrateur l'écrit à SKILL.md §4. Anglais, ou la langue de doc choisie. Les valeurs
machine sont aussi dans `scripts/lib/tooling.conf` ; cette page dit **pourquoi**.

```markdown
# Project

> Scope: what this project is, the decisions taken at bootstrap and why. The machine values
> live in `scripts/lib/tooling.conf`; this page owns the reasons.
> Related: [[Architecture]] · [[ParallelDelivery]] · [[Hooks]] · [[Testing]]
> Updated: <YYYY-MM-DD>

## Facts

### Identity
| Key | Value |
|---|---|
| Purpose | <one or two sentences, in the user's words> |
| Repository | `<owner>/<slug>`, <private/public>, default branch `<main>` |
| Licence | <SPDX id or "proprietary — all rights reserved"> |
| Documentation language | <en/…> ; UI languages: <none / list> |
| Bootstrapped | <YYYY-MM-DD> with `/shipyard:bootstrap` (shipyard <version>) |

### Components
| Id | Directories | Language and framework | Package manager | Dependency audit | CI job name (required check) |
|---|---|---|---|---|---|
| <api> | `<api/>` | <Python 3.12, FastAPI> | <uv> | <the ecosystem's own audit, run by `scripts/check.sh ci <api>` — e.g. `uv audit`, `npm audit --omit=dev`, `cargo audit`, or `osv-scanner` when named here> | `<API — lint, types, tests>` |
Plus `Tooling — selftests, wiki, wip` (required) and `Scope` (not required).

### Skills and documents
- Skills installed: <ship-parallel, wip-refine[, deploy][, release]> — the registry is `CLAUDE.md` and [[INDEX]].
- Documents that move together: <none / e.g. PRIVACY.md + README § Privacy for any new outbound data flow> ([[Documentation]]).

### Delivery
- Current <release / milestone>: <name, e.g. 0.1.0 or "MVP"> — what `wip/todo/` holds.
- Deploy target: <none / container over ssh / managed platform / static hosting> — targets
  live in the untracked `<DEPLOY_ENV_FILE>`, never in a tracked file.
- Autonomy: <Claude merges and deploys its own green PRs / merges only / opens PRs only>.
- Releases: <continuous / planned> — `wip/todo/` holds <the release / the milestone> in progress.
- Default-branch protection: <available — applied after the bootstrap PR merges (strict,
  linear, enforce_admins) / unavailable: the probe answered "Upgrade to GitHub Pro" — the hooks
  are the only guard (see the deferred list below)>.

### Quality and permissions
- Gates: <standard / strict / light> — <what runs at commit, what runs in CI>.
- Permissions posture: <broad allowlist guarded by the hooks / cautious> ; stack tools to
  allow: <uv, ruff, mypy, pytest, …>.

### Risk
- Lane C (explicit go-ahead before each merge): <areas> → `LANE_C_RE` = `<regex>`.
- Silent-failure classes (lane B whatever the size): <data migrations, contracts between
  components, anything persisted or sent to another system, …>.
- Lane B size threshold: <1500> added or modified lines of code (`scripts/pr_size.py`).

### Agents (from the shipyard plugin)
| Rating | Agent | Model |
|---|---|---|
| complex | `shipyard:implementer-complex` | Sonnet, effort high |
| simple | `shipyard:implementer-simple` | Sonnet, effort low |
| bulk | `general-purpose`, one per unit | Haiku |
| review (lanes B, C) | `shipyard:reviewer` | Sonnet, effort high |
At most <CONCURRENCY_CAP> implementers at a time. To use other models, define project agents in
`.claude/agents/` and record it here.

### Team
- Mode: <solo / team> (`TEAM_MODE`).
- <team only> Owners are declared in `.github/CODEOWNERS` and described in [[Team]]; at
  bootstrap: @<login> owns <areas>. Each new teammate runs `/shipyard:join`.
- <team only> Code-owner review is a process (ship-parallel waits for the owner), not a branch
  rule; `require_code_owner_reviews` is a later team decision, once every area has two owners.

### Tooling
- shipyard <version>, vendored scripts listed in `scripts/lib/VENDORED.json`; update with
  `/shipyard:sync-tooling` after a plugin update.

### Initial backlog (the user's words)
<the 3–8 first features exactly as the user wrote them, one bullet each; WP-D turns each into a
`wip/todo/` entry (annex 06 §7) and links it here once written>

### Deferred at bootstrap
<one line per deferred item with the exact file name of the entry WP-D will write, e.g.
"Delivery metrics — `wip/todo_nr/<YYYY-MM-DD>-delivery-metrics-not-installed.md`"; also the
branch protection when unavailable — or "none (tooling level: complet)">

## Decisions & History

- **<Decision> (<YYYY-MM-DD>).** <the answer, and why: the user's words, or "default: …">.
  (one bullet per questionnaire answer and per decision taken alone after the go-ahead)
```

## 7. Correspondance réponse → artefacts

| Réponse | `tooling.conf` | Fichiers et lots touchés |
|---|---|---|
| `stack` | `COMPONENTS`, un `COMPONENT_<ID>_RE` par composant, `DEAD_PATH_ROOTS` (+ le répertoire de chaque composant), `SIZE_EXCLUDE_RE` (+ ses dossiers de tests, de générés et ses verrous) | WP-A (scaffold, `check.sh`, audit), WP-F (un job par composant), Project.md § Components ; lu par les copies `ci_scope.py` et `worktree_setup.sh` |
| `name` | `PROJECT_SLUG`, `GIT_CONFIG_NS`, `SETUP_MARKER`, `SCHEDULED_STAMP`, `WORKTREE_PREFIX` | tout ; nom du dépôt |
| `doc_language` | — | WP-D, WP-E (gabarits traduits) |
| `i18n` | — | CLAUDE.md non négociable « no hardcoded user-facing string » ; entrée `todo_nr` pour l'outillage de traduction (un skill naîtra à la deuxième chaîne ajoutée à la main) |
| `forge` | — | §3 de SKILL.md, licence, Project.md § Delivery (protection) |
| `deploy` | `DEPLOY_PATHS_RE`, `DEPLOY_ENV_FILE`, `SECRET_PATH_RE` (+ le nom de `DEPLOY_ENV_FILE`) | WP-E (skill `deploy` + `probe.sh`, `<DEPLOY_ENV_FILE>.example`), `ship-parallel` §1 (sonde) et §4, `.gitignore`, page `Deployment` (WP-D) |
| `autonomy` | `AUTONOMY` (`merge-deploy` · `merge` · `pr`) | CLAUDE.md § Workflow, `/shipyard:ship-parallel` |
| `release` | `RELEASE_MODE` (`continuous` · `planned`) | WP-E (skill `release` si planifié), `wip/README.md` (sens de `todo/`), déclencheur de l'élagage |
| `gates` | — | WP-A (configs, `check.sh`), WP-F, Project.md § Quality and permissions |
| `lane_c` | `LANE_C_RE` | `ship-parallel` §1, Project.md § Risk |
| `team` | `TEAM_MODE` (`solo` · `team`) | `.github/CODEOWNERS` (orchestrateur), `Team.md` et la ligne d'équipe de CLAUDE.md (WP-D) |
| `ownership` | — | `.github/CODEOWNERS` : les chemins d'outillage et la zone déclarée, au login de la personne qui bootstrappe ; `Team.md` |
| (fixé) modèles | — | agents du plugin ; Project.md § Agents |
| (fixé) niveau d'outillage | `TOOLING_LEVEL=essentiel` | les éléments du niveau complet deviennent des entrées `wip/todo_nr/` (WP-D) |
| feu vert + autoMode | — | SKILL.md §9 ; ce choix **est** le consentement : rien n'est redemandé ensuite |
| (défaut) posture de permissions | — | `.claude/settings.json` (orchestrateur), Project.md § Quality and permissions |
| (défaut) `PRUNE_EVERY_MERGES` | `PRUNE_EVERY_MERGES` | passe d'élagage (annexe 06 §3) |

## 8. Fichier de réponses du mode test

Une clé par ligne, `id: valeur`, plus la description et les fonctionnalités :

```
description: Command-line tool that renames photos from their EXIF date.
features:
- rename files in a folder from their EXIF capture date
- dry-run mode that prints the plan
- undo the last run from a journal file
stack: cli=Python 3.12, uv, ruff, mypy, pytest
name: exif-renamer
doc_language: en
i18n: no
forge: local
deploy: none
autonomy: merge-deploy
release: planned
gates: standard
lane_c: none
team: team
ownership: cli, tooling
login: test-user
go: yes
```

`login` est propre au mode test (sans GitHub, le login de la personne qui bootstrappe).

`forge: local` est propre au mode test : le remote est un dépôt nu local (SKILL.md §11) ; la
licence par défaut y est « propriétaire », comme pour un dépôt privé.

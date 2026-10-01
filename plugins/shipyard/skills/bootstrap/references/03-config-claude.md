# Annexe 3 — Configuration Claude Code : CLAUDE.md, settings, rules, agents

> Lue par **WP-D** (§1, §3, §4, §6) pour `CLAUDE.md` et `.claude/rules/`, et par
> l'orchestrateur (§2) pour `.claude/settings.json` et la proposition `autoMode`. Les gabarits
> sont en anglais : traduire la prose (jamais les clés JSON, le code ni les commandes) si la
> langue de doc choisie au questionnaire n'est pas l'anglais. Les hooks, les agents et les
> skills de livraison viennent du plugin `shipyard` : le projet ne les écrit pas, il les active
> (§2.2) et les nomme (§1).

## 1. `CLAUDE.md` — le gabarit

**Pourquoi un budget.** Dans un projet antérieur, `CLAUDE.md` avait atteint 204 lignes, dont
environ 40 % de process : chaque incident était devenu une règle et aucune n'avait été retirée.
Ramené à 120 lignes, il ne garde que ce dont *chaque* session a besoin ; le reste vit dans la
page wiki qui le possède, et `CLAUDE.md` pointe vers elle en une ligne. Le budget est
`CLAUDE_MD_BUDGET`. Le gabarit rempli doit tenir dedans en laissant de la marge, parce que le
projet en ajoutera : si les variantes résolues serrent, raccourcir d'abord `Commands` et `Code
style`, jamais `Workflow` ni `Git`.

**Pourquoi ces sections et pas d'autres.** Une règle que l'agent doit appliquer *sans y penser*
(l'ordre « worktree d'abord », « une PR verte = fini ») doit être sous ses yeux à chaque
session ; une règle qu'un hook décide n'a pas besoin d'être répétée ici, il suffit de dire où
sont listés les refus (`.llmwiki/Hooks.md`). Les explications longues vont au wiki.

Gabarit (les `<…>` sont remplis par WP-D à partir de `.llmwiki/Project.md` et de
`scripts/lib/tooling.conf` ; les blocs `<!-- variant: … -->` sont choisis puis les commentaires
retirés) :

````markdown
# <Project name> — Instructions for Claude Code

> Budget: ≤ <CLAUDE_MD_BUDGET> lines; anything past it moves to the wiki page that owns it.

<Project name> is <one sentence: what it does and for whom>. Components: <component id — stack,
one short clause each>.
<!-- variant: deploy target exists -->
The deploy target is configured per machine in the untracked `<DEPLOY_ENV_FILE>`: never commit a
real host, URL, path or credential — placeholders only, in `<DEPLOY_ENV_FILE>.example`.
<!-- end variant -->

Hooks, agents and delivery skills come from the **shipyard** plugin, enabled in
`.claude/settings.json`; a session without it has no guard — install it first (`README.md`).

## Read the wiki first

Durable project knowledge lives in **`.llmwiki/`**, not in this file. **Before any non-trivial
task, read `.llmwiki/INDEX.md` and load the pages your task touches.** Do not guess at
architecture, decisions or procedures — a page already has them. `[[Name]]` in a wiki page
resolves to `.llmwiki/Name.md`. What was decided when the project started, and why:
`.llmwiki/Project.md`.

Repeatable procedures are **skills** — check them before writing steps out by hand:
`/shipyard:ship-parallel`, `/shipyard:wip-refine`, `/shipyard:sync-tooling`<, `/shipyard:join`>
from the plugin<; `deploy`, `release` in `.claude/skills/`>.

Scoped instructions: <`<component>/CLAUDE.md` (…)> <· `.claude/rules/<name>.md` (…)> <or: none yet>.

## Non-negotiables

1. <project rule from the questionnaire, with its reason in one clause>
<!-- 0 to 3 items. Example (i18n chosen): "Never hardcode a user-facing string: every text goes
through <i18n mechanism>, in all <N> languages; never hand-roll a plural." Delete the section if
there is none. -->

What a hook refuses outright — secrets, red gates, commits on the wrong branch, push and merge
shapes — and what the hooks do *not* cover: `.llmwiki/Hooks.md`.

## Workflow

- **Work is tracked one file per entry under `wip/`**, never in a shared list: `todo/` for the
  <release | milestone> in progress (at most <WIP_LIMIT> entries), `todo_nr/` for the next,
  `done/` closed. `wip/README.md`.
- **A problem you find but were not asked to fix becomes a `wip/` entry** — not an inline fix,
  not dropped: `wip/todo_nr/`, or `wip/todo/` when it blocks the <release | milestone>
  (security, crash, data loss<, …>). Then carry on with the task.
- **Tooling that fights you is a `wip/` entry too** — a skill, hook, wiki procedure or this file
  that forced a detour; it may propose a removal. Never edit a vendored file
  (`scripts/lib/VENDORED.json`); after a plugin update, `/shipyard:sync-tooling`.
- **An entry you fix moves to `wip/done/` in the same change**, by `git mv`, with a
  `**Status:** done` line under its title.
- **Keep every document a change falsifies true, in the same commit**: its wiki page and
  `Updated:` date, `README.md`<, and …>. `.llmwiki/Documentation.md`.
- **Nothing is finished until it is tested and committed**: the commit hook runs
  `scripts/check.sh fast`, CI the tests; green gates with no commit, or red ones, are incomplete.
- **A finished change is a green pull request against `<DEFAULT_BRANCH>`.** Push,
  `gh pr create --base <DEFAULT_BRANCH>` with a body saying what changed and why,
  `gh pr checks <n> --watch`, fix what fails, report the URL and the check state. Never stack on
  another branch: wait for it to merge, or put both changes in one pull request. A branch held
  back on purpose sets `git config branch.<name>.noPullRequest true`, and you say so.
<!-- variant: autonomy = merge + deploy -->
- **You merge and deploy your own green pull requests, through `/shipyard:ship-parallel`**, in
  the lane their risk picked: squash-merge, deploy what the merge changed, smoke-test. A session
  that cannot reach the deploy target says "merged, not deployed" and files a `wip/todo/` entry;
  a later problem is a new pull request.
<!-- variant: autonomy = merge only -->
- **You squash-merge your own green pull requests, through `/shipyard:ship-parallel`**, in the
  lane their risk picked. Deploying is the user's; say what each merge would deploy.
<!-- variant: autonomy = PR only -->
- **You stop at a green pull request**: the user reviews and merges. `/shipyard:ship-parallel`
  plans, launches and reports; it never merges.
<!-- end variant -->
<!-- variant: team mode -->
- **You own the areas listed under your login in `.llmwiki/Team.md`**; a change outside them
  waits for its owner's approval, whatever its lane. A new teammate runs `/shipyard:join` first.
<!-- end variant -->
- **Several tasks at once are several pull requests, in parallel** — one per theme, one agent
  and worktree each, rated at planning: `shipyard:implementer-complex` (Sonnet, high effort),
  `shipyard:implementer-simple` (Sonnet, low), bulk units on Haiku. `/shipyard:ship-parallel`.
- **Leave the local environment clean**: the main checkout back on a fast-forwarded
  `<DEFAULT_BRANCH>`, then `scripts/cleanup_local.py` and `--apply` once no agent is working;
  report what it keeps.
- **The process gets pruned, not only grown**: this file's budget above, and a pruning pass
  <before each release | every `PRUNE_EVERY_MERGES` merged pull requests> (`.llmwiki/Documentation.md`).

## Commands

```bash
scripts/worktree_setup.sh <dir>        # dependencies + codegen for a fresh worktree
scripts/check.sh fast                  # static gates — what the commit hook runs
scripts/check.sh test                  # test suites — what CI runs
<component run / build commands, one per line, with a comment>
scripts/selftest.sh                    # tooling self-tests (vendored scripts, skill scripts)
scripts/wip.py list                    # open work
scripts/wiki_lint.py                   # wiki lint
```

## Code style

- <style guide and the config file that enforces it>
- <directory layout in one line>
- <one or two architecture rules, e.g. "data access goes through …, never from …">
- A bug fix starts with a failing test that reproduces it.

## Git

**Start every piece of work on a fresh branch off the current `origin/<DEFAULT_BRANCH>`, in its
own worktree**, before the first commit — not after it. The main checkout stays on
`<DEFAULT_BRANCH>`, fast-forwarded: worktrees start from it and deploys run from it. The hooks
never fetch, so the fetch is on you.

```bash
git fetch --prune origin
git worktree add --no-track -b <type>/<topic> <WORKTREE_PREFIX><topic> origin/<DEFAULT_BRANCH>
scripts/worktree_setup.sh <WORKTREE_PREFIX><topic>
git push -u origin <type>/<topic>   # first push: tracks its own remote, so a merged branch reads [gone]
```

An agent launched with `isolation: "worktree"` has its worktree already, and switches to
`<type>/<topic>` off `origin/<DEFAULT_BRANCH>` as its first step.

- Branch names `<type>/<topic>`; commit messages `feat:`, `fix:`, `refactor:`, `docs:`, `chore:`.
- Do not commit build artifacts, generated files or secrets.
- Never force-push, and never rewrite a commit already on `origin/<DEFAULT_BRANCH>`. Bring a
  branch up to date by merging `<DEFAULT_BRANCH>` into it —
  `gh api -X PUT repos/{owner}/{repo}/pulls/<n>/update-branch` — never by rebasing. That merge
  happens on GitHub: in a worktree of that branch, `git pull --no-rebase` before the next commit,
  or the push is rejected.
````

**Ce qui varie avec quelle réponse du questionnaire** (annexe 02) :

| Ligne / bloc | Réponse qui la fixe |
|---|---|
| Phrase « deploy target… » | cible de déploiement ≠ aucune |
| `release` vs `milestone` dans Workflow | `RELEASE_MODE` : `planned` → release ; `continuous` → milestone (« jalon ») |
| Exemples de bloqueurs (`security, crash, data loss, …`) | domaine du projet (ex. conformité, politique de store) |
| Liste des skills | `/shipyard:join` seulement en équipe ; `deploy` si cible de déploiement, `release` si `RELEASE_MODE=planned` ; jamais un skill qui n'existe pas |
| Non-negotiables | i18n, règles métier dures données au questionnaire |
| Variante d'autonomie | `AUTONOMY` ; `merge-deploy` **sans cible de déploiement** prend la variante « merge only » en remplaçant sa seconde phrase par « Nothing is deployed by a merge. » |
| Variante équipe | `TEAM_MODE=team` ; supprimée en solo |
| « pruning pass » | `RELEASE_MODE` : avant chaque release, ou toutes les `PRUNE_EVERY_MERGES` PR mergées (défaut 30) |
| `README.md<, and …>` dans « Keep every document… » | documents qui doivent bouger ensemble (ex. politique de confidentialité si le projet envoie des données) |
| Commands | les cibles de `scripts/check.sh` (fixées par le contrat, connues d'avance), les scripts vendorisés, et la commande de lancement de la stack donnée par `Project.md` ; toute autre commande que WP-D ne peut pas connaître → marqueur `<!-- FILL: … -->` rempli à l'intégration |

La ligne équipe ne nomme pas de zones : `CLAUDE.md` est le même pour tous, chacun lit les
siennes dans `Team.md` (ou `scripts/owners.py --who <login>`).

**Contrôle d'intégration** : `wc -l CLAUDE.md` ≤ `CLAUDE_MD_BUDGET` ; chaque skill de projet
nommé existe sous `.claude/skills/` ; chaque chemin entre backticks existe (le lint wiki ne
couvre pas `CLAUDE.md`, l'orchestrateur le vérifie à la main).

## 2. `.claude/settings.json` — plugin et permissions

### 2.1 Partagé contre personnel

- `.claude/settings.json` est **commité** : il active le plugin pour ce dépôt et porte
  l'allowlist commune. C'est le même pour tous les clones et tous les agents.
- `.claude/settings.local.json` est **gitignoré** : préférences et « always allow » personnels.
  Il s'accumule au fil des clics « toujours autoriser » ; ce n'est pas une politique, ne le
  versionnez jamais et ne le recopiez pas d'un projet à l'autre.
- Les clés `permissions` se fusionnent entre niveaux (utilisateur, projet, local).
- **Ne pas mettre `permissions.defaultMode` dans le fichier partagé** : le réglage projet
  écraserait le mode choisi par chaque utilisateur (par exemple le mode auto). Le mode reste un
  choix personnel (`~/.claude/settings.json` ou `settings.local.json`).
- **Pas de bloc `hooks`.** Les hooks viennent du plugin (son `hooks/hooks.json`, chargé avec
  lui). Un bloc `hooks` ici ferait tourner deux fois les mêmes gardes, ou deux versions qui ne
  jugent pas pareil. Une règle propre au projet qu'un script peut décider va dans
  `scripts/check.sh fast`, que le garde de commit du plugin appelle déjà (annexe 05) ; un hook
  de projet ne s'ajoute plus tard que pour ce que `check.sh` ne peut pas faire, avec sa raison
  dans `Hooks.md`.

### 2.2 Activation du plugin (l'orchestrateur l'écrit tel quel)

```json
{
  "extraKnownMarketplaces": {
    "claude-shipyard": {
      "source": { "source": "github", "repo": "vemore/claude-shipyard" }
    }
  },
  "enabledPlugins": {
    "shipyard@claude-shipyard": true
  }
}
```

- **Au niveau du projet, pas de l'utilisateur.** `enabledPlugins` dans le fichier partagé
  active le plugin pour ce dépôt et pour chaque personne qui le clone ; ses garde-fous ne
  s'étendent pas aux autres dépôts de l'utilisateur. Activé au niveau utilisateur, il serait
  chargé partout — inerte faute de `tooling.conf`, mais présent, avec sa ligne de `SessionStart`
  dans chaque session, et le bootstrap n'a pas à décider pour les autres projets. Si
  l'utilisateur l'a installé au niveau utilisateur pour lancer le bootstrap, c'est son choix :
  le récapitulatif le signale, rien n'est changé dans `~/.claude/`.
- `extraKnownMarketplaces` : un clone neuf connaît la marketplace sans configuration ; à la
  première ouverture du dossier (approbation de confiance), Claude Code propose d'ajouter la
  marketplace et d'installer le plugin. À défaut : `/plugin marketplace add
  vemore/claude-shipyard`, puis `/plugin install shipyard@claude-shipyard`. Le README le dit
  pour un clone neuf (WP-D).
- La version en vigueur est celle que chaque personne a installée (`/plugin` la montre) ; les
  copies vendorisées enregistrent la leur dans `scripts/lib/VENDORED.json`, et `SessionStart`
  signale l'écart (annexe 04 §2).

### 2.3 `permissions` selon la posture de `Project.md` § Quality and permissions (défaut : large + garde-fous)

Syntaxe : `Bash(<préfixe> *)` (correspondance par préfixe, `*` final pour les arguments) ;
`Edit`, `Write` seuls autorisent l'outil partout. Les règles `deny` sont des préfixes : elles
attrapent la forme écrite, pas toutes les formes équivalentes (`git -C x push -f` n'est pas
`git push -f`). **La garantie, ce sont les hooks du plugin** ; `deny` n'est qu'un filet de
confort.

**Posture « large + garde-fous » (recommandée).** L'agent travaille sans demander : le garde
Bash du plugin refuse les formes dangereuses (force-push, push sur la branche par défaut, merge
sans squash ou avec `--admin`, PR empilée, commit de secret, commit avec gates rouges), donc
l'allowlist peut être large sans que l'autonomie coûte la sécurité. **Elle suppose le plugin
actif** : une session où il n'est pas installé a l'allowlist sans les gardes. D'où la phrase de
`CLAUDE.md` et du README (« install it first »), et les `deny` qui restent.

```json
{
  "permissions": {
    "allow": [
      "Edit", "Write", "MultiEdit",
      "Bash(git *)",
      "Bash(gh pr *)", "Bash(gh run *)", "Bash(gh api *)", "Bash(gh repo view *)",
      "Bash(gh workflow *)", "Bash(gh auth status *)",
      "Bash(scripts/*)", "Bash(python3 scripts/*)", "Bash(./scripts/*)",
      "Bash(python3 -m unittest *)",
      "Bash(ls *)", "Bash(cat *)", "Bash(head *)", "Bash(tail *)", "Bash(wc *)",
      "Bash(grep *)", "Bash(rg *)", "Bash(find *)", "Bash(diff *)", "Bash(sort *)",
      "Bash(mkdir *)", "Bash(mv *)", "Bash(cp *)", "Bash(touch *)", "Bash(chmod *)",
      "Bash(<stack tool> *)",
      "WebSearch"
    ],
    "deny": [
      "Bash(git push --force *)", "Bash(git push -f *)",
      "Bash(gh pr merge --admin *)", "Bash(gh repo delete *)",
      "Bash(git config --global *)",
      "Read(./.env)", "Read(./**/.env)", "Read(./<DEPLOY_ENV_FILE>)"
    ]
  }
}
```

- `<stack tool>` : une ligne par outil de la stack (gestionnaire de paquets, lanceur de tests,
  linter, compilateur), lue dans `.llmwiki/Project.md` § Quality and permissions.
- `Read(./.env)` en `deny` : évite qu'un secret entre dans un transcript par simple lecture.
  `cat .env` le contourne ; c'est de l'hygiène, pas une frontière. Sans cible de déploiement,
  la ligne `Read(./<DEPLOY_ENV_FILE>)` disparaît.
- Pas de `Bash(rm *)` dans la posture par défaut : une suppression reste une question, parce
  qu'aucun hook ne protège le contenu d'un worktree non commité.

**Posture « prudente ».** Lecture et vérifications sans question, tout le reste demandé :

```json
{
  "permissions": {
    "allow": [
      "Bash(git status *)", "Bash(git diff *)", "Bash(git log *)", "Bash(git show *)",
      "Bash(git branch *)", "Bash(git worktree list *)", "Bash(git fetch *)",
      "Bash(gh pr view *)", "Bash(gh pr checks *)", "Bash(gh pr list *)", "Bash(gh run view *)",
      "Bash(scripts/check.sh *)", "Bash(scripts/wip.py *)", "Bash(scripts/wiki_lint.py *)",
      "Bash(scripts/selftest.sh *)", "Bash(python3 -m unittest *)",
      "Bash(ls *)", "Bash(cat *)", "Bash(head *)", "Bash(tail *)", "Bash(wc *)",
      "Bash(grep *)", "Bash(rg *)", "Bash(find *)"
    ],
    "deny": [ "Bash(git push --force *)", "Bash(git push -f *)",
              "Bash(gh pr merge --admin *)", "Bash(gh repo delete *)" ]
  }
}
```

Avec cette posture, `ship-parallel` reste possible mais chaque agent demandera ses éditions ;
l'utilisateur peut basculer sa session en `acceptEdits` (Maj+Tab) pour les accepter en bloc.

Le fichier écrit est **un seul objet JSON** : `extraKnownMarketplaces`, `enabledPlugins` et
`permissions` côte à côte.

### 2.4 Le mode auto (niveau utilisateur seulement)

Le mode auto (`defaultMode: "auto"`) et ses réglages `autoMode.*` (`environment`, `allow`,
`soft_deny`, `hard_deny`) ne se lisent **que** dans les réglages utilisateur
(`~/.claude/settings.json`) ou gérés — un dépôt ne peut pas s'accorder sa propre confiance. Le
bootstrap ne les écrit donc jamais dans le projet. L'option « Go, et ajouter ce dépôt à
`autoMode.environment` » du récapitulatif (annexe 02) **est** le consentement : rien n'est
redemandé. Si elle a été choisie, l'orchestrateur ajoute à la fin, au tableau
`autoMode.environment` des réglages utilisateur, un paragraphe qui décrit ce dépôt au
classifieur (lire le fichier d'abord, ajouter sans rien écraser, garder `"$defaults"` s'il est
présent) :

```json
"**Repository <owner>/<repo>** (<public|private>, GitHub): default branch `<DEFAULT_BRANCH>` <is protected (squash-only, required checks) | is guarded by the shipyard plugin's hooks only (no server-side protection on this plan)>. Work happens in git worktrees under `<WORKTREE_PREFIX>*` and `.claude/worktrees/`; pushes go to `origin` only, on `<type>/<topic>` branches.",
"**Secrets for <PROJECT_SLUG>**: untracked files only (`.env`, `<DEPLOY_ENV_FILE>`); never in tracked files, command lines or pull request bodies.",
"**Deploy target for <PROJECT_SLUG>**: <kind of target, no host name> reached through the `deploy` skill after a squash-merge — routine, outward-facing, reversible by its rollback."
```

La troisième ligne n'existe que s'il y a une cible de déploiement. La variante de la première
suit le verdict de la sonde de protection (`Project.md`). Une entrée `soft_deny` (« production
deploy — confirm each run ») ne s'ajoute que si l'utilisateur a demandé, dans sa description,
à confirmer chaque déploiement — aucune question ne la propose.

## 3. `.claude/rules/*.md` — instructions par chemins

Un fichier de `.claude/rules/` avec un frontmatter `paths:` ne se charge que lorsque l'agent lit
un fichier qui correspond à l'un des globs (sans `paths:`, il se charge au démarrage comme
`CLAUDE.md`). À utiliser quand :

- les instructions concernent un sous-arbre **qui ne doit pas les contenir** — typiquement un
  dossier publié tel quel (assets statiques, site, package distribué) : un `CLAUDE.md` posé
  dedans serait publié avec lui. Dans un projet antérieur, un `CLAUDE.md` vivait dans le dossier
  copié intégralement dans le build web, et partait donc en production ;
- ou elles ne concernent qu'une poignée de fichiers dispersés (un script de build, un fichier de
  connexion, une suite d'intégration) qui n'ont pas de dossier commun.

Sinon, préférer un `CLAUDE.md` de composant (§4). Gabarit (WP-D) :

```markdown
---
paths:
  - "<published-dir>/**"
  - "<scattered/file/one>"
---

# <Area> — rules

These instructions used to belong in `<dir>/CLAUDE.md`; they live here because <why the
directory cannot hold them>.

## Read the wiki first
- `.llmwiki/<Page>.md` — <what it owns>

## Rules
1. **<Rule>.** <Why, one or two sentences.>

## Commands
<the commands for this area>

## Gotchas
- <symptom> → <cause> → <fix>
```

## 4. `CLAUDE.md` de composant

Un `CLAUDE.md` dans le dossier d'un composant (`api/CLAUDE.md`, `web/CLAUDE.md`) se charge dès
que l'agent travaille sous ce dossier. À créer dès qu'un composant a ses propres commandes et au
moins une règle qui ne vaut pas ailleurs ; jamais pour répéter la racine. **Pas dans un dossier
qui finit dans un artefact publié** (le paquet d'une bibliothèque, `src/<pkg>/`, un dossier
servi tel quel) : le fichier y serait distribué — utiliser alors une règle par chemins (§3).
Gabarit (WP-D, un par composant de `COMPONENTS` qui le justifie) :

````markdown
# <component> — <stack, version>

> Scope: <what lives here>. Root rules in `/CLAUDE.md` still apply.

## Read the wiki first
- `.llmwiki/<Page>.md` · `.llmwiki/<Page>.md`
- <Procedure X> is a skill: `<skill>`. Do not improvise its steps.

## Commands
```bash
<setup> · <run> · <test> · <lint/format/types>   # the same ones scripts/check.sh runs
```

## Rules
1. **<Rule>.** <Why.>  <!-- e.g. config template kept in sync with the settings loader -->

## Gotchas
- <symptom> → <cause> → <fix>
````

## 5. Agents : ceux du plugin, et comment un projet les remplace

Le bootstrap n'écrit **aucun** fichier dans `.claude/agents/`. Les agents viennent du plugin,
avec des modèles fixés par lui :

| `subagent_type` | Modèle, effort | Rôle |
|---|---|---|
| `shipyard:implementer-complex` | sonnet, high | une PR notée complexe à la planification |
| `shipyard:implementer-simple` | sonnet, low | une PR notée simple |
| `shipyard:reviewer` | sonnet, high | revue indépendante des lanes B et C, en lecture seule |
| `general-purpose` + `model: "haiku"` | haiku | une unité de volume, lancée par l'orchestrateur |

Tous les trois portent `isolation: worktree`.

**Pourquoi des définitions et pas un `model` par appel.** L'outil Agent accepte un `model` par
appel, mais l'*effort* ne vient que d'une définition ; et un `model` passé à l'appel **écrase**
celui de la définition — `ship-parallel` n'en passe donc aucun quand il lance ces agents. Une
session où le plugin n'est pas chargé ne voit pas ces définitions : `ship-parallel` retombe alors
sur `general-purpose` avec `model: "sonnet"` (sans effort), et le dit dans son rapport. Les hooks
jugent le dossier de travail, jamais le type d'agent : `SubagentStop` s'applique à ces agents
comme aux autres.

**Remplacer un agent.** Un projet qui veut un autre modèle ou d'autres consignes **n'édite pas
le plugin** (la modification serait perdue à la mise à jour et ferait du projet une variante) :
il écrit son propre agent sous un nom à lui, `.claude/agents/<kebab-case>.md` — en partant de la
définition du plugin, `model` et `effort` changés —, l'inscrit dans `.llmwiki/Project.md` §
Agents avec sa raison, et `ship-parallel` lance alors ce nom. Une session qui démarre avant que
ce fichier existe ne le voit pas : le changement vaut à partir de la session suivante.

## 6. Où va quoi

| Nature de l'information | Où | Pourquoi là |
|---|---|---|
| Ce que *chaque* session doit appliquer sans réfléchir | `CLAUDE.md` (budgété) | chargé à chaque session ; chaque ligne coûte à chaque tour |
| Faits durables (architecture, schéma, décisions et leur pourquoi) | `.llmwiki/<Page>.md` | un propriétaire par fait, chargé à la demande |
| Procédure répétable propre au projet (déployer, migrer, publier) | `.claude/skills/<nom>/` | déclenchable, numérotée, citée `§N` |
| Procédure de livraison commune (livrer en parallèle, trier le backlog, rejoindre l'équipe) | skill du plugin `/shipyard:…` | écrite et testée une fois pour tous les projets ; réglée par `tooling.conf` |
| Règle décidable par un script, commune à tous les projets | hook du plugin + une ligne dans `.llmwiki/Hooks.md` | appliquée même quand personne n'y pense ; la changer = une version du plugin |
| Règle décidable par un script, propre au projet | `scripts/check.sh fast` + `.llmwiki/Testing.md` § Gates | le garde de commit du plugin l'appelle ; une seule définition des gates |
| Valeur partagée par des scripts, hooks et skills | `scripts/lib/tooling.conf` | une seule source, commentée clé par clé |
| Script que la CI ou l'humain lance sans Claude | copie vendorisée (`scripts/`, listée dans `VENDORED.json`) | identique au gabarit du plugin ; jamais éditée, synchronisée par `/shipyard:sync-tooling` |
| Règle d'un sous-arbre | `CLAUDE.md` de composant ou `.claude/rules/` | chargée seulement là où elle sert |
| Qui possède quel chemin (équipe) | `.github/CODEOWNERS` + `.llmwiki/Team.md` | lu par GitHub, par `scripts/owners.py` et par les agents ; changé par une PR approuvée |
| Travail à faire, problème constaté, idée | `wip/<dossier>/<date>-<slug>.md` | un fichier par entrée : zéro conflit entre PR |
| Préférences personnelles, permissions accumulées | `.claude/settings.local.json` | gitignoré |
| Ce que Claude retient d'une conversation à l'autre (mémoire automatique) | la mémoire de l'utilisateur | **jamais** ce que le dépôt enregistre déjà (structure, décisions, procédures, historique git) : une mémoire qui double le dépôt finit par le contredire |

Ce que le wiki dit de cette configuration — réglages et posture de permissions, routage des
modèles, budget de `CLAUDE.md` — est donné à WP-D par l'annexe 04.

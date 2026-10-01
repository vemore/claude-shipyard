# Annexe 6 — Wiki (`.llmwiki/`) et backlog (`wip/`)

> Pour **WP-D** (pages, `Team.md` en équipe, `wip/`, backlog initial) et l'orchestrateur
> (`.llmwiki/Project.md`, lignes de `.gitignore` §6). Le §5 décrit le comportement des scripts
> vendorisés `scripts/wiki_lint.py` et `scripts/wip.py`, pour que les pages et les entrées que
> WP-D écrit les passent du premier coup. Les gabarits en anglais sont à recopier tels quels — à
> traduire dans la langue de la doc du projet si ce n'est pas l'anglais.
> Les `<…>` des gabarits sont à remplacer ; un fichier généré ne mentionne jamais « annexe » :
> le projet n'aura pas ces annexes.

## 1. Conventions de `.llmwiki/`

**Ce que c'est.** Un dossier plat de pages Markdown que les agents lisent avant d'agir : la
mémoire durable du projet (*ce qui est* et *pourquoi*), à côté des skills (*comment faire*). On
suit le patron « LLM wiki » : un changement de fait est une ingestion, les réponses se
capitalisent, un lint garde la forme. Volontairement **pas** adoptés : un `log.md` (l'historique
git du dossier le donne déjà), un moteur de recherche (l'index et `grep` suffisent à cette
taille), un frontmatter YAML (rien ne l'interroge).

Les dix conventions, à recopier dans la section `## Conventions` d'`INDEX.md` :

1. `[[Name]]` renvoie à `.llmwiki/<Name>.md`. Un lien pendant signale une page qui mériterait
   d'exister, pas une erreur (le lint le note sans échouer).
2. Un fait porte sa source (`src/config.py:44`). Les valeurs sont verbatim : si le code dit
   `8192`, on écrit `8192`, jamais « environ 8k ». Pourquoi : un agent recopie ce qu'il lit.
3. Toute page finit par `## Decisions & History` : le *pourquoi* des faits, pas leur
   reformulation. Pourquoi : sans raison, un garde-fou est retiré comme redondant.
4. Un fait devenu faux et qu'on ne peut pas corriger tout de suite n'est pas réécrit en silence :
   il reçoit juste en dessous `> **Status: Outdated** (YYYY-MM-DD) — what changed, and what now holds.`
   Ces blocs sont repliés lors de la passe d'élagage (§3). Un fait qu'on *peut* corriger se
   corrige directement : git garde l'ancien.
5. **Un propriétaire par fait.** Un fait vit sur une page ; les autres y renvoient, ne le
   répètent pas.
6. **Changer un fait est une ingestion.** `grep -rn` l'ancienne valeur dans `.llmwiki/` et
   corriger chaque page qu'elle falsifie, dans le même changement, chacune avec sa date
   `Updated:` et sa ligne d'INDEX.
7. **Les réponses se capitalisent.** Une synthèse que la tâche suivante devrait sinon
   reconstruire (cause racine, comparaison, mesure) va dans la page qui possède le sujet, dans la
   même PR — pas seulement dans le chat ou le corps de la PR.
8. Deux pages en désaccord qu'on ne peut pas trancher maintenant : `> **Status: Contradicted**
   (YYYY-MM-DD) — see [[Other]]` sur les deux, plus une entrée `wip/`.
9. **Budgets** : une ligne d'INDEX tient en 25 mots au plus ; une page reste sous
   `WIKI_PAGE_BUDGET` lignes (`scripts/lib/tooling.conf`) — au-delà, on la scinde par sous-sujet
   et on laisse un renvoi.
10. Pas de code collé dans une page : on pointe le fichier et la ligne. Pourquoi : le code
    collé est la première chose qui ment.

**Procédures dans les skills, faits dans le wiki.** Une page décrit ce qui est ; une suite
d'étapes à exécuter est un skill — du plugin (`/shipyard:…`) ou du projet (`.claude/skills/`) —,
que la page cite (« for the procedure, use the `<skill>` skill »). `CLAUDE.md` ne garde qu'une
ligne par règle transversale, avec le renvoi.

### Gabarit d'`INDEX.md` (verbatim)

```markdown
# Wiki index

Load this file first. Then read only the pages your task touches.

## Conventions

<the ten conventions, in the project's documentation language>

## Overview

| Page | Summary | Updated |
|---|---|---|
| [[Project]] | Decisions taken at bootstrap and since: scope, stack, autonomy, thresholds. | YYYY-MM-DD |
| [[Architecture]] | Components, data flow, where things live. | YYYY-MM-DD |
| [[Team]] | Who owns which area, how to join, who reviews what. | YYYY-MM-DD |
| [[KnownLimits]] | Limits deferred on purpose, and what is missing rather than deferred. | YYYY-MM-DD |

## Engineering

| Page | Summary | Updated |
|---|---|---|
| [[Testing]] | What each test and selftest covers, the gates, how CI scopes jobs. | YYYY-MM-DD |
| [[Hooks]] | What the shipyard plugin's hooks refuse, on what evidence, and what they do not cover. | YYYY-MM-DD |
| [[Security]] | Secrets, what never goes in a tracked file, dependency scanning. | YYYY-MM-DD |

## Delivery

| Page | Summary | Updated |
|---|---|---|
| [[ParallelDelivery]] | Worktrees, lanes, model routing, serial squash merges, cleanup. | YYYY-MM-DD |
| [[Deployment]] | What a merge deploys, how, how to roll back. | YYYY-MM-DD |
| [[Documentation]] | When a change must update README and the wiki; budgets; the pruning pass. | YYYY-MM-DD |

## Procedures live in skills, not here

These pages describe *what is*. For *how to do*, use the skills: `/shipyard:ship-parallel`,
`/shipyard:wip-refine`, `/shipyard:sync-tooling`<, `/shipyard:join`> from the shipyard plugin<;
`deploy`, `release`, any project skill in `.claude/skills/`>.
```

La ligne `[[Team]]` et `/shipyard:join` n'existent qu'en équipe (`TEAM_MODE=team`) ; la ligne
`[[Deployment]]` et le skill `deploy`, que si le projet a une cible de déploiement ; `release`,
que si `RELEASE_MODE=planned`. La date de la colonne `Updated` est **identique** à la ligne
`> Updated:` de la page (le lint compare).

### Gabarit de page (verbatim)

```markdown
# <PageName>

> Scope: <what this page owns, one or two lines>. [For the procedure, use the `<skill>` skill.]
> Related: [[A]] · [[B]] · [[C]]
> Updated: YYYY-MM-DD

## Facts

### <sub-topic>

<facts with `path:line` sources, verbatim values; tables welcome>

## Decisions & History

- **<Decision title> (YYYY-MM-DD).** <why; the evidence (incident, PR number, wip/done/ entry);
  the alternatives rejected and why>.
```

Les trois lignes d'en-tête sont des citations `>` dans cet ordre ; `> Updated:` est la première
ligne de la page qui commence ainsi (le lint la lit). Une page peut ajouter `> Procedure: the
<skill> skill.` après `Related`. `Decisions & History` est narratif et daté ; le plus récent en
bas.

## 2. Pages initiales (WP-D)

WP-D écrit toutes les pages sauf `Project.md` (écrite par l'orchestrateur avant le fan-out :
WP-D la lit et la lie, ne la modifie pas). WP-D travaille **en parallèle** de WP-A : les chemins
de code qu'il cite sont ceux que `Project.md` fixe (répertoire de chaque composant) ; le lint
(chemins morts) attrape un écart à l'intégration. Chaque page reçoit les raisons semées depuis
l'annexe 01 §9.

| Page | Contenu exigé | Alimentée par |
|---|---|---|
| `INDEX.md` | gabarit §1, une ligne par page existante, liste des skills réellement présents (plugin et projet) | `Project.md` |
| `Project.md` | *orchestrateur* : but, stack, composants et leurs répertoires, forge, mode solo ou équipe, autonomie accordée (`AUTONOMY`), mode de release (`RELEASE_MODE`) et release ou jalon en cours, chemins lane C, noms des jobs CI, agents, niveau d'outillage, langue de doc, posture de permissions, version de shipyard vendorisée ; chaque décision avec sa raison | questionnaire (annexe 02) |
| `Architecture.md` | composants (id de `COMPONENTS`, répertoire, langage, points d'entrée), flux de données (liste ou schéma ASCII), services externes, stockage, variables d'environnement (noms seulement, renvoi à `.env.example`), table « où vivent les choses », invariants | `Project.md`, description de l'utilisateur |
| `Hooks.md` | les hooks du plugin vus du projet : ce qui est configuré, quel dépôt un hook juge, ce qui est refusé et sur quelle preuve, échappatoires, ce qu'ils ne couvrent pas, où ils sont testés | annexe 04 §2 |
| `ParallelDelivery.md` | protection de la branche par défaut (valeurs attendues) ; worktrees et checkout principal ; nettoyage ; lanes A–D avec `LANE_C_RE` et `SIZE_THRESHOLD` ; calibration du relecteur ; routage de modèles ; merges ; « merged, not deployed » ; métriques (Complet) | annexe 04 §4 |
| `Documentation.md` | §3 ci-dessous | cette annexe, annexe 04 §5 |
| `Testing.md` | ce que couvre chaque fichier de test et de selftest (par fichier, jamais un compte : les comptes dérivent) ; cibles de `scripts/check.sh` ; jobs CI et scope ; copies vendorisées ; trous connus | annexe 04 §3 |
| `KnownLimits.md` | deux sections, « Deferred on purpose » et « Missing rather than deferred » ; au bootstrap : ce que le scaffold ne fait pas encore, la protection de branche si indisponible. Sa `Decisions & History` dit : « this page is not a backlog — actionable work belongs in `wip/` » | orchestrateur, rapports des lots |
| `Security.md` | ce qui est suivi et ce qui ne l'est pas (`.env.example` vs `.env`, `DEPLOY_ENV_FILE`) ; ce qui n'entre jamais dans un fichier suivi (hôte réel, jeton, clé, chemin personnel) ; détection par chemin **et** contenu ; secrets liés seulement par `worktree_setup.sh --deploy` ; dépôt public = tout push est publié ; scan de dépendances et ignores avec expiration + entrée `wip/` | annexe 04 §5 |
| `Deployment.md` | *seulement s'il y a une cible* : topologie en une ligne, ce que chaque chemin déclenche (`DEPLOY_PATHS_RE`), le skill `deploy`, la sonde, le rollback, « merged, not deployed » ; jamais d'hôte réel | annexe 04 §5 |
| `Team.md` | *seulement en équipe* : gabarit ci-dessous | `Project.md` (la zone déclarée au questionnaire), `.github/CODEOWNERS` |

**Titres fixes.** Les skills — ceux du plugin compris, qui lisent ces pages — et les autres
pages citent des sections par leur titre (« `ParallelDelivery.md` § Reviewer calibration ») :
ces `###` existent tels quels, en anglais même si la doc est dans une autre langue (ce sont des
ancres), dans cet ordre :

| Page | Sous-sections `###` de `## Facts` |
|---|---|
| `Hooks.md` | `What is configured` · `Which repository a hook judges` · `What is refused` · `What the hooks do not cover` · `Self-test` |
| `ParallelDelivery.md` | `Protection of the default branch` · `Worktrees` · `Cleanup` · `Lanes` · `Reviewer calibration` · `Model routing` · `Merges` · `Merged, not deployed` (si cible) · `Measuring delivery` (Complet) |
| `Testing.md` | `What each test file covers` · `Gates` · `CI` · `Selftests` · `Known gaps` |
| `Documentation.md` | `README triggers` · `Documents that move together` · `Budgets` · `Lint` · `Pruning pass` · `Skill conventions` |
| `Team.md` | `Members` · `How to join` · `Who reviews what` |

### Gabarit de `Team.md` (équipe seulement, verbatim)

Le skill `/shipyard:join` **édite le tableau `### Members`** : ses colonnes, leur ordre et le
format des cellules sont fixes. Une ligne par membre ; `Login` est le login GitHub avec son `@` ;
`Areas` liste ses motifs CODEOWNERS, chacun entre backticks, séparés par des virgules, tels
qu'ils figurent dans `.github/CODEOWNERS` ; `Since` est la date de la PR qui l'a ajouté.
`.github/CODEOWNERS` fait foi pour GitHub et `scripts/owners.py` ; ce tableau en est la
lecture humaine, et les deux changent dans la même PR.

```markdown
# Team

> Scope: who owns which area of this repository, how a new teammate joins, and who reviews
> what. The machine copy is `.github/CODEOWNERS`; this page owns the reasons.
> Procedure: the `/shipyard:join` skill.
> Related: [[Project]] · [[ParallelDelivery]] · [[Hooks]]
> Updated: YYYY-MM-DD

## Facts

### Members

| Login | Areas (CODEOWNERS patterns) | Since |
|---|---|---|
| @<login> | `/<component-dir>/`, `/.claude/`, `/scripts/`, `/.github/`, `/CLAUDE.md` | YYYY-MM-DD |

### How to join

Run `/shipyard:join` in this repository. It asks which areas you will own, confirms your GitHub
login, adds you to `.github/CODEOWNERS` and to the table above on a fresh `docs/join-<login>`
branch, and opens the pull request. That pull request touches `.github/CODEOWNERS`, which the
current owners own: it waits for their approval like any change to someone else's area. Until it
merges, the session-start message reminds you that you own nothing yet.

### Who reviews what

- A pull request is reviewed by the owners of every area its diff touches: GitHub requests
  their review from `.github/CODEOWNERS` (last matching pattern wins), and `scripts/owners.py`
  gives the same answer locally (`git diff --name-only origin/<default>...HEAD | scripts/owners.py`).
- A pull request that touches an area you do not own merges only after one owner of each such
  area approves it; the orchestrator does not merge it before, and never routes around it. Your
  other pull requests carry on meanwhile.
- An owner's approval stands for the lane C go-ahead on that owner's paths.
- The tooling paths (`/.claude/`, `/scripts/`, `/.github/`, `/CLAUDE.md`) belong to the
  person who bootstrapped the project until the team decides otherwise, by a pull request to
  `.github/CODEOWNERS`. `wip/` and `.llmwiki/` are shared and have no owner: almost every pull request touches them (closing its entry, updating the page it makes false), so an owner of them would have to approve every teammate's pull request.
- Approval is a process, not a branch rule: the default branch does not require code-owner
  reviews. Making it a rule (`require_code_owner_reviews`) is a team decision for when every
  area has at least two owners — before that, an owner could not merge their own pull requests.

## Decisions & History

- **The owner of a path decides on changes to it (<bootstrap date>, inherited at bootstrap).**
  Several people launch agents in parallel; without an owner, a pull request can rewrite an
  area its author only knows from the code, without the decisions behind it.
- **Ownership is declared by each person and versioned in git (<bootstrap date>, inherited at
  bootstrap).** Scripts and agents must read it (`scripts/owners.py`), and an ownership guessed
  from `git blame` is wrong in silence; a declaration goes through a pull request the current
  owners approve, and git keeps who owned what since when.
- **Process before branch protection (<bootstrap date>, inherited at bootstrap).** GitHub does
  not let the author approve their own pull request: a required code-owner review would stop a
  sole owner from merging their own work on their area. The rule lives in `ship-parallel` first;
  the branch rule is added only once every area has several owners.
```

Le dernier point de `Who reviews what` suit le choix fait au questionnaire (`Project.md`) ;
garder la variante qui s'applique et retirer les chevrons. Les motifs entre backticks qui
commencent par `/` ne sont pas soumis au contrôle des chemins morts du lint (il ne vérifie que
ceux qui commencent par une racine de `DEAD_PATH_ROOTS`).

## 3. Contenu de `Documentation.md`

**Table de déclenchement du README** (« ce que tu as changé → ce qu'il faut vérifier dans
`README.md` ») — à recopier et adapter :

| Changed | Check in README.md |
|---|---|
| Toolchain or runtime version | Requirements section |
| A dependency added or removed | Requirements, install steps |
| A step needed to build or run a fresh clone | Setup — **a missing step is a defect, not a doc nit** |
| A build, run or test flag | Commands |
| A new top-level directory | Layout |
| A CI job added, renamed or removed | CI / contributing section |
| Supported platforms or browsers | Requirements |
| A new outbound data flow (network call, telemetry, third-party service) | Privacy / data section, plus every document in "Documents that move together" |
| A user-visible feature | Features |
| An environment variable or config key | Configuration, and `.env.example` |

Règles : vérifier contre la source, jamais contre l'ancien README ; si le changement ne falsifie
rien dans la table, le README n'a pas à bouger — et le dire dans la PR. Pourquoi : dans un
projet antérieur, le README a dérivé dix mois faute de déclencheur explicite. Le README d'un
clone neuf dit aussi, dans `Setup` : installer le plugin `shipyard` (ou accepter la proposition
de Claude Code à l'ouverture du dossier), `git config core.hooksPath .githooks`, puis
`scripts/worktree_setup.sh .`.

**Documents qui bougent ensemble.** Si `Project.md` liste des documents liés (politique de
confidentialité, inventaire des données, déclaration de permissions, fiche d'un store), tout
nouveau flux de données sortant les met **tous** à jour dans la même PR. Pourquoi : une
fonctionnalité qui envoyait des données a été livrée alors que la déclaration publique disait
que rien ne quittait l'appareil. La liste est vide par défaut ; l'orchestrateur la remplit si
le questionnaire en révèle.

**Budgets** : `CLAUDE_MD_BUDGET` lignes pour `CLAUDE.md` (défaut 120), `WIKI_PAGE_BUDGET` pour
une page. `CLAUDE.md` garde ce dont chaque session a besoin ; le reste va dans la page qui le
possède. La ligne de budget est écrite en tête de `CLAUDE.md` (annexe 04 §5).

**Le lint, en trois parties :**
- *Scripté* (`scripts/wiki_lint.py`, §5.1, **bloquant en CI dès le premier jour** — un projet
  neuf n'a aucune dette à absorber ; un projet antérieur, qui l'avait adopté tard, a dû le
  laisser non bloquant) : budgets, chemins morts, `file:line` au-delà de la fin du fichier,
  dates INDEX/page, pages absentes de l'INDEX, en-têtes et section finale manquants ; notes
  (non bloquantes) pour les liens pendants et les blocs `Status`.
- *Mécanique, à la main* : `Updated:` plus ancien que le dernier commit des sources citées.
- *Jugement* : contradictions entre pages ; « réponses reconstruites » (une synthèse qui ne vit
  que dans une PR ou une entrée `wip/done/`).

**La passe d'élagage** — avant chaque release (`RELEASE_MODE=planned`), ou, en livraison
continue, toutes les `PRUNE_EVERY_MERGES` PR mergées (`tooling.conf`, défaut 30) ou à un
refinement si celui-ci vient avant. La procédure est `/shipyard:wip-refine` §8 (le skill
`release` du projet la lance avant de couper une version). La page en dit le principe :
1. Lister chaque règle de `CLAUDE.md`, chaque skill du projet et chaque refus de hook ; chercher
   une preuve qu'il a servi depuis la dernière passe (entrées `wip/`, PR, commits qui le citent).
   Proposer de retirer ceux sans preuve. Un refus de hook vient du plugin : sans preuve, il
   devient une entrée `wip/` (`Area: tooling`) qui le signale pour le plugin, jamais une
   suppression locale.
2. `wc -l CLAUDE.md` contre le budget ; pages au-delà de `WIKI_PAGE_BUDGET` à scinder.
3. Replier les blocs `Status: Outdated` / `Contradicted` réglés.
4. Niveau Complet, si les mesures sont installées : métriques de livraison contre la base.
5. La passe **propose** ; l'utilisateur décide (un `AskUserQuestion` multi-choix) ; les retraits
   forment leur propre PR `chore/prune-<YYYY-MM-DD>`.
Pourquoi : sans elle, chaque incident devient une règle et aucune ne part.

**Conventions des skills de projet** (à recopier sous `### Skill conventions`, pour que les
skills créés plus tard les suivent) :
- un skill naît de la répétition : une procédure faite deux fois à la main devient un skill à
  la troisième, dans sa propre PR ; jamais un skill spéculatif ;
- `name` = nom du dossier, kebab-case ; `description` = « <what it does> — <its steps or
  scope>. Use when <situations>. Triggers: "<phrase>", … », 300 à 700 caractères, qui nomme les
  capacités sortantes ou destructrices ; `disable-model-invocation: true` pour un skill dont
  l'effet principal est sortant et qui ne part que sur demande ;
- sections numérotées citables (`§3`, `§3b` plutôt que renuméroter), le piège d'abord
  (`## The one rule you cannot break`), `## When NOT to use this skill` si un voisin couvre un
  cas proche, `## Checklist` en fin de skill opérationnel ;
- les faits dans le wiki, la procédure dans le skill ; chaque règle porte sa raison ; les
  actions sortantes : valider, rapporter, puis exécuter sur le feu vert ;
- scripts sous `.claude/skills/<skill>/scripts/`, appelés par ce chemin complet depuis la racine,
  chacun avec son `test_<nom>.py` à côté (lancé par `scripts/selftest.sh`) ; `SKILL.md` ≤ 500
  lignes ;
- un skill est listé dans `CLAUDE.md` et dans la dernière section d'`INDEX.md`, sinon il n'est
  jamais cherché ;
- les skills du plugin (`/shipyard:…`) ne se copient ni ne se modifient : leur comportement se
  règle par `tooling.conf` et par ces pages ; un besoin qu'ils ne couvrent pas est une entrée
  `wip/` (`Area: tooling`).

## 4. Le système `wip/`

**Dossiers** — chacun contient un `.gitkeep`, car git ne suit pas les dossiers vides (un projet
antérieur a perdu `wip/todo/` et un eval qui écrivait dedans a cassé) :

| Dossier | Contient |
|---|---|
| `wip/todo/` | travail ouvert pour la release — ou le jalon — en cours ; au plus `WIP_LIMIT` entrées |
| `wip/todo_nr/` | travail ouvert pour la suivante ; **défaut de tout nouveau constat** |
| `wip/done/` | entrées closes **et** abandonnées |
| `wip/assets/<entry-slug>/` | images liées par une entrée (`../assets/<slug>/x.png`) ; ne bouge pas quand l'entrée bouge |

**Pas de fichier d'index** : ce serait de nouveau le fichier que toutes les PR touchent.
`scripts/wip.py list` est l'index. « Release » désigne la release ou le jalon en cours que
`Project.md` nomme ; le champ s'appelle `Blocks release` dans les deux cas, pour que l'outil ne
change pas.

**Nommage** : `wip/<dossier>/YYYY-MM-DD-<slug>.md`, la date du jour où le problème est noté, un
slug `[a-z0-9-]+` qui ne change **jamais** — c'est ce qui permet à deux branches qui touchent
deux entrées différentes de ne jamais entrer en conflit.

### Gabarit d'entrée (verbatim)

```markdown
# <What is wrong, as a statement>

- **Noted:** YYYY-MM-DD — <while doing what>
- **Theme:** <one tag; reuse an existing one: scripts/wip.py themes all>
- **Area:** <a component id from COMPONENTS> | tooling | docs | ci | infra
- **Blocks release:** yes — <why> | no

<The problem, with file paths and evidence (a line, a command output, a PR).>

**Fix:** <the proposed change>
**State of the art:** <only for a common, non-project-specific subject: current practice,
sources, date consulted, where the fix departs from it and why>
**Acceptance:** <2–5 checkable statements; optional to write an entry, required to promote it>
**Open question:** <what the user must decide>
```

Une entrée tient en une vingtaine de lignes. Les mentions en gras sont un guide, pas un schéma :
`wip.py` accepte aussi les titres `##` et les synonymes (§5.2). `Theme` est ce qui regroupe des
entrées dans une même PR ; `Area` dit quel composant ou quelle couche.

**Où va un nouveau constat.** Un problème qu'une tâche fait apparaître sans qu'on ait demandé de
le corriger n'est ni corrigé en passant ni abandonné : il devient une entrée, et la tâche
continue. Dans `todo_nr/` par défaut ; dans `todo/` seulement s'il bloque la release, c'est-à-dire
dans l'une de ces classes : **sécurité, crash, perte de données, obligation légale ou politique
d'un store/d'une plateforme**. Pourquoi ce défaut : sinon le périmètre de la release grandit à
chaque session.

**Entrées outillage.** Un skill, un hook, une commande, une procédure de wiki ou une règle de
`CLAUDE.md` qu'il a fallu contourner est un constat comme un autre (`Area: tooling`). Le
correctif proposé **peut être une suppression** ; préférer remplacer une règle à en ajouter une
à côté. Exception : une correction d'une ligne que la tâche en cours prouve fausse (une commande
mal orthographiée dans un skill du projet) se fait sur place ; tout ce qui change *ce que fait*
un outil est une proposition. Un défaut du plugin (un hook, un skill `/shipyard:…`, une copie
vendorisée) n'est **jamais** corrigé dans le projet : l'entrée nomme la version du plugin
(`scripts/lib/VENDORED.json`) et ce qui s'est passé.

**Cycle de vie.**
- Tout déplacement est un `git mv` ; le nom ne change jamais.
- **Clore dans la PR qui corrige** : `git mv wip/todo/X.md wip/done/X.md`, puis, juste sous le
  titre : `**Status:** done (YYYY-MM-DD) — closed by <branch or #PR>. <one or two sentences>`.
- Partiellement fait : l'entrée reste ouverte et ne garde que ce qui reste.
- **Abandonner** est aussi un déplacement vers `done/` :
  `**Status:** dropped (YYYY-MM-DD) — <why, or: merged into [[<surviving-entry-file-name>]]>`.
  Pourquoi : `done/` garde ce qui a été écarté à côté de ce qui a été livré ; une idée qui
  revient retrouve son historique.
- **On ne supprime jamais une entrée, et on n'édite jamais une entrée qu'une autre PR possède.**
  Pourquoi : c'est la seule source de conflit possible dans `wip/`. Le hook Bash du plugin refuse
  la suppression d'une entrée et l'ajout d'un `TODO.md` racine.

**Promotion `todo_nr/` → `todo/`.** C'est le **point d'engagement** : avant, une entrée est une
option, bon marché à écrire et à abandonner ; après, elle fait partie de la release. Elle est
décidée par une passe de refinement (`/shipyard:wip-refine`), lancée après chaque release, quand
`todo_nr/` dépasse `REFINE_THRESHOLD` entrées, ou sur demande. L'utilisateur décide ; la passe
propose.

**Définition de « ready »** — les six conditions pour être promue (pas pour être écrite) :
1. **Toujours vraie**, avec une preuve (une ligne, un commit, une sortie de commande).
2. **Une PR** : un `**Fix:**` concret, environ une journée, une seule raison de revert. Plus
   gros : on scinde.
3. **Testable** : `**Acceptance:**` porte 2 à 5 énoncés vérifiables.
4. **Débloquée** : aucune question ouverte ni dépendance non livrée.
5. **Thématisée** : réutilise une étiquette existante (`scripts/wip.py themes all`).
6. **Ancrée, si le sujet est commun** (sauvegarde, migrations, cache, authentification, CI…) :
   une section `**State of the art:**` — pratique actuelle, sources, date de consultation, et en
   quoi le correctif s'en écarte et pourquoi.

Les lanes B et C (`/shipyard:ship-parallel` §1) exigent les critères d'acceptation avant le
lancement de la PR.

### Gabarit de `wip/README.md` (verbatim)

```markdown
# wip/ — work tracking

One file per entry. No shared list and no index file: two pull requests collide here only
when they touch the same entry, and none ever should.

## Folders

| Folder | Holds |
|---|---|
| `todo/` | Open work for the release (or milestone) in progress — at most `WIP_LIMIT` entries (`scripts/lib/tooling.conf`). |
| `todo_nr/` | Open work for the next one. **The default for any new finding.** |
| `done/` | Closed and dropped entries. |
| `assets/<entry-slug>/` | Images an entry links as `../assets/<slug>/x.png`; the folder stays put when the entry moves. |

Every folder holds a `.gitkeep`: git does not track empty directories, and a missing `todo/`
breaks every tool that writes into it. `scripts/wip.py list` is the index.

## Writing an entry

Name it `<folder>/YYYY-MM-DD-<slug>.md` — the date the problem was noted, and a slug that never
changes. About twenty lines:

<the entry template above, verbatim>

A problem a task surfaces but was not asked to fix is neither fixed inline nor dropped: it
becomes an entry, and the task carries on. It goes to `todo_nr/`, or to `todo/` only if it
blocks the release: security, crash, data loss, legal or platform policy.

A skill, hook, command, wiki procedure or `CLAUDE.md` rule that had to be worked around is a
finding too (`Area: tooling`). The fix may be a removal; prefer replacing a rule to adding one
next to it. A defect of the shipyard plugin itself is never fixed here: the entry names the
plugin version recorded in `scripts/lib/VENDORED.json`.

## Closing, dropping, moving

- Every move is a `git mv`; the file name never changes.
- Close an entry in the pull request that fixes it: move it to `done/` and add, right under the
  title, `**Status:** done (YYYY-MM-DD) — closed by <branch or #PR>. <one or two sentences>`.
- Partly done stays open, keeping only what is left.
- Dropping is a move to `done/` too: `**Status:** dropped (YYYY-MM-DD) — <why, or: merged into
  [[<entry-file-name>]]>`.
- Never delete an entry, and never edit one that another pull request owns.

## From todo_nr/ to todo/

The move is the commitment point, decided by a refinement pass (`/shipyard:wip-refine`) after
each release, when `todo_nr/` passes `REFINE_THRESHOLD` entries, or on request. The pass
proposes; the user decides. An entry is promoted only when it is ready: still true (with
evidence), one pull request, 2–5 acceptance statements, unblocked, themed with an existing tag,
and grounded in current practice when the subject is a common one.

## Commands

    scripts/wip.py list [todo|todo_nr|done|all]     # by folder, then theme; ! marks a release blocker
    scripts/wip.py themes [todo|todo_nr|done|all]   # theme counts
    scripts/wip.py check                            # format check, run in CI
    scripts/wip.py refine [todo|todo_nr|all]        # signals for a refinement pass
```

## 5. Les scripts vendorisés `wiki_lint.py` et `wip.py`

Copiés du plugin, à l'identique, avec leurs selftests (`scripts/selftest/test_wiki_lint.py`,
`scripts/selftest/test_wip.py`) ; le projet ne les écrit ni ne les modifie. Ils se comportent
comme suit — WP-D écrit pages et entrées pour qu'ils passent, et un écart entre ce texte et
l'en-tête du script se tranche en faveur du script (et se signale dans le rapport). Ils lisent
`scripts/lib/tooling.conf` du dépôt où ils s'exécutent ; sortie 2 si elle est illisible.

**Chemin mort** (règle commune, `scripts/lib/dead_paths.py`) : dans le texte, un segment entre
backticks simples dont le contenu commence par `(<DEAD_PATH_ROOTS>)/` ; ignoré s'il contient
`*`, `?`, `<`, `>`, `{`, `}`, `$`, une espace, ou `...` ; un suffixe `:<ligne>` ou `:<l1>-<l2>`
(gardé pour la vérification de ligne), un `#ancre` et un `/` final sont retirés ; résolu depuis
la racine du dépôt ; mort s'il n'existe pas. Les blocs de code clôturés (```` ``` ````) sont
ignorés en entier : ils contiennent des exemples, pas des références. Conséquence pour WP-D : un
chemin qu'un autre lot n'a pas encore écrit (un fichier de WP-A) reste juste s'il figure dans
`Project.md` ; un chemin d'exemple va entre chevrons ou dans un bloc de code.

### 5.1 `scripts/wiki_lint.py [WIKI_DIR]`

Défaut `WIKI_DIR` = `.llmwiki` à la racine du dépôt. Sortie : une ligne par constat
`<page>[:<ligne>]: <message>`, les notes préfixées `note: `, puis un total
`<N> finding(s), <M> note(s)`. Codes : **0** aucun constat (des notes peuvent exister), **1** au
moins un constat, **2** pas d'`INDEX.md`. Les notes ne changent jamais le code de sortie.

Constats (bloquants) :
1. Page (hors `INDEX.md`) de plus de `WIKI_PAGE_BUDGET` lignes.
2. Chemin mort (règle commune ci-dessus), et `chemin:<ligne>` au-delà de la fin du fichier.
3. Page sans ligne `> Updated: YYYY-MM-DD` (date valide), ou sans titre `## Decisions & History`.
4. Ligne d'INDEX `| [[X]] | <résumé> | <date> |` dont la date diffère de la ligne `> Updated:` de
   `X.md` ; ligne d'INDEX vers une page inexistante ; résumé de plus de 25 mots.
5. Page `*.md` du dossier (hors `INDEX.md`) absente de l'INDEX.

Notes (non bloquantes) :
- Bloc `> **Status: Outdated** (YYYY-MM-DD)` ou `> **Status: Contradicted** (YYYY-MM-DD)` : la
  passe d'élagage les replie. Un `YYYY-MM-DD` littéral dans un texte de convention ne correspond
  pas.
- Lien pendant `[[Name]]` : un lien collé à un backtick est un exemple de convention, ignoré.

Non vérifié : contradictions entre pages, `Updated:` plus ancien que les sources citées,
réponses reconstruites, liens externes (un vérificateur de liens lancé sur chaque PR est une
primitive de requêtes sortantes pilotée par le contenu du dépôt).

### 5.2 `scripts/wip.py <commande> [todo|todo_nr|done|all]`

Analyse commune d'une entrée :
- `README.md`, `.gitkeep`, tout ce qui est sous `wip/assets/`, et `ARCHIVE-*.md` sont ignorés ;
- titre = première ligne non vide commençant par `# ` ;
- métadonnées : lignes `- **Noted:**`, `- **Theme:**`, `- **Area:**`, `- **Blocks release:**`
  (la valeur commence par `yes` ou `no`, insensible à la casse) ;
- statut : `**Status:** done|dropped` (éventuellement en puce `- `) dans les six premières lignes
  non vides ;
- sections : `**<label>:**` ou `## <label>` (`#` à `####`, deux-points facultatif, insensible à
  la casse), avec ces synonymes :
  - Fix : `fix`, `proposed fix`, `fix proposé`, `correctif`, `correctif proposé`
  - Acceptance : `acceptance`, `acceptance criteria`, `acceptation`, `critères d'acceptation`
  - Open question : `open question`, `open questions`, `question ouverte`, `questions ouvertes`
  - State of the art : `state of the art`, `état de l'art`

`list` (défaut `todo`) : par dossier puis par thème, une ligne par entrée
`  [!] <nom-sans-.md> — <titre>`, `!` pour `Blocks release: yes`. Code 0.

`themes` (défaut `all`) : nombre d'entrées par thème et par dossier. Code 0.

`check` (défaut `all`) — code **1** si au moins une erreur, la liste sur stdout :
- nom de fichier hors `YYYY-MM-DD-<slug>.md`, ou date invalide ;
- titre, `Theme` ou `Area` manquant ; `Area` hors de `COMPONENTS` ∪ {`tooling`, `docs`, `ci`, `infra`} ;
- `Blocks release` manquant hors de `done/` ;
- dans `done/`, statut `done`/`dropped` manquant ; hors de `done/`, un statut présent ;
- même nom de fichier dans deux dossiers (une entrée copiée au lieu d'être déplacée).
Avertissement **non bloquant** : `wip/todo/` au-delà de `WIP_LIMIT` (une entrée bloquante doit
pouvoir y entrer ; c'est le refinement qui fait respecter la limite).

`refine` (défaut `all` = `todo` + `todo_nr`) — une ligne par entrée :
`<dossier>/<nom>  age <N>d  idle <M>d  [drapeaux]`, où *age* part de `Noted` (à défaut, la date du
nom) et *idle* du dernier commit qui touche le fichier. Drapeaux : `no-fix`, `no-acceptance`,
`open-question` (section présente et non vide) ; `stale` (*idle* > `STALE_DAYS`) ;
`dead-path:[…]` ; `links-closed:[…]` (l'entrée nomme une entrée qui est maintenant dans `done/`) ;
`BLOCKS-RELEASE`. Puis : chaque thème de plus de `CROWDED_THEME` entrées ouvertes, le total
ouvert, `wip/todo/` contre `WIP_LIMIT`, et `wip/todo_nr/` avec une suggestion de refinement
au-delà de `REFINE_THRESHOLD`. Code 0. Ces drapeaux sont ceux que lit `/shipyard:wip-refine`.

## 6. Lignes de `.gitignore` (pour l'orchestrateur)

```gitignore
# Editor vaults opened on the wiki: one person's local appearance and plugin state.
.obsidian/
```

Rien d'autre : `wip/` et `.llmwiki/` sont entièrement suivis, `wip/assets/` compris.

## 7. Le backlog initial (WP-D)

**Fonctionnalités de l'utilisateur → `wip/todo/`.** À partir de la description libre et des
réponses (`Project.md`) :
- une entrée par fonctionnalité **de la taille d'une PR** (environ une journée, une seule raison
  de revert) ; une fonctionnalité plus grosse est scindée en plusieurs entrées qui partagent le
  même `Theme` ;
- titre formulé comme un énoncé de ce qui manque (« Users cannot export a report as CSV ») ;
- `Noted:` = date du bootstrap, « while bootstrapping the project » ;
- `Area` = l'id du composant concerné (`COMPONENTS`) ; `Blocks release: no` sauf si la
  fonctionnalité *est* le jalon ;
- `**Fix:**` rédigé depuis la description ; `**Acceptance:**` 2 à 5 énoncés vérifiables par un
  test ou une commande ; tout choix que la description laisse ouvert devient un
  `**Open question:**` (l'entrée n'est alors pas *ready* : le premier `/shipyard:ship-parallel`
  le posera) ;
- au-delà de `WIP_LIMIT` entrées, les plus fondatrices (celles dont les autres dépendent) vont
  dans `todo/`, le reste dans `todo_nr/`.

**Outillage différé → `wip/todo_nr/`.** Les noms de fichier sont ceux que `Project.md` §
Deferred at bootstrap a fixés : WP-D écrit exactement ces fichiers, pour que les chemins cités
par `Project.md` existent. Une entrée par élément que le niveau d'outillage choisi n'installe
pas (par exemple : métriques de livraison, métriques de coût des agents, contrôle des workflows
planifiés, harnais d'evals, workflow de mise à jour des dépendances), `Area: tooling`,
`Blocks release: no`, et un thème par famille — `metrics` (livraison, coût des agents),
`ci-hygiene` (crons, dépendances), `evals` — : un thème unique pour tous dépasserait
`CROWDED_THEME` dès le premier jour et `wip.py refine` les signalerait comme à fusionner. Chaque
entrée est **autonome** : le projet n'aura pas cette annexe, donc le `**Fix:**` décrit en 5 à 10
lignes ce que le mécanisme fait et pourquoi, et l'`**Acceptance:**` dit comment on sait qu'il
marche. Si le mécanisme pourrait venir du plugin (un script générique), l'entrée le dit : le
correctif est alors une évolution du plugin, pas un script du projet.

**Autres entrées que l'orchestrateur peut demander à WP-D** (ou écrire à l'intégration) :
protection de branche indisponible (dépôt privé en offre gratuite), outil de la stack non
installable sur la machine, `<TODO>` laissé dans un skill de projet, tout point du
questionnaire laissé « à décider plus tard ».

**Vérification avant de rendre la main** : `python3 scripts/wip.py check` et
`python3 scripts/wiki_lint.py` verts — les deux scripts sont vendorisés avant le fan-out. Un
constat qui ne dépend que d'un fichier d'un autre lot (un chemin de code que WP-A n'a pas encore
écrit) se signale dans le rapport ; l'orchestrateur relance les deux à l'intégration.

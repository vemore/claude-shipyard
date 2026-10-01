# Annexe 7 — Les skills de projet

> Lue par **WP-E**, qui n'existe que si le projet a une cible de déploiement ou des releases
> planifiées, et qui écrit `.claude/skills/deploy/**`, `.claude/skills/release/**` et
> `<DEPLOY_ENV_FILE>.example` (annexe 00 §3). Les skills de livraison communs à tous les projets
> sont dans le plugin (§1.1) : WP-E ne les écrit pas, ne les copie pas. Ce que le wiki dit de ces
> skills est donné à WP-D par l'annexe 04.

## 1. Ce que WP-E produit

| Skill | Quand | Source |
|---|---|---|
| `deploy` | `DEPLOY_PATHS_RE` non vide (une cible de déploiement existe) | §3 (squelette) |
| `release` | `RELEASE_MODE=planned` | §4 (squelette) |

Rien d'autre. **Un skill naît de la répétition** : une procédure faite deux fois à la main
devient un skill à la troisième, dans sa propre PR. Écrire au bootstrap des skills spéculatifs
(« add-endpoint », « add-screen ») produit des procédures que personne n'a exécutées, donc
fausses, et que les agents suivront quand même. Le bootstrap ne crée que `deploy` et `release`,
quand le questionnaire les justifie.

### 1.1 Les skills du plugin, et comment un projet les règle

| Skill | Rôle | Ce qu'il attend du projet |
|---|---|---|
| `/shipyard:ship-parallel` | livrer plusieurs entrées `wip/` en parallèle : plan, lanes, un agent par PR, merges en série, déploiement, nettoyage | `tooling.conf`, `Project.md` § Risk et § Agents, `ParallelDelivery.md` ; le skill `deploy` et sa sonde s'il y a une cible |
| `/shipyard:wip-refine` | trier le backlog, proposer les promotions ; sa §8 est la passe d'élagage | `wip/`, `scripts/wip.py`, `Documentation.md` |
| `/shipyard:join` | (équipe) déclarer ses zones dans `.github/CODEOWNERS` et `Team.md` | le format de `Team.md` (annexe 06 §2) |
| `/shipyard:sync-tooling` | mettre à jour les copies vendorisées après une mise à jour du plugin, par une PR | `scripts/lib/VENDORED.json` |

Ils vivent dans le plugin et se mettent à jour avec lui. Un projet **règle** leur comportement :
- par les clés de `scripts/lib/tooling.conf` qu'ils lisent : `AUTONOMY` (merge et déploie, merge
  seulement, PR seulement), `RELEASE_MODE`, `TEAM_MODE`, `SIZE_THRESHOLD`, `LANE_C_RE`,
  `DEPLOY_PATHS_RE`, `CONCURRENCY_CAP`, `WIP_LIMIT`, `REFINE_THRESHOLD`, `STALE_DAYS`,
  `CROWDED_THEME`, `PRUNE_EVERY_MERGES` ;
- par ses pages wiki, que les skills lisent : les classes d'échec silencieux de `Project.md` §
  Risk, les agents de `Project.md` § Agents, la calibration de `ParallelDelivery.md` ;
- par ses propres skills, que les skills du plugin appellent par leur nom (`deploy`, et sa
  sonde à `.claude/skills/deploy/scripts/probe.sh`).

**Jamais en éditant le plugin**, ni en écrivant dans le projet un skill du même rôle : la
modification serait perdue à la mise à jour, ferait du projet une variante que plus aucun
correctif n'atteint, et deux procédures pour un même travail divergent. Un besoin qu'aucune clé
ne couvre est une entrée `wip/` (`Area: tooling`) qui propose l'évolution du plugin.

### 1.2 Notation des gabarits

- Les gabarits sont en anglais. **Traduire la prose dans la langue de documentation du projet si
  ce n'est pas l'anglais** ; garder en anglais les commandes, noms de fichiers, identifiants et
  messages de commit.
- `<default>` : remplacer par la valeur de `DEFAULT_BRANCH` ; `<project>` : par le nom du projet
  (les skills sont lus par un agent, pas exécutés : la valeur doit être écrite en clair).
- `<…>` en minuscules ailleurs : à remplir par WP-E depuis `tooling.conf` ou `Project.md`, ou
  par l'agent au moment de l'exécution quand le texte le dit (`<n>`, `<version>`, `<sha>`).
- `<WORKTREE_PREFIX>`, `<DEPLOY_ENV_FILE>` et les autres noms de clés de `tooling.conf` entre
  chevrons **restent littéraux** : ils se lisent dans `tooling.conf` au moment de l'étape.
- `<TODO: …>` : ce que le questionnaire n'a pas fixé (§3, §4).
- Le gabarit d'un skill est donné entre `~~~~markdown` et `~~~~` ; tout ce qui est entre les
  deux est le fichier `SKILL.md`, frontmatter compris.

## 2. Conventions d'un skill de projet

Ces conventions s'écrivent aussi, résumées, dans `.llmwiki/Documentation.md` § Skill
conventions (WP-D, annexe 06 §3), pour que les skills créés plus tard les suivent.

### 2.1 Frontmatter

- `name` : le nom du dossier, kebab-case.
- `description`, une formule fixe :
  `<ce qu'il fait, verbe en tête> — <les sous-étapes ou le périmètre>. Use when <situations, séparées par des virgules>. Triggers: "<phrase>", "<phrase>", …`
  - **Pourquoi** : la description est la seule partie lue pour décider de charger le skill.
    Les situations disent *quand*, les déclencheurs couvrent la façon dont l'utilisateur parle
    vraiment : sa langue (et l'anglais), ses formulations littérales, les noms d'outils et de
    commandes qu'il tape. Entre 300 et 700 caractères.
  - Nommer explicitement les capacités sortantes ou destructrices (« deploy **or roll back** »,
    « publish **on the user's go** ») : qui lit la description doit savoir ce que le skill peut
    faire hors de la machine.
- `disable-model-invocation: true` pour un skill dont l'effet principal est sortant et qui ne
  doit partir que sur demande explicite (`release`). **Pas** pour `deploy` :
  `/shipyard:ship-parallel` doit pouvoir l'invoquer sous l'autorisation de `CLAUDE.md` ; le
  garde-fou d'un usage hors boucle est dans son corps (§3), pas dans le frontmatter.
- Rien d'autre par défaut. Ajouter `allowed-tools` ou `model` seulement avec une raison écrite
  dans le corps.

### 2.2 Corps

- **Sections numérotées** `## 0.`, `## 1.`, `## 3b.` — citables comme « `deploy` §5 » depuis le
  wiki, une entrée `wip/`, un autre skill ou un prompt d'agent. Une étape à l'intérieur d'une
  section : « §1.5 ». Insérer `3b` plutôt que renuméroter : les citations existantes restent
  justes — `/shipyard:ship-parallel` cite `deploy` §5 (rollback).
- **Le piège d'abord.** Juste après l'introduction, une section `## The one rule you cannot
  break` (ou `## The trap`) : l'invariant dont la violation est *silencieuse* — un état qui a
  l'air sain et ne l'est pas. Ce qu'un agent lit en premier est ce qu'il retient.
- **Les faits dans le wiki, la procédure dans le skill.** Un skill dit *comment faire* ; il
  pointe vers la page qui dit *ce qui est* et *pourquoi* (« why: `.llmwiki/Deployment.md` »)
  sans recopier. Deux copies d'un fait divergent toujours, et l'agent suit celle qu'il a lue en
  dernier.
- `## When NOT to use this skill` quand un skill voisin ou une action plus simple couvre un cas
  qui ressemble au sien.
- `## Checklist` en fin de skill **opérationnel** (deploy, release) : cases `- [ ]`, chacune
  reprenant un gate dur. Pourquoi : à la fin d'une longue procédure, c'est la checklist qui
  attrape l'étape sautée.
- Les règles portent leur raison, et quand elle existe l'incident qui l'a créée. Une règle sans
  raison est la première qu'un agent pressé contourne, et la première qu'une passe d'élagage ne
  sait pas juger.
- Les actions sortantes suivent le motif **valider, rapporter, puis exécuter sur le feu vert**
  (`--dry-run` / `validate` d'abord, la commande réelle seulement quand l'utilisateur, ou
  l'autorisation durable de `CLAUDE.md`, la couvre).

### 2.3 Fichiers annexes

- `scripts/` à côté de `SKILL.md`, **seulement** quand la procédure a besoin de code. Chaque
  script suit les règles de l'annexe 05 §1 (Python stdlib ou shell, en-tête, `--help`, code 2
  pour l'usage) et a un test `test_<nom>.py` à côté, sans réseau ni identifiants (faux `gh`,
  fixtures). Le skill l'appelle **par son chemin complet depuis la racine du dépôt** —
  `python3 .claude/skills/<skill>/scripts/<nom>.py`, `.claude/skills/<skill>/scripts/<nom>.sh` —
  jamais par un chemin relatif au skill : l'agent qui le lit travaille depuis la racine d'un
  worktree. `scripts/selftest.sh` (vendorisé) lance ces tests, dossier par dossier.
- Un script générique, utile à tout projet, appartient au plugin : il se propose par une entrée
  `wip/` (`Area: tooling`). Un script propre au projet et partagé par plusieurs skills vit dans
  `scripts/`, à côté de `check.sh`, avec son test sous `scripts/selftest/` — jamais sous le nom
  d'une copie vendorisée.
- `references/` pour les gabarits longs (un brief à confier à un autre agent, un modèle de
  notes de version) : le skill reste court et charge le gabarit au moment où il sert.
- **Taille : 500 lignes au plus** par `SKILL.md`. Au-delà, sortir un gabarit dans
  `references/` ou un fait dans le wiki.

### 2.4 Registre

Chaque skill du projet est listé par son nom dans `CLAUDE.md` (« Repeatable procedures are
skills — check them before writing steps out by hand: … »), à côté des skills du plugin, et dans
la section finale de `.llmwiki/INDEX.md` (« Procedures live in skills, not here »). Un skill
absent de ces deux listes n'est jamais cherché. WP-E donne la liste dans son rapport ; WP-D
l'écrit.

### 2.5 Evals

Un skill de projet dont le bon résultat est **déterministe** (des fichiers, des commits, un état
de l'arbre) peut recevoir des evals au format du skill `skill-creator` —
`.claude/skills/<skill>/evals/evals.json` :
`{"skill_name": "<skill>", "evals": [{"id": 1, "prompt": "<a real past task, replayed>", "expected_output": "<the right outcome; names its wip/done/ source>", "files": [], "expectations": ["<5–7 checkable statements>"]}]}`.
Un skill dont le résultat passe par une cible distante ou par un jugement (`deploy`, `release`)
n'en reçoit pas au bootstrap : aucune tâche réelle n'existe encore à rejouer.

## 3. Le skill `deploy` (squelette, si une cible existe)

WP-E écrit le squelette ; les commandes réelles dépendent de la cible choisie au
questionnaire (conteneur sur un hôte via ssh, PaaS, pages statiques, registre de paquets). Ce
que le questionnaire n'a pas fixé reste un `<TODO: …>` explicite, listé dans le rapport, et
devient une entrée `wip/todo/` écrite par l'orchestrateur (« deploy skill has unfilled steps »,
`Blocks release: yes`) : un squelette qui a l'air complet est pire qu'un trou visible.

Pas de `disable-model-invocation` : `/shipyard:ship-parallel` §4 doit pouvoir l'invoquer après
chaque merge. Le garde-fou d'un usage hors boucle est dans le corps (§0 ci-dessous).

~~~~markdown
---
name: deploy
description: Deploy or roll back <project> to <target kind> — pre-flight checks, environment changes, deploy of a given commit, verification of the real deployed content, one-step rollback. Use when shipping a merged change, rolling back a bad deploy, changing a production environment variable, or diagnosing the live service. Called by /shipyard:ship-parallel §4 after each merge. Triggers: "deploy", "rollback", "push to prod", <user-language phrases>, <tool names>.
---

# deploy

Deploys a commit of `<default>` to <target, described without any host name>. Targets and
credentials are in the **untracked** `<DEPLOY_ENV_FILE>`, reachable only from a worktree set up
with `scripts/worktree_setup.sh --deploy`. Facts about the topology and their reasons:
`.llmwiki/Deployment.md`.

## 0. Before anything

- Under `/shipyard:ship-parallel` §4, `CLAUDE.md` already authorises the deploy. **Outside it,
  confirm with the user before running §3 or §5** — a deploy is outward-facing.
- Never write a real host, URL, path or credential into a tracked file — placeholders only,
  the real values live in `<DEPLOY_ENV_FILE>`.

## The one rule you cannot break

<the invariant whose violation is silent for this target — e.g. "data migrations do not roll
back with the code", "exactly one instance holds the in-memory state", "the build id served
must be the merged sha". WP-E writes the one that applies; if none is known yet, write
"<TODO: the first incident will name it>" and keep the section.>

## 1. Pre-flight

1. `.claude/skills/deploy/scripts/probe.sh` — must print `deploy: reachable`.
2. The tree is clean and at the intended commit: `git status --porcelain` empty,
   `git rev-parse HEAD` equals the merged sha.
3. <target-specific checks: credentials loaded, disk space, registry reachable, pending
   migration detected and a pre-migration backup possible>

## 2. Environment changes (only when the change needs one)

Read before writing: the key may already be set — never append blind. Show the current value
(masked if secret), change it in place or append it, then restart (§3.3). Rollback of an
environment change = restore the previous line and restart.

## 3. Deploy

1. <build the artefact for the commit>
2. <if a data migration is pending: take the pre-migration backup automatically, and stop
   without migrating if the backup fails>
3. <ship and restart>
4. <apply migrations>

## 4. Verify — the content, not "ok"

1. Read the health/version endpoint's **content**: the build id equals the deployed sha, the
   configuration it reports is the intended one. A health check once answered "ok" for two
   days while every real request failed because one configuration value was wrong.
2. Exercise a real path — the one the merged change touched — end to end.
3. Record what was checked, for the `/shipyard:ship-parallel` report.

## 5. Rollback

1. One command, to the previous artefact: <command>. Running it twice must not go further back
   than one release unless asked.
2. **Data migrations do not roll back with the code.** Undo a schema change by restoring the
   pre-migration backup taken in §3.2, not by a downgrade script — a downgrade is usually only
   proven on an empty database.
3. Verify (§4) after the rollback too.

## Checklist

- [ ] Probe said reachable; tree clean at the merged sha
- [ ] Pre-migration backup taken (if a migration was pending)
- [ ] Deployed build id == merged sha, read from the live endpoint
- [ ] The changed path exercised for real, not only the health endpoint
- [ ] No host, URL, path or credential added to a tracked file
~~~~

### 3.1 `.claude/skills/deploy/scripts/probe.sh`

Contrat (annexe 00 §4) : une seule ligne, `deploy: reachable` ou `deploy: <raison>`, sortie 0
ou 1, **jamais d'hôte imprimé** (la sortie finit dans des rapports et des transcripts).
`/shipyard:ship-parallel` §1 l'appelle par ce chemin exact à la planification. Il charge
`<DEPLOY_ENV_FILE>` (absent → `deploy: no <file> in this checkout`, sortie 1), puis teste **les
routes que le déploiement utilisera vraiment** (ssh en mode batch avec délai court, API du
registre, API du PaaS avec le jeton), pas l'URL publique du service : une URL publique répond de
partout et ne prouve rien sur la capacité de *déployer*. Lecture seule, chaque appel sous délai
de 5 s. Testé par `.claude/skills/deploy/scripts/test_probe.py`, avec un fichier
d'environnement factice et des commandes bouchonnées.

### 3.2 `<DEPLOY_ENV_FILE>.example`

Les clés que `probe.sh` et le skill lisent, chacune avec une valeur **factice** et un commentaire
d'une ligne (`DEPLOY_HOST=example.invalid`). Jamais une valeur réelle : ce fichier est suivi, et
`SECRET_ALLOW_RE` l'exempte du contrôle de chemin, pas du contrôle de contenu.

## 4. Le skill `release` (squelette, si `RELEASE_MODE=planned`)

`disable-model-invocation: true` : une release publie, souvent de façon irréversible ; elle
ne part que sur demande de l'utilisateur, jamais parce qu'un agent a jugé le moment venu.

Deux choix tenus par ce squelette, et pourquoi :
- **Merger d'abord, puis construire et tagger le commit squashé** (§5) : un merge en squash
  laisse les commits de la branche de release hors de `<default>` ; un tag ou un artefact
  construit sur eux est invisible pour `git describe` et casse les notes de la release suivante.
- **Une seule passe d'élagage** : celle de `/shipyard:wip-refine` §8, que §3b lance ; le skill
  n'en porte pas de copie, qui divergerait.

~~~~markdown
---
name: release
description: Cut and publish a release of <project> — release worktree, version bump, release notes, policy gate, pruning pass, merge, then artefact build and verification from the squash commit, and publish and tag on the user's explicit go. Use when the user asks to prepare, cut or publish a release, bump the version, or write release notes. Triggers: "release", "cut a release", "bump version", "publish", <user-language phrases>.
disable-model-invocation: true
---

# release

## The one rule you cannot break

Publishing is outward-facing and usually irreversible. Every publishing command runs first in
its validate / dry-run form, the result is reported, and the real command runs only on the
user's explicit go **for this target**. A go for one channel is not a go for another.

## 1. Release worktree

`git fetch --prune origin && git worktree add --no-track -b chore/release-<version> <WORKTREE_PREFIX>release origin/<default>`,
then `scripts/worktree_setup.sh <WORKTREE_PREFIX>release`. <TODO: if publishing needs signing
material, the flag of `worktree_setup.sh` that links it to this worktree only — none exists at
bootstrap; the first release that needs one adds it, with a `wip/` entry until then.>

## 2. Version and notes

1. Bump the version in <the one place it is declared — or every place, listed>.
2. Notes from `git log <last-tag>..origin/<default> --oneline`, grouped by conventional type,
   rewritten for users (what they will notice), not for developers.

## 3. Policy gate

| Check | How |
|---|---|
| <licence of new dependencies> | <command> |
| <privacy / data disclosures still true> | <the documents that must move together> |
| <store or registry policy> | <command or reading> |

A failure here is not fixed inside the release: stop, write a `wip/todo/` entry, tell the user,
and let them decide whether it blocks.

## 3b. Pruning pass

Run `/shipyard:wip-refine` §8 before cutting the release. It proposes; its removals are their
own pull request, decided by the user — not part of this release branch.

## 4. Build and verify the artefact

1. <build command>
2. `.claude/skills/release/scripts/verify_artifact.<ext>`: one line per check, non-zero on
   the first failure — version, signature, target platform, size, no debug flag, no secret. A
   stale build directory fails the check: rebuild rather than work around it.

This dry build, in the release worktree, only proves the artefact can be built before the
merge; what is published is rebuilt from the squash commit in §5.

## 5. Merge, then publish the squash commit

The published artefact and the tag must be **the squash commit on `<default>`**: a squash
merge leaves the release branch's own commits off `<default>`, so a tag or a build made from
them is invisible to `git describe` and breaks the next release's notes.

1. Merge the release branch (version bump, notes) through `/shipyard:ship-parallel` §3. Note
   the squash sha: `git fetch --prune origin && git rev-parse origin/<default>`.
2. In a detached worktree at that sha
   (`git worktree add --detach <WORKTREE_PREFIX>release-build <sha>`), rebuild and rerun §4.
3. Validate: <the dry-run / validate command>. Report what it says.
4. On the user's go for this target: <the publish command>.
5. Tag that sha: `git tag v<version> <sha>`, `git push --dry-run origin v<version>`, then the
   real push — outward-facing, so it is part of the same go, named explicitly in the question.

## Checklist

- [ ] Version bumped everywhere it is declared
- [ ] Policy gate passed, or the user decided on each failure
- [ ] Pruning pass run (`/shipyard:wip-refine` §8), its removals proposed as their own pull request
- [ ] Release branch merged; artefact rebuilt and verified at the squash sha
- [ ] Validate output reported before the publish
- [ ] Publish and tag (on the squash sha) run only on the user's explicit go
~~~~

Si l'artefact de la stack n'est pas connu au bootstrap, `verify_artifact` reste un `<TODO: …>`
dans `SKILL.md` — jamais un script vide qui « passe » — et l'orchestrateur écrit l'entrée
`wip/todo/` correspondante (« release skill has unfilled steps »). Un script écrit a son test à
côté (`.claude/skills/release/scripts/test_verify_artifact.py`).

## 5. Avant le rapport de WP-E

- `grep -rn '<default>\|<project>' .claude/skills/` ne renvoie rien (les valeurs sont écrites
  en clair) ; les `<TODO: …>` restants sont listés dans le rapport.
- Chaque `SKILL.md` ≤ 500 lignes ; chaque frontmatter a `name` = nom du dossier.
- Chaque script cité par un skill existe sous `.claude/skills/<skill>/scripts/`, est exécutable
  et répond à `--help` ; chacun a son test, et `scripts/selftest.sh` (vendorisé) est vert.
- Chaque nom de script, de clé et de skill cité figure dans l'annexe 00, dans cette annexe ou
  parmi les skills du plugin (§1.1).
- `<DEPLOY_ENV_FILE>.example` ne contient que des valeurs factices.
- Le rapport donne : la liste des skills de projet (pour `CLAUDE.md` et `INDEX.md`), les
  `<TODO>` (chacun devient une entrée `wip/` écrite par l'orchestrateur), et ce que la page
  `Deployment.md` doit savoir de la cible (sans hôte).

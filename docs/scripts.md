# Les scripts de shipyard

> Pour qui maintient le plugin. Ce document dit **ce que fait chaque script du process, dans
> quels cas limites, et pourquoi**. Les sources sont dans `plugins/shipyard/templates/` ; chaque
> projet en reçoit des **copies vendorisées**. Les noms, signatures et codes de sortie viennent du
> contrat du plugin ([`contrat-plugin.md`](contrat-plugin.md) §4-§5), qui l'emporte en cas
> d'écart. La spécification de `scripts/check.sh`, que chaque projet écrit lui-même, est
> l'annexe 05 de la skill `bootstrap` (`references/05-check.md`). Les hooks ont leur propre
> document : [`hooks.md`](hooks.md).

## 1. Du gabarit à la copie vendorisée

### 1.1 Pourquoi des copies

Le code générique est écrit et testé **une fois**, dans le plugin, et un correctif atteint tous
les projets à la mise à jour du plugin, au lieu d'être régénéré (et de varier) à chaque bootstrap.
Mais ce que la CI exécute doit rester dans le dépôt : **un runner GitHub n'a pas le plugin**, et
un humain lance ces scripts sans Claude. D'où des copies, **identiques** au gabarit de leur version
(empreintes dans `scripts/lib/VENDORED.json`) : une copie modifiée localement est une dérive
signalée, pas une personnalisation silencieuse.

### 1.2 Ce qui est vendorisé

| Gabarit (`plugins/shipyard/templates/`) | Destination dans le projet |
|---|---|
| `scripts/{ci_scope,cleanup_local,pr_size,wiki_lint,wip,lane_paths,owners,precommit}.py` | `scripts/` |
| `scripts/worktree_setup.sh`, `scripts/selftest.sh` | `scripts/` |
| `scripts/lib/{conf,dead_paths}.py` | `scripts/lib/` |
| `scripts/selftest/test_*.py` | `scripts/selftest/` |
| `githooks/pre-commit` | `.githooks/pre-commit` |

**Ce qui n'est pas vendorisé** et reste propre au projet : `scripts/lib/tooling.conf` (toutes les
valeurs), `scripts/check.sh` (les gates de la stack, §3) et son selftest, tout fichier absent de la
liste ci-dessus. Les hooks Claude Code ne sont pas copiés non plus : ils vivent dans le plugin.

**Règle de généricité.** Une copie ne contient aucune valeur propre à un projet : une telle valeur
est une clé de `tooling.conf`, jamais une ligne de code. C'est ce qui permet qu'elle soit identique
partout.

### 1.3 `bin/vendor.py` et `scripts/lib/VENDORED.json`

```
bin/vendor.py <racine-du-projet> [--check] [--force]
```

- Écrit les fichiers du tableau §1.2, les rend exécutables, et écrit `scripts/lib/VENDORED.json` :
  `{"shipyard": "<version de plugin.json>", "files": {"<chemin>": "<sha256>"}}`.
- **Refuse d'écraser** un fichier vendorisé dont le contenu diffère de l'empreinte enregistrée
  (modifié à la main), sauf `--force`, et liste ces fichiers. Pourquoi : écraser en silence
  détruirait une correction locale que quelqu'un croyait garder ; refuser en silence laisserait
  un projet figé sans le savoir.
- `--check` n'écrit rien. Il imprime, par fichier, `ok`, `outdated <from> -> <to>`,
  `modified <chemin>` ou `missing <chemin>`. Sortie 0 : rien à faire ; 1 : quelque chose à
  synchroniser ; 2 : usage.
- Ne touche **jamais** à `tooling.conf`, à `check.sh`, ni à un fichier non listé.

Le circuit d'une mise à jour : `/plugin update` apporte les nouveaux gabarits ; le hook
`SessionStart` voit que `VENDORED.json` est plus ancien que `plugin.json` (ou qu'un fichier est
modifié) et le dit ; `/shipyard:sync-tooling` lance `bin/vendor.py` ; la synchronisation est ensuite
livrée comme tout changement du projet. **Un changement qui modifie un gabarit est au moins une version mineure**, et
son entrée de `CHANGELOG.md` dit « run `/shipyard:sync-tooling` ».

## 2. Règles communes

- **Python 3.9+, bibliothèque standard seulement** pour tout script de logique. Shell seulement
  pour ce qui lance les outils de la stack (`check.sh`, `worktree_setup.sh`, `selftest.sh`).
  Pourquoi : pas de `jq`, pas de `date -d` ni de `timeout` GNU, absents de macOS ; un script qui
  casse sur une dépendance absente fait taire le garde-fou qu'il alimente. La CI du plugin les
  exécute sur Linux et macOS.
- **Racine et configuration.** Chaque script trouve sa racine par `git rev-parse --show-toplevel`
  dans le répertoire courant (donc la racine du *worktree*, pas celle du checkout principal) et lit
  `scripts/lib/tooling.conf` de cette racine, par `scripts/lib/conf.py` : lignes `CLE=valeur` ou
  `CLE='valeur'`, commentaires `#`, aucune interpolation. **Une clé absente est une erreur
  explicite** (`missing key X in scripts/lib/tooling.conf`), jamais une valeur par défaut silencieuse :
  un défaut caché est exactement la dérive que le fichier unique supprime. Toute regex `*_RE` est
  évaluée par le module `re` de Python : un script shell qui en a besoin passe par Python plutôt que
  par `grep -E`, dont les classes (`\t`, `\d`, `[[:space:]]`) ne disent pas la même chose.
- **Code 2 = erreur d'usage ou de configuration**, pour tous. Un appelant traite tout code non
  prévu comme un échec (le hook de commit : comme un refus).
- **En-tête.** Chaque script commence par un docstring ou un commentaire anglais : usage, ce qu'il
  garantit, ce qu'il ne couvre pas, pourquoi il existe. `--help` l'imprime.
- **Réseau.** Aucun, sauf `cleanup_local.py` (fetch + `gh`) et `pr_size.py <n>` (`gh`). Tout appel
  externe passe par `subprocess.run(..., timeout=N, capture_output=True, text=True)` ; un délai
  dépassé ou un `gh` non authentifié dégrade la sortie, ne la fait pas planter.
- **Selftests.** Un fichier par script sous `scripts/selftest/test_<script>.py` : `unittest`
  stdlib, piloté par des tables de cas, bac à sable dans `tempfile.mkdtemp()` (dépôt + remote nu
  `git init --bare`), `gh` bouchonné par un exécutable écrit dans un répertoire placé en tête de
  `PATH` et qui répond selon une variable d'environnement du cas. Pourquoi bouchonner `gh` : sinon
  les cas dépendant de GitHub sont sautés partout où `gh` n'est pas authentifié, et la seule
  réponse jamais vue est celle qui casse le hook.
- Les bacs à sable fixent `GIT_AUTHOR_NAME/EMAIL`, `GIT_COMMITTER_NAME/EMAIL`,
  `GIT_CONFIG_GLOBAL=/dev/null` et `GIT_CONFIG_NOSYSTEM=1` : un test qui hérite de la config de
  l'utilisateur (signature GPG, `init.defaultBranch`, hooks globaux) n'est pas reproductible.
- Les selftests sont eux aussi vendorisés : dans un projet, `scripts/selftest.sh` les lance contre
  **les copies du projet**, ce qui prouve qu'elles fonctionnent dans son environnement. Dans le
  dépôt du plugin : `python -m unittest discover -s plugins/shipyard/templates/scripts/selftest -v`.

## 3. `scripts/check.sh` : la seule définition des gates (propre à la stack)

`check.sh` n'est **pas** vendorisé : il est écrit par le bootstrap pour la stack choisie, et
`bin/vendor.py` n'y touche jamais. Le plugin ne dépend que de son **interface**, que les hooks, la
CI et `worktree_setup.sh` appellent.

**Pourquoi un point unique.** Écrits à plusieurs endroits (le hook de commit, le YAML de la CI, un
`CLAUDE.md` de sous-dossier), les gates divergent, et un commit vert localement devient rouge en CI.
Ici, le hook appelle `check.sh fast`, la CI appelle `check.sh ci <component>`, l'humain appelle
`check.sh all` : une seule commande, un seul endroit à modifier.

**Cibles :**

| Cible | Fait | Codes |
|---|---|---|
| `fast [--paths-from FILE]` | gates **statiques** (lint, format `--check`, types) des composants que les chemins touchent, plus les contrôles d'outillage ci-dessous ; sans `--paths-from` : tous les composants | 0 / 1 / 3 |
| `test [COMPONENT]` | suites de tests d'un composant ou de tous | 0 / 1 / 3 |
| `all` | `fast` puis `test`, tout | 0 / 1 / 3 |
| `edit FILE` | contrôle d'un seul fichier, < 5 s, **rapport seulement** | 0 rien · 1 rapport sur stdout |
| `ci COMPONENT` | exactement le contenu du job CI : installation verrouillée, `fast`, `test`, build/packaging, audit de dépendances | 0 / 1 / 3 |
| `setup COMPONENT` | installe les dépendances (verrou exact) et lance la génération de code du composant ; appelé par `worktree_setup.sh` | 0 / 1 / 3 |

**Quels composants pour `fast --paths-from`.** Le fichier contient un chemin par ligne. Le script les
passe à `python3 scripts/ci_scope.py` et lance les gates des composants marqués `true`. Ainsi la
logique chemins → composants n'existe qu'une fois (§6) : le commit vérifie exactement les composants
dont la CI tournera. Un changement de documentation seule ne lance aucun gate de composant ; un
chemin inconnu les lance tous. Si `ci_scope.py` est absent ou échoue, `fast` lance **tous** les
composants, avec un avertissement sur stderr : un sur-ensemble coûte des secondes, un gate sauté est
une régression invisible.

**Contrôles d'outillage de `fast`**, décidés par chemin, indépendamment des composants (quelques
secondes au total) :

- un `*.py` sous `scripts/` ou `.claude/skills/*/scripts/` →
  `python3 -m py_compile` sur ces fichiers ;
- un `*.sh` sous `scripts/` ou `.claude/` → `bash -n` sur ces fichiers ;
- un chemin sous `.llmwiki/` → `python3 scripts/wiki_lint.py` (sortie 1 sur constat seulement ; ses
  lignes `note:` ne bloquent pas) ;
- un chemin sous `wip/` → `python3 scripts/wip.py check`.

Pourquoi : ces deux derniers bloquent le job `tooling` en CI ; les lancer au commit évite une PR
rouge pour une date d'`Updated:` oubliée. Les selftests, eux, restent en CI (ce sont des tests).

**Sortie et codes.**

- Chaque gate est lancé, sa sortie capturée. En échec : les 40 dernières lignes, puis
  `Reproduce with: <commande exacte>` ; le script continue les autres gates pour tout rapporter en
  une fois, puis sort en 1.
- Outil absent (`command -v` échoue, ou l'environnement du composant n'est pas installé : pas de
  `.venv`, pas de `node_modules`) : message `<tool> is not installed for <component>`, et en
  **dernière ligne de stderr** `SETUP: <commande d'installation>` (typiquement
  `scripts/worktree_setup.sh` ou `scripts/check.sh setup <component>`), sortie 3. Jamais un gate
  sauté en silence. Si un outil manque *et* qu'un autre gate échoue, sortie 3 (il faut d'abord
  installer pour savoir).
- `edit FILE` : si l'outil manque, sortie 0 sans rien dire (le hook post-édition est un confort, la
  garantie est au commit).

**Règles.**

- Les outils de la stack ne visent que les dossiers de leur composant (`ruff check src tests`, pas
  `ruff check .`), dans `check.sh` comme dans la configuration (`include`, `files`). Le dépôt
  contient aussi les scripts vendorisés, écrits pour Python 3.9 et contrôlés par `py_compile` : un
  linter de la stack réglé sur une version plus récente les casserait, et certains formateurs
  réécrivent aussi le Markdown du wiki.
- **`fast` reste statique et rapide** (cible : < 30 s à chaud). Les tests au commit sont payés deux
  fois par changement (au commit puis en CI) et forcent un worktree à moitié installé à tout
  installer pour résoudre un conflit d'une ligne. La CI les exécute, et le hook `Stop` refuse de
  finir un tour sur une PR rouge : rien n'est livré rouge.
- **Le formatage est vérifié (`--check`), jamais imposé par un refus de lancer le formateur** : le
  formateur est sûr à lancer ; c'est du code non formaté qu'on refuse.
- `ci <component>` n'utilise que des installations verrouillées (`--locked`, `npm ci`,
  `--frozen-lockfile`) : un verrou désynchronisé doit rendre la CI rouge, pas être réparé en
  silence.
- Un test qui se saute quand une variable d'environnement manque (service externe, conteneur)
  reçoit un drapeau `<NAME>_REQUIRED=true` positionné par `ci <component>` : en CI il échoue au lieu
  de passer vert sans avoir rien exécuté.
- Le selftest de `check.sh` (`scripts/selftest/test_check.py`, écrit avec lui) couvre, dans un dépôt
  bac à sable avec des outils bouchonnés sur `PATH` : un gate qui échoue → 1 avec « Reproduce
  with: » ; outil absent → 3 et `SETUP:` en dernière ligne ; outil absent + gate rouge → 3 ;
  `--paths-from` documentation seule → aucun gate de composant ; `ci_scope.py` absent → tous ;
  `edit` sur un fichier propre → 0 sans sortie.

Les exemples par écosystème (Python/uv, Node, Go, Rust, JVM, site statique) que le bootstrap suit
pour écrire `check.sh` sont dans l'annexe 05 §2 de la skill `bootstrap`.

## 4. `scripts/worktree_setup.sh`

Usage : `scripts/worktree_setup.sh [DIR] [--no-<component>]… [--deploy]` : options et `DIR` dans
n'importe quel ordre. **Tous les arguments sont validés avant d'écrire le marqueur** (`--no-<x>`
inconnu, `--deploy` sans cible → sortie 2 sans marqueur) : un marqueur laissé par une faute de
frappe serait honoré par le nettoyage pour toujours.

**Pourquoi il existe.** Un worktree neuf n'a ni dépendances ni code généré : son premier commit
serait refusé par un gate pour une raison sans rapport avec le changement, et un agent perdrait son
temps à le diagnostiquer. Un seul script rend n'importe quel worktree utilisable.

Étapes, dans l'ordre :

1. `TREE=$(git -C "${DIR:-.}" rev-parse --show-toplevel)` ; pas un dépôt → message, sortie 2.
   `MAIN` = parent du `git -C "$TREE" rev-parse --path-format=absolute --git-common-dir` (le
   checkout principal, d'où viennent les secrets). Charge `$TREE/scripts/lib/tooling.conf` (la copie
   de la branche du worktree).
2. **Écrit le marqueur avant tout ce qui est lent** : `$TREE/$SETUP_MARKER` contenant
   `pid <$$> started <date ISO-8601 UTC> branch <branche>`. Pourquoi : un nettoyage lancé depuis une
   autre session a supprimé un worktree *et* sa branche pendant que la génération de code tournait.
   Tout ce que le setup écrit est ignoré par git, donc `git status` voyait un arbre propre, et la
   branche n'avait encore aucun commit : les deux signes d'un worktree abandonné. Une consigne « ne
   pas nettoyer pendant un setup » ne protège rien ; un marqueur que le nettoyage lit, si.
3. `--deploy` : si `DEPLOY_ENV_FILE` est vide → `this project has no deploy target`, sortie 2.
   Sinon, si `$MAIN/$DEPLOY_ENV_FILE` existe et que `TREE ≠ MAIN` → `ln -sfn` vers
   `$TREE/$DEPLOY_ENV_FILE` ; s'il n'existe pas → avertissement, et on continue. **Lié, jamais
   copié** : une rotation de secret est vue partout, et aucune copie ne survit dans un worktree
   oublié. **Jamais par défaut** : un agent implémenteur ne déploie pas, donc son worktree n'a pas à
   atteindre la cible. Ce qu'un agent peut toucher se limite à ce que sa tâche demande.
4. Pour chaque composant de `COMPONENTS` non exclu par `--no-<component>` :
   `scripts/check.sh setup <component>`. Un `--no-<x>` dont `x` n'est pas un composant est une
   erreur, sortie 2 (une faute de frappe ne doit pas sauter une installation).
5. Supprime le marqueur, puis imprime en dernière ligne `ready: <TREE> (<branche>)`.

Règles :

- `set -euo pipefail` (ce n'est pas un hook) : une étape qui échoue arrête le script **en laissant
  le marqueur**, exprès, sans `trap`. Un setup planté laisse un worktree à moitié construit :
  c'est précisément celui qu'il ne faut pas supprimer. Le `--help` dit comment retirer un marqueur
  périmé : `rm <tree>/<SETUP_MARKER>`, à la main, après vérification.
- Le script ne touche à aucune configuration globale ni git (`core.hooksPath` : posé une fois par
  clone) et n'écrit que sous `$TREE`.
- Idempotent : relancé sur un worktree prêt, il refait l'installation verrouillée (rapide) et
  imprime `ready:`.

Selftest (avec un `scripts/check.sh` factice dans le bac à sable, qui note ses appels et peut
échouer sur demande) : marqueur présent pendant `check.sh setup` et retiré au succès ; marqueur
conservé et sortie ≠ 0 si un setup échoue ; `--no-<c>` saute exactement ce composant ;
`--no-inconnu` → sortie 2 ; `--deploy` crée un lien symbolique vers le fichier du checkout
principal ; `--deploy` sans fichier source → avertissement et sortie 0 ; aucun lien sans
`--deploy` ; `DIR` hors dépôt → sortie 2 ; dernière ligne `ready: …`.

## 5. `scripts/cleanup_local.py`

Usage : `scripts/cleanup_local.py [--apply]`. Dry run par défaut ; **toujours sortie 0** : c'est un
rapport, pas un gate.

**Pourquoi.** Chaque boucle parallèle laisse des worktrees d'agents, des branches `worktree-<nom>`
abandonnées pour la vraie branche, un worktree de déploiement et une branche locale par PR mergée.
Un premier nettoyage à la main a trouvé 20 branches et 2 worktrees périmés, et il a fallu trois
tentatives pour *prouver* chaque branche supprimable. Le script fait cette preuve, et garde tout ce
qu'il ne peut pas prouver.

**Préparation.**

1. Se place dans le checkout principal (parent du `--git-common-dir`) et y lit la conf.
2. `git fetch --prune --quiet origin` (délai 60 s). **C'est le seul script autorisé à fetcher** :
   tout son travail est de juger contre le distant, et il est lancé délibérément par l'opérateur, pas
   en arrière-plan d'une autre opération (un fetch écrit dans le clone que partagent tous les
   worktrees). Échec → `warning: fetch failed; judging against a stale origin/<default>` et on
   continue (un distant périmé ne fait que garder davantage).
3. `origin/<DEFAULT_BRANCH>` absent → message, sortie 0. `gh auth status` (délai 10 s) → `GH_OK`
   vrai ou faux.

**Règle « branche supprimable »**, `deletable(branch) -> (bool, raison)` :

1. `git rev-list --count origin/<d>..<branch>` = 0 → oui, `no commit ahead of origin/<d>`.
2. Sinon, sans `GH_OK` → non, `<N> commit(s) ahead; gh unavailable to prove a merge`.
3. `gh pr list --head <branch> --state merged --json number,headRefOid --limit 1`. Aucune → cherche
   une PR ouverte pour la raison : `pull request #N OPEN` ou `no pull request` → non.
4. PR mergée trouvée : `gh api repos/{owner}/{repo}/compare/<headRefOid>...<tip local> --jq .status`.
   `identical` ou `behind` → oui, `merged in #N (local tip included)`. Réponse vide ou erreur (le tip
   local n'existe pas sur GitHub) → non, `local tip is not on GitHub`. `ahead` / `diverged` → non,
   `local tip has commits beyond merged #N`.

Pourquoi le compare GitHub et pas autre chose : `git cherry` signale *toutes* les branches
squash-mergées comme non mergées (le squash change les patch-ids) ; une comparaison locale avec la
tête de la PR échoue parce que les têtes mises à jour sur GitHub n'ont jamais été fetchées ;
`git merge-tree` contre la branche par défaut rapporte comme « changements » d'anciennes versions de
lignes réécrites depuis. Le compare de la tête mergée contre le tip local répond à la vraie question :
*chaque commit local est-il dans ce qui a été mergé ?*

**Worktrees** (`git worktree list --porcelain` ; jamais le checkout principal). Les gardes sont
évaluées **dans cet ordre**, et chacune garde le worktree **et sa branche** (la branche est ajoutée à
l'ensemble `KEPT`) : sans cela, la boucle des branches supprimerait la branche sous un worktree vivant.

| # | Garde | Preuve | Ligne imprimée |
|---|---|---|---|
| 1 | Verrou d'une session vivante | ligne `locked <raison>` dont la raison contient `pid <N>` (verrou posé par Claude Code, forme observée `claude agent <nom> (pid N start T)`), `N` vivant (`os.kill(N, 0)` ; `PermissionError` = vivant) et, si `/proc/N/stat` est lisible (Linux), son champ 22 égal à `T` | `keep worktree <path> (<b>) — locked by a running session (pid N)` |
| 2 | Verrou manuel | `locked` sans `pid` | `keep … — locked: <raison>` |
| 3 | Setup en cours | `<wt>/<SETUP_MARKER>` existe | `keep … — setup in progress (<SETUP_MARKER>)` |
| 4 | Agent peut-être au travail | `CLEANUP_IDLE_MINUTES > 0` et un fichier quelconque sous le worktree (fichiers ignorés compris) a une mtime plus récente que maintenant − N minutes ; `os.walk`, arrêt au premier trouvé | `keep … — modified in the last N minutes (an agent may be working)` |
| 5 | Modifications non commitées | `git -C <wt> status --porcelain` non vide | `keep … — uncommitted changes` |
| 6 | HEAD détachée | `git merge-base --is-ancestor HEAD origin/<d>` vrai → à supprimer ; sinon, si `gh` dit que HEAD est la tête d'une PR **mergée** (`gh pr list --state merged --search <sha>`, puis compare de la tête mergée contre HEAD = `identical`) → à supprimer (worktree d'un relecteur, détaché sur une tête qu'un squash a laissée hors de la branche par défaut) ; sinon garder | `would remove … — detached on a commit in origin/<d>` / `… — detached on the head of merged #<n>` / `keep … — detached on a commit not in origin/<d>` |
| 7 | Branche | `deletable(branch)` | `would remove … — <raison>` / `keep … — <raison>` |

Détails :

- La variable d'environnement `CLEANUP_IDLE_MINUTES` surcharge la conf ; `0` désactive **la seule**
  garde 4 : un verrou vivant et le marqueur sont toujours honorés.
- Champ 22 de `/proc/N/stat` : le nom du processus (champ 2) peut contenir espaces et parenthèses ;
  le script coupe après la **dernière** `)` : le champ 22 est alors l'indice 19 de la suite. Sur macOS
  (pas de `/proc`), seul « pid vivant » est vérifié ; le `--help` le dit.
- Un verrou dont le pid est mort, ou recyclé (heure de démarrage différente), est **périmé** : le
  worktree passe les autres gardes normalement ; s'il est supprimé, c'est par
  `git worktree remove -f -f <path>` et la ligne ajoute `; stale lock, pid N is gone`.
- `--apply` : `git worktree remove <path>` (avec `-f -f` si verrou périmé). Échec → ligne
  `FAILED remove worktree <path>` suivie de l'erreur de git, indentée de 4 espaces ; la branche est
  alors gardée. Puis `git worktree prune`.

**Branches** (`git for-each-ref refs/heads --format='%(refname:short)'`) : sont sautées la branche par
défaut, la branche courante du checkout principal (si elle est supprimable :
`keep <b> — current branch of the main checkout; switch to <d> first`), toute branche de `KEPT` et
toute branche encore extraite dans un worktree restant. Pour les autres : `deletable` →
`would delete branch <b> — <raison>` (avec `--apply` : `git branch -D <b>` — `-D` parce qu'une
branche squash-mergée n'est jamais « mergée » au sens de git — puis `deleted branch <b>`), sinon
`keep branch <b> — <raison>`. Fin de sortie en dry run : `Dry run. Re-run with --apply to act.`

**Limite honnête** (écrite dans `--help` et dans le wiki du projet) : aucune garde ne rend `--apply`
sûr pendant que des agents travaillent. Un worktree non verrouillé, inactif depuis plus que la
fenêtre, sur une branche sans commit, ressemble à un abandon. Les gardes couvrent les fenêtres qui
ont coûté du travail en pratique : une session d'agent vivante, le setup de quelques minutes, un
agent entre deux commits. D'où la règle d'usage : `--apply` seulement une fois que tous les agents
ont rendu leur rapport.

Selftest (remote nu + clone + `gh` bouchonné) : branche à 0 commit d'avance → supprimée ; PR mergée,
compare `identical` → supprimée ; PR mergée + un commit local en plus (compare `ahead`) → gardée ; PR
ouverte → gardée `#N OPEN` ; aucune PR → gardée ; `gh` indisponible → gardée avec raison ; worktree
sale → gardé avec sa branche ; marqueur → gardé avec sa branche ; mtime récente → gardé, puis supprimé
avec `CLEANUP_IDLE_MINUTES=0` ; verrou avec le pid du test et sa vraie heure de démarrage → gardé ;
verrou au pid mort → supprimé par `--apply` avec `stale lock` ; verrou manuel → gardé ; (Linux) pid
vivant mais heure différente → périmé ; HEAD détachée sur un commit de la branche par défaut →
supprimée ; branche courante du checkout principal → gardée avec le conseil ; dry run ne modifie rien
(comparer `git worktree list` et `git branch` avant/après) ; échec de suppression → `FAILED` + erreur
indentée (provoqué par un répertoire parent en lecture seule ; cas sauté si exécuté en root).

## 6. `scripts/ci_scope.py`

Usage : `git diff --name-only origin/<d>...HEAD | scripts/ci_scope.py`.

**Fonction pure** : chemins sur stdin (un par ligne, vides ignorés, espaces de bord retirés), une
ligne `<component>=true|false` par composant de `COMPONENTS`, dans cet ordre, sur stdout. Aucun
réseau, aucun `gh` : on rejoue une PR passée avec un simple `git diff`. Un renommage doit fournir les
deux chemins (l'ancien et le nouveau). Le script **lit stdin jusqu'au bout** même quand la réponse
est déjà « tout » (pas de sortie anticipée : le producteur du pipe recevrait SIGPIPE et ferait échouer
l'étape CI sous `pipefail`). Entrée vide → tout `false`. Sortie 2 si `tooling.conf` manque ou est
incomplet (en CI, un `scope` en échec fait tourner tous les jobs).

**Aucune table de chemins en dur.** La table chemins → composants vit dans `tooling.conf`, une clé par
composant : `COMPONENT_<ID>_RE` (`<ID>` = l'identifiant du composant dans `COMPONENTS`, en
majuscules, `-` remplacé par `_`), une regex Python des chemins qui le concernent (répertoire,
manifestes, verrous). Le script applique, pour chaque chemin :

1. un chemin que reconnaît une `COMPONENT_<ID>_RE` lance **tous les composants** dont l'expression le
   reconnaît (un fichier partagé par plusieurs : leur ensemble), même s'il ressemble à de la
   documentation (une page générée vérifiée par un test, un site de docs, un `SKILL.md` lu par un
   test) ;
2. sinon, la **documentation seule** ne lance rien : `\.md$` partout (y compris `.claude/**/*.md` :
   skills, agents et règles sont des prompts qu'aucun job de composant ne teste, le job `tooling`,
   qui tourne toujours, les couvre), `^wip/`, `^\.llmwiki/`, `^docs/` ;
3. sinon, **fourre-tout : tout lance tout** : `^\.github/`, `^\.claude/` hors `.md` (hooks, settings,
   scripts locaux des skills), `^scripts/` (dont `check.sh` et `tooling.conf` : changer un gate doit le
   faire tourner), et tout chemin inconnu.

Les drapeaux s'accumulent (OU) sur tous les chemins. **Pourquoi** : *se tromper doit coûter un run
lent, jamais un merge non testé*. Une règle trop étroite ne rend rien rouge, elle laisse merger ce
que rien n'a testé. Le job `tooling` n'apparaît pas dans la sortie : il tourne toujours.

Un composant sans `COMPONENT_<ID>_RE` ne tournerait que par le fourre-tout, donc à chaque changement :
c'est un défaut de configuration, pas un état voulu.

Selftest : *rien* (`README.md`, une page du wiki, une entrée `wip/`, un `SKILL.md`, `docs/guide.md`) ;
*un composant* (un fichier source, son verrou) ; *tout* (`.github/workflows/ci.yml`,
`scripts/check.sh`, `scripts/lib/tooling.conf`, `.claude/settings.json`, un script de skill, un
chemin inconnu) ; *mélanges* (doc + un composant → ce composant ; renommage d'un composant vers un
autre → les deux) ; entrée de 10 000 lignes lue en entier (pas de SIGPIPE) ; script exécutable.

## 7. `scripts/pr_size.py`

Usage : `scripts/pr_size.py <n>` (lit `gh pr diff <n>`, délai 60 s ; `gh` absent ou en échec →
message sur stderr, sortie 2) ou `scripts/pr_size.py -` (diff unifié sur stdin). Imprime un seul
entier. `-v`/`--verbose` détaille, sur stderr, le compte par fichier et les fichiers exclus.

**Ce qui est compté** : les lignes **ajoutées** (`+`) dans les hunks des fichiers dont le chemin ne
correspond pas à `SIZE_EXCLUDE_RE`. Le chemin d'un fichier est celui de la ligne `diff --git a/X b/Y`
(on prend `Y`, on retire `b/`, on dé-quote un chemin entre guillemets). Seules les lignes situées
**après le premier `@@`** d'un fichier sont comptées : ainsi l'en-tête `+++ b/…` ne l'est jamais,
alors qu'une ligne de contenu commençant par `++` l'est. Une suppression pure (`+++ /dev/null`) et un
fichier binaire comptent 0. Une ligne modifiée apparaît comme un couple `-`/`+` et compte donc une
fois.

**Pourquoi ajoutées seulement, hors docs et tests.** Le seuil mesure combien de code de production une
revue doit tenir en tête, pas combien est vérifié. Une PR de nettoyage dont 1 026 lignes étaient la
*suppression* de deux guides morts comptait 1 590 lignes et a exigé un feu vert ; recomptée sur les
seuls ajouts de code, elle faisait 279. Compter les tests rendait une PR bien testée plus « grosse »
qu'une PR non testée : le seuil poussait contre ce que le projet veut le plus. Une PR de
documentation seule compte 0.

**Usage par `ship-parallel`** : au moment du merge, au-dessus de `SIZE_THRESHOLD` la PR est **lane B
quoi qu'ait dit le plan**. C'est le filet d'une lane mal estimée à la planification, pas le critère
principal : la lane se décide sur ce que le changement va toucher, avant que le code existe.

Selftest (diffs écrits à la main) : docs seules → 0 ; 10 lignes de code ajoutées → 10 ; 3 lignes
modifiées → 3 ; fichier supprimé → 0 ; fichier de test exclu ; verrou exclu ; renommage avec
modifications → comptées sous le nouveau chemin ; ligne de contenu `++x` dans un hunk → comptée ;
binaire → 0 ; chemin entre guillemets ; entrée `-` ; `gh` absent avec un numéro → sortie 2.

## 8. `scripts/lane_paths.py`

Usage : `git diff --name-only … | scripts/lane_paths.py lane-c|deploy`.

Lit des chemins sur stdin, **un par ligne** (un chemin peut contenir une espace), charge
`tooling.conf` depuis la racine du dépôt courant, et imprime ceux qui correspondent à `LANE_C_RE`
(`lane-c`) ou à `DEPLOY_PATHS_RE` (`deploy`), un par ligne. Sortie **0** si au moins un chemin
correspond, **1** si aucun, **2** si `tooling.conf` est illisible. Une regex vide ne correspond à rien
(pas de lane C, rien à déployer). Lit stdin jusqu'au bout (le producteur ne reçoit jamais SIGPIPE).

**Pourquoi un script plutôt qu'un `grep -E` dans une skill.** Les regex de `tooling.conf` sont évaluées
par Python, et une ligne de shell avec un quoting imbriqué, recopiée par un agent, est exactement ce
qui casse sans bruit. Il sert à `ship-parallel` : au merge, un chemin de `lane-c` rend la PR lane C quoi
qu'ait dit le plan ; après un merge, `deploy` dit si ce que le merge a changé se déploie.

Selftest, sans réseau : aucune correspondance, une correspondance, regex vide, chemins avec espaces,
stdin vide.

## 9. `scripts/owners.py`

Usage : `scripts/owners.py [--who LOGIN]`, chemins sur stdin.

- Sans `--who` : une ligne `chemin<TAB>@owner …` par chemin, avec la sémantique de CODEOWNERS : **le
  dernier motif qui correspond l'emporte**.
- Avec `--who` : les motifs que possède `@LOGIN`. Sortie 1 si LOGIN ne possède rien.
- Sortie 2 : pas de CODEOWNERS, ou usage.

`CODEOWNERS` est cherché dans `.github/CODEOWNERS`, puis `CODEOWNERS`, puis `docs/CODEOWNERS` (l'ordre
de GitHub).

**Pourquoi.** En équipe (`TEAM_MODE=team`), trois choses lisent la propriété du code et ne doivent pas
chacune réimplémenter la syntaxe de CODEOWNERS : le hook `SessionStart` (« You own: … » ou l'invite à
`/shipyard:join`), `ship-parallel` (le plan montre, pour chaque PR, les owners des chemins probables ;
une PR qui touche une zone étrangère attend l'approbation d'un owner de cette zone) et `/shipyard:join`
(qui met le fichier à jour). Le script est la lecture unique ; le fichier lui-même est tenu par
`/shipyard:join`, et un commentaire en tête le dit.

**Ne couvre pas** : l'application de la règle. GitHub demande la revue ; l'approbation des owners est
un **process**, pas une règle de branche, parce que `require_code_owner_reviews` empêcherait un owner
seul de sa zone de merger ses propres PR. Les owners sont des `@login` (contrat §7).

## 10. `scripts/precommit.py`

Appelé par `.githooks/pre-commit` (voir [`hooks.md`](hooks.md) §9), pour les commits faits hors de
Claude Code. Il fait le **contrôle des secrets** (chemin et contenu, par les clés `SECRET_*` de
`tooling.conf`) puis lance
`scripts/check.sh fast --paths-from` sur les fichiers indexés. Sortie 0 ; 1 = refus. Il **sort 0 tout
de suite si `CLAUDECODE=1`** : le hook `PreToolUse` de Claude Code a déjà jugé ce commit, et chaque
commit de Claude paierait sinon ses gates deux fois.

**Pourquoi un script vendorisé.** Il tourne sans le plugin (terminal, IDE), donc il doit être dans le
dépôt ; il lit les mêmes clés `SECRET_*` que la garde du plugin, de sorte que les valeurs n'existent
qu'une fois. Comme les hooks, il ne rend rien impossible : `git commit --no-verify` reste
l'échappatoire humaine assumée, et la CI reste le dernier filet.

## 11. `scripts/selftest.sh`

Une commande, premier step du job `tooling` du projet. Elle lance
`python3 -m unittest discover -s scripts/selftest -p 'test_*.py'`, puis la même commande avec `-s` sur
**chaque** `.claude/skills/*/scripts/` existant (un processus par dossier : deux skills peuvent avoir
un `test_x.py` de même nom), additionne les tests exécutés (ligne « Ran N tests ») et **échoue si un
lancement échoue ou si le total est 0**.

**Pourquoi pas `discover -s .claude/skills`** : `unittest` ne descend pas dans un dossier sans
`__init__.py` ; Python 3.9 répond alors « Ran 0 tests, OK », 3.12 sort en 5. Un selftest qui ne lance
rien passe pour vert, et un garde-fou jamais exercé ne se distingue pas d'un garde-fou qui passe.
**Pourquoi à chaque push** : les cas intéressants sont ceux qui *ressemblent* à une violation et n'en
sont pas ; sans table exercée à chaque changement, la première modification d'une règle casse un
garde-fou en silence.

## 12. `scripts/wip.py` et `scripts/wiki_lint.py`

Spécifiés par l'annexe 06 de la skill `bootstrap` ; l'en-tête de chaque script fait foi sur le détail.

- **`wip.py list|themes|check|refine [todo|todo_nr|done|all]`** : l'index du backlog. Une entrée est
  `wip/<todo|todo_nr|done>/YYYY-MM-DD-<slug>.md`, un fichier par entrée et **aucun fichier d'index** :
  deux PR ne se rencontrent jamais dans `wip/`, et le script *est* l'index. `check` (sortie 1 sur
  erreur, lancé en CI) fait respecter le format sur lequel les outils s'appuient : nom de fichier,
  titre, `Theme`, `Area` parmi `COMPONENTS` et `tooling, docs, ci, infra`, `Blocks release`, statut
  `done|dropped` seulement dans `done/`, pas deux fichiers de même nom dans deux dossiers. `refine`
  imprime les signaux d'un tri (âge, inactivité, `no-fix`, `no-acceptance`, `stale`, `dead-path`,
  `links-closed`, `BLOCKS-RELEASE`, thèmes encombrés, seuil `REFINE_THRESHOLD`). Ne juge pas si une
  entrée est encore vraie : c'est le travail de `/shipyard:wip-refine`.
- **`wiki_lint.py [WIKI_DIR]`** : les contrôles du wiki (`.llmwiki/`) qu'un script peut faire,
  bloquants en CI : page trop longue (`WIKI_PAGE_BUDGET`), chemin mort entre backticks
  (`scripts/lib/dead_paths.py`, racines `DEAD_PATH_ROOTS`), ligne `> Updated: YYYY-MM-DD` ou titre
  `## Decisions & History` manquant, ligne d'`INDEX.md` dont la date diffère de celle de la page, page
  absente de l'index. Les `note:` (bloc `Outdated`/`Contradicted`, lien `[[Nom]]` pendant) ne bloquent
  pas. Pourquoi : un agent copie ce qu'il lit, donc un wiki qui vieillit en silence égare chaque
  tâche suivante ; les linters Markdown ne connaissent ni les `[[liens]]`, ni les chemins entre
  backticks, ni les dates `Updated:`.

## 13. Niveau Complet (hors copies vendorisées)

L'annexe 05 §7-8 spécifie des scripts du niveau d'outillage `complet` : `delivery_metrics.py`
(fenêtre, taux de retouche à 48 h, déploiements déduits des chemins, taille, vert au premier run, âges
de `wip/`), `check_scheduled_runs.py` (GitHub désactive un workflow planifié après 60 jours sans
activité, et rien ne devient rouge), `agent_metrics.py` (coût des sessions, attribué par skill, agent,
outil), et le harnais d'evals `evals/`. **Ils ne font pas partie des copies vendorisées de la
version 0.1.0** (contrat §5). Le hook `SessionStart` appelle `scripts/check_scheduled_runs.py`
seulement si `TOOLING_LEVEL=complet` et que le script existe.

## 14. Ce que les scripts ne couvrent pas

- Ils ne rendent rien impossible : un `git commit --no-verify`, un merge par l'interface web ou un
  `check.sh` modifié à la main passent à travers ; la CI et la protection de branche sont derrière.
- `cleanup_local.py --apply` n'est jamais sûr pendant que des agents travaillent (§5).
- Les copies vendorisées ne se mettent pas à jour seules : un projet qui n'ouvre jamais de session
  avec le plugin garde la version qu'il a (le hook le dit à la session suivante).
- Une session de code distant ne charge pas le plugin du projet : les scripts, qui sont dans le dépôt,
  y fonctionnent, les hooks non.

## 15. Décisions et historique

- **Une seule définition des gates** (`check.sh`) : trois copies (hook, CI, sous-dossier) avaient
  divergé.
- **Des tests hors du commit** : ils étaient payés deux fois.
- **`gh` bouchonné dans les selftests** : la seule réponse jamais vue fut celle qui cassa.
- **Un fourre-tout dans `ci_scope`** : un mauvais scope ne rougit rien, il laisse merger du non testé.
- **Le marqueur de setup** : un nettoyage concurrent a supprimé un worktree en plein setup ; une
  consigne que l'opérateur doit se rappeler ne protège rien.
- **Les secrets seulement sur demande** (`--deploy`) : ce qu'un agent peut atteindre se limite à sa
  tâche.
- **Le compare GitHub pour prouver une branche supprimable**, et non `git cherry`, une comparaison
  locale ou `merge-tree` : trois tentatives pour prouver 20 branches ; chaque garde garde aussi la
  branche.
- **La taille compte les ajouts de code seulement** : une PR de nettoyage comptait 1 590 lignes dont
  1 026 de suppressions demandées.
- **Des copies vendorisées plutôt que des scripts lus dans le plugin** (nouveau) : un runner GitHub n'a
  pas le plugin, et un humain lance ces scripts sans Claude. Contrepartie : la dérive est détectée par
  empreinte (`VENDORED.json`) et corrigée par `/shipyard:sync-tooling`.
- **Aucune valeur propre à un projet dans une copie** (nouveau) : `COMPONENT_<ID>_RE`, `LANE_C_RE`,
  `DEPLOY_PATHS_RE`… sont des clés de `tooling.conf`, parce qu'une copie doit rester identique au
  gabarit de sa version.
- **`owners.py` comme lecture unique de CODEOWNERS** (nouveau) : trois consommateurs, une seule
  implémentation de la syntaxe.

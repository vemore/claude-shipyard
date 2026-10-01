# Les hooks de shipyard

> Pour qui maintient le plugin. Ce document dit **ce que font les hooks, pourquoi, et ce qu'ils
> ne couvrent pas**. Le code est dans `plugins/shipyard/hooks/`, les tests dans
> `tests/test_hooks.py`. Les noms, les clés de `tooling.conf` et les interfaces viennent du
> contrat du plugin ([`contrat-plugin.md`](contrat-plugin.md) §5-§7), qui l'emporte en cas
> d'écart. Les faits que le wiki d'un projet en reprend sont dans l'annexe 04 de la skill
> `bootstrap` (`references/04-faits-pour-le-wiki.md`).
>
> Tout est en **Python 3.9+, bibliothèque standard seulement** (sauf `session_start.sh`, en
> `sh`), et les messages sont en anglais : ils entrent dans le contexte du modèle.

## 1. Principes

**Pourquoi des hooks.** Une règle écrite en prose dans `CLAUDE.md` ne tient que tant que l'agent
la relit et y pense ; la CI ne l'attrape qu'après le push. Toute règle qu'un script peut
**décider** (forme d'une commande, chemin commité, état d'une branche) devient un refus
mécanique. Les règles de **jugement** restent en prose : une garde heuristique qui crie au loup
est pire que la prose, parce que l'agent apprend à la contourner.

**Ce que les hooks ne sont pas.** Ils ne sont pas une frontière de sécurité (§11) : ils
réduisent une classe d'erreurs fréquentes et visibles, ils ne la rendent pas impossible. La
protection de branche de GitHub, quand elle existe, reste derrière.

### 1.1 Où ils vivent

| Dans le plugin (`plugins/shipyard/hooks/`) | Dans le projet |
|---|---|
| `hooks.json` : le câblage des événements | `scripts/lib/tooling.conf` : **toutes** les valeurs (branche par défaut, regex de secrets…) |
| `guard_bash.py`, `parse_command.py`, `post_edit.py`, `require_pull_request.py`, `session_start.py`, `session_start.sh`, `_common.py` | `scripts/check.sh` : les gates, propres à la stack |
| | `scripts/precommit.py` et `.githooks/pre-commit` : copies vendorisées, pour les commits faits hors de Claude Code (§9) |

Les commandes de `hooks.json` sont de la forme `python3 "${CLAUDE_PLUGIN_ROOT}/hooks/<fichier>.py"`
(sauf `session_start.sh`). `CLAUDE_PROJECT_DIR` reste disponible mais n'est jamais ce qui désigne
le dépôt jugé (§1.3).

Câblage (le fichier `hooks.json` fait foi ; les délais sont ceux qui ont tenu en pratique) :

| Événement | Matcher | Script | Rôle | Délai |
|---|---|---|---|---|
| `SessionStart` | | `session_start.sh` | briefing de début de session (§8) | 60 s |
| `PreToolUse` | `Bash` | `guard_bash.py` | refus des formes dangereuses ; secrets, branche et gates avant un commit (§4-§5) | 300 s |
| `PostToolUse` | `Edit\|Write\|MultiEdit` | `post_edit.py` | rapport de cohérence après une édition, sans bloquer (§6) | 60 s |
| `Stop` | | `require_pull_request.py` | pas de fin de tour sur des commits sans PR, ni sur une PR rouge (§7) | 60 s |
| `SubagentStop` | | `require_pull_request.py` | idem pour un agent implémenteur | 60 s |

Le délai de 300 s de la garde Bash existe parce que les gates statiques tournent *dans* le hook,
au moment du commit : un délai court transformerait un lint lent en commit refusé.

**Conséquence du plugin : les règles en vigueur sont celles de la version du plugin**, plus
celles du checkout. Un projet ne contient plus les hooks ; une PR qui change un refus est une PR
du dépôt du plugin, testée par `tests/test_hooks.py`, et distribuée par `/plugin update`. Le
checkout principal reste malgré tout sur la branche par défaut, fast-forwardée, et ne commite
jamais : c'est lui qui sert aux fast-forwards, aux déploiements et de point de départ aux
worktrees des agents.

Les hooks sont lus **au démarrage de la session** (`/hooks` montre ce qui est chargé) : une
modification, ou une mise à jour du plugin, ne vaut qu'à la session suivante.

### 1.2 Protocoles par événement

Tels que prouvés en production ; en cas d'écart avec https://code.claude.com/docs/en/hooks, la
documentation gagne et le test fige ce qui a été retenu.

| Événement | Champs du payload (JSON sur stdin) utilisés | Pour bloquer / informer | Code |
|---|---|---|---|
| `PreToolUse` (`Bash`) | `cwd`, `tool_input.command` | message sur **stderr** + **exit 2** : l'appel est bloqué et le message est montré au modèle | **seul 2 bloque** : exit 1 est une « erreur non bloquante » et la commande s'exécute quand même |
| `PostToolUse` (`Edit\|Write\|MultiEdit`) | `cwd`, `tool_input.file_path` | stdout JSON `{"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": "<texte>"}}` : atteint le modèle sans rien bloquer (le stdout brut ne va qu'au journal de debug) | 0 |
| `SessionStart` | `cwd`, `source` | stdout **brut** injecté dans le contexte | toujours 0 |
| `Stop`, `SubagentStop` | `cwd`, `stop_hook_active` | stdout JSON `{"decision": "block", "reason": "<texte>"}` : le modèle reprend avec `reason` comme consigne | 0 ; si `stop_hook_active` est vrai, **rien n'est imprimé** |

### 1.3 Quel dépôt est jugé

- `cwd` est le dossier courant de la session au moment de l'appel ; pour un sous-agent lancé avec
  `isolation: "worktree"`, c'est son worktree. `CLAUDE_PROJECT_DIR` est le dossier où la session
  a démarré (le checkout principal).
- **Ce qui est jugé, c'est le dépôt où la commande s'exécute**, jamais `CLAUDE_PROJECT_DIR` par
  défaut : un commit dans un worktree est jugé sur la branche et les fichiers du worktree, avec
  le `tooling.conf` et le `check.sh` de ce worktree. Juger le checkout principal à la place a
  cassé quatre fois en deux jours avant que la règle n'existe.
- Quand le dépôt ne peut pas être déterminé, le hook le dit (`unknown-repo`, avec remède) au lieu
  de deviner.

### 1.4 Projet non bootstrappé : les hooks sont inertes

Le plugin peut être activé dans n'importe quel dépôt — et il l'est dans tous, dès qu'il est
installé pour l'utilisateur, ce qu'il faut pour lancer `/shipyard:bootstrap` dans un dossier
vide. **Sans `scripts/lib/tooling.conf` dans le dépôt jugé, tous les hooks sortent 0 sans rien
imprimer.** Seule exception : `SessionStart` dans un dossier **vide** imprime une suggestion :

```
This folder is empty and shipyard is enabled: run /shipyard:bootstrap <what you want to build>
to start a project with its tooling.
```

Pourquoi : un plugin installé pour un usage ne doit pas refuser des `git push` dans des dépôts
qui n'ont rien demandé. Le bootstrap pose `tooling.conf` ; sa présence est le consentement.

L'inertie se décide **commande par commande**, pas par session : chaque refus, push ou commit est
jugé sur le dépôt où il s'exécute (`cd`, `git -C`). Un `git -C ../autre-depot push --force` lancé
depuis un projet bootstrappé vers un dépôt sans `tooling.conf` passe ; l'inverse est refusé. Une
commande dont le répertoire ne se laisse pas déterminer est jugée sur le dépôt de la session. Une
ligne sans `git` ni `gh` sort tout de suite.

Les commits faits hors de Claude Code passent par `.githooks/pre-commit`, qui lance la copie
vendorisée `scripts/precommit.py` (secrets, puis `scripts/check.sh fast`) : l'ancien mode
`guard_bash.py --git-pre-commit` n'existe plus, puisque les hooks ne sont pas dans le dépôt.

### 1.5 Politique d'échec

Une erreur interne d'un hook ne bloque **jamais** : tout `main()` est enveloppé dans
`try/except Exception` → trace sur stderr, `exit 0`. Un garde qui bloque sur son propre bug est
pire que le risque qu'il couvre. En contrepartie, l'absence silencieuse est traitée ailleurs :
`SessionStart` dit en clair quand `python3`, `git` ou `gh` manquent (§8), et un gate qui n'a pas
pu tourner est un refus, pas un passage (§5.6).

## 2. `_common.py`

### 2.1 Configuration

`load_conf(root)` lit `<root>/scripts/lib/tooling.conf`, la copie **du dépôt jugé** : une branche
qui change une valeur la voit appliquée à ses propres commits. Analyse : lignes `CLE=valeur`, les
lignes vides et `#` sont ignorées, coupure au premier `=`, **une** paire de quotes simples ou
doubles externes est retirée, aucune interpolation. Les valeurs par défaut codées
(`DEFAULT_BRANCH=main`, `GIT_CONFIG_NS=project`, regex vides = règle désactivée) ne servent qu'aux
clés absentes d'un fichier présent.

Une regex `*_RE` qui ne compile pas est un refus (`bad-config`), pas un scan éteint en silence.

### 2.2 Résolution du dépôt

- `repo_root(path)` : pour un fichier, part de son dossier (ou du plus proche parent existant
  s'il vient d'être supprimé), puis `git -C <dir> rev-parse --show-toplevel` ; `None` si ce n'est
  pas un dépôt.
- `git(root, *args, timeout=10) -> (rc, stdout)` : jamais d'exception vers l'appelant.
- `current_branch(root)` : `git symbolic-ref -q --short HEAD` ; `None` = HEAD détachée.
- `origin_is_github(root)` : lit l'URL **brute** (`git config --get remote.origin.url`) et non
  `git remote get-url`, qui applique les réécritures `insteadOf` — les tests s'en servent pour
  pointer une URL GitHub vers un dépôt nu local. Vrai si l'URL contient `github.com`.

### 2.3 `gh`

`gh_run(args, cwd, timeout=None, ok_codes=(0,)) -> Optional[str]` rend `None` si `gh` est absent
du `PATH`, non authentifié, trop lent, ou sort avec un code hors `ok_codes` — **silencieusement**
dans tous ces cas. `gh pr checks` sort en 1 quand un check échoue et en 8 quand un check est en
attente : ses appels passent `ok_codes=(0, 1, 8)` et lisent la sortie, sinon le hook ne verrait
jamais d'échec. Délai par défaut 20 s, surchargeable par `HOOK_GH_TIMEOUT` (pour les tests).
`gh_ready(root)` = `gh` présent ∧ `origin_is_github` ∧ `gh auth status` rend 0 (mis en cache pour
l'exécution).

**Les hooks ne font jamais `git fetch`.** Un fetch écrit dans le clone, dont les refs sont
partagées par tous les worktrees, sous les pieds d'une autre session. Tout ce qu'ils savent d'une
branche date donc du dernier `git fetch --prune` — c'est l'agent qui le fait — et un silence des
hooks n'est pas une preuve de fraîcheur.

## 3. `parse_command.py` : lire une ligne de commande sans être un shell

**Pourquoi un parseur et pas un grep.** Découper sur `&&` et `;` puis chercher des sous-chaînes
crie au loup sur chaque cas de quoting : `git commit -m "never git push --force"`, un `echo`, et
surtout un heredoc qui *documente* une commande interdite — la garde se déclenchait sur le
fichier même qui la décrit.

Entrée : le texte de `tool_input.command`, le `cwd` du payload, la configuration. Sortie (dict
sérialisable en JSON) :

```json
{"parse_ok": true,
 "blocks":  [{"rule": "force-push", "message": "…"}],
 "commits": [{"all": false, "amend": false, "pathspecs": [], "cwd": "/abs/or/null"}],
 "pushes":  [{"refspecs": ["HEAD"], "bare": false, "head_ref": true, "cwd": "/abs/or/null"}],
 "config_writes": [{"key": "ns.allowstackedpr", "cwd": "/abs"}]}
```

`cwd: null` signifie « dépôt indéterminable ». Les listes permettent plusieurs commits ou pushes
sur une même ligne (`git -C a commit … && git -C b commit …`).

### 3.1 Étapes

0. **Commentaires.** Une passe qui connaît les quotes retire les commentaires (un `#` en début de
   mot hors quotes) ; ensuite `shlex` tourne avec `commenters=''`, sinon il couperait au premier
   `#` d'un mot (`git push origin feat#1 --force` perdrait `--force`).
1. **Heredocs.** Les ouvreurs `<<-?\s*(["']?)([A-Za-z_][A-Za-z0-9_]*)\1` sont repérés et les
   lignes du corps supprimées jusqu'à la ligne égale au délimiteur (tabulations retirées pour
   `<<-`). La ligne ouvrante est gardée. Cela retire aussi le corps de
   `git commit -m "$(cat <<'EOF' … EOF)"`, dont il ne reste qu'une chaîne entre quotes sur deux
   lignes. `<<<` (here-string) n'est pas un heredoc.
2. **Tokenisation.** Chaque ligne passe par `shlex.shlex(line, posix=True,
   punctuation_chars=True)` avec `whitespace_split = True`, suivi d'un jeton `;` de fin de ligne.
   Si une ligne lève `ValueError` (quote ouverte sur plusieurs lignes), le texte entier est relexé
   d'un bloc ; si cela échoue encore : `parse_ok = false` (§3.4).
3. **Ponctuation collée.** `shlex` colle les suites de ponctuation (`);` après `X=$(pwd)`) : tout
   jeton fait uniquement de `();<>|&` est découpé en opérateurs connus, le plus long d'abord
   (`;;`, `&&`, `||`, `|&`, `>>`, `<<<`, `<<`, `>&`, `&>`, `>|`, puis un caractère). Ce `);`
   cachait le `git commit` qui suivait : le commit passait sans gates.
4. **Segments.** Coupe sur `&&`, `||`, `;`, `;;`, `|`, `|&`, `&`, `(`, `)` et les fins de ligne.
   Chaque redirection (`>`, `>>`, `<`, `<<`, `<<<`, `>&`, `&>`, `>|`) est retirée **avec** son jeton
   cible, ainsi qu'un jeton tout-chiffres juste avant une redirection (le descripteur de
   `2>/dev/null`, sinon pris pour un argument).
5. **Sous-shells.** Le `cwd` notionnel est empilé sur `(` et dépilé sur `)` :
   `(cd /tmp && …); git commit` juge le `cwd` d'avant la parenthèse.
6. **Affectations.** Un segment fait **uniquement** de `NOM=valeur` (éventuellement précédés de
   `export`) lie chaque nom : à la valeur littérale (après `~` en tête), ou à *inconnu* si elle
   contient `$`, une backquote, `*`, `?`, `[` ou `(`. Une affectation **en préfixe**
   (`W=/x git …`) ne lie rien, comme le shell (elle ne vaut que pour cette commande) ; elle est
   simplement retirée de la tête.
7. **Normalisation de la tête.** Sont retirés en tête : `if then else elif fi do done while until
   for ! { } time nohup command exec builtin` ; `env` et ses `NOM=val`, `-i`, `-u NOM` ; `sudo` et
   ses options (`-u X`, `-g X`, `-E`, `-H`…) ; `timeout` et sa durée (et `-s SIG`, `-k D`) ;
   `nice` (`-n N`) ; `xargs` et ses options (`-I X`, `-n N`, `-P N`, `-L N`, `-d X`, `-E X`,
   `-s N`, drapeaux sans argument) — ce qui suit `xargs` est la commande lancée, jugée comme
   telle (ses arguments manquants sont inconnus, mais les drapeaux visibles, comme `--force`,
   comptent).
8. **Déroulage.** Une tête `bash`, `sh`, `zsh` ou `dash` suivie d'une option qui contient `c`
   (`-c`, `-lc`, `-ec`, `-xc`) : l'argument suivant est un script, parsé récursivement avec le
   même `cwd` et les mêmes variables, et son verdict est fusionné. `eval` : les arguments sont
   joints par des espaces et parsés récursivement. Profondeur max 3. `bash script.sh` (sans `-c`)
   reste opaque (§11).
9. **Répertoire courant notionnel.** Départ : `cwd` du payload. `cd` / `pushd` : sans argument →
   `$HOME` ; `-` → inconnu ; chemin absolu → lui ; `~` / `~/…` → `expanduser` ; `$NOM` / `${NOM}`
   liés à un littéral (étape 6) → substitués ; relatif sans `$` → joint au `cwd` notionnel s'il est
   connu, puis `normpath` ; tout le reste (variable héritée de l'environnement, `$(…)`, glob) →
   **inconnu**. `popd` → inconnu. Un `cd` absolu ultérieur rend le `cwd` connu à nouveau.
10. **`git`.** Les options globales avant la sous-commande sont sautées : avec argument `-C`, `-c`,
    `--git-dir`, `--work-tree`, `--namespace`, `--super-prefix`, `--config-env`, `--exec-path` (les
    formes `--opt=val` n'en consomment pas) ; tout autre jeton commençant par `-` est un drapeau
    sans argument (`-p`, `-P`, `--no-pager`, `--bare`, `--no-optional-locks`…). Chaque `-C dir` est
    résolu comme un `cd` relatif au répertoire git courant du segment (`-C a -C b` → `a/b`).
    `--git-dir` ou `--work-tree` présents → dépôt **inconnu** pour un commit ou un push.
11. **Commit.** `git commit` : `-a`/`--all` (y compris groupé : `-am`) → `all` ; `--amend` →
    `amend` ; `--dry-run`, `-h`, `--help` → pas un commit. Options courtes à argument :
    `m F C c t` (le reste du jeton s'il y en a un, sinon le jeton suivant) ; `S` et `u` n'ont
    qu'un argument collé. Options longues à argument (sauf forme `=`) : `--message`, `--file`,
    `--reuse-message`, `--reedit-message`, `--template`, `--author`, `--date`, `--fixup`,
    `--squash`, `--cleanup`, `--trailer`, `--pathspec-from-file` (ce dernier → `all = true`,
    sur-ensemble). `--` : tout ce qui suit est pathspec ; tout jeton non-option est pathspec.
12. **Push.** `--dry-run`/`-n` et `--help` ignorent le segment. Options à argument : `--repo`,
    `--receive-pack`, `--exec`, `-o`, `--push-option`. Premier positionnel = remote, suivants =
    refspecs ; `bare = (aucun refspec)`. `head_ref = true` si un refspec sans `:` vaut `HEAD` ou
    `@`. Les règles du §4 en dérivent.
13. **`gh`.** `gh pr create` : valeur de `--base X`, `--base=X`, `-B X`, `-BX`. `gh pr merge` : les
    drapeaux sont scannés en **sautant les arguments** des options qui en prennent
    (`-b/--body`, `-F/--body-file`, `-t/--subject`, `-A/--author-email`, `--match-head-commit`,
    `-R/--repo`), les drapeaux courts groupés sont lus lettre par lettre (`-sd` =
    `--squash --delete-branch`). `gh pr create` saute de même `-t -b -F -H -a -l -m -p -r -R -T`
    et leurs formes longues. `gh api` : méthode (`-X`/`--method`) et chemin.
14. **`git config`.** Écriture = une valeur après la clé, ou `--add`, `--replace-all`, `set`
    (syntaxe récente `git config set <clé> <val>`) ; lecture = `--get`, `--get-all`,
    `--get-regexp`, `--list`/`-l`, `get`, ou clé seule. `--unset` n'est pas une écriture au sens de
    la règle (il re-verrouille). Clés comparées en minuscules.

### 3.2 Exemples (repris dans les tests)

| Ligne | Verdict |
|---|---|
| `cd /abs/wt && git commit -m x` | commit, `cwd=/abs/wt` |
| `W=/abs/wt; git -C "$W" commit -m x` | commit, `cwd=/abs/wt` |
| `W=/abs/wt git -C "$W" commit -m x` | commit, `cwd=null` (préfixe : rien n'est lié) |
| `X=$(date); git commit -m x` | commit détecté (découpage de `);`) |
| `bash -c 'git push --force origin x'` | bloc `force-push` |
| `git commit -m "never git push --force"` | commit, aucun bloc |
| `cat > notes.md <<'EOF'` / `git push --force origin main` / `EOF` | aucun bloc |

### 3.3 Ce que le parseur ne prétend pas faire

Il n'expande ni l'environnement hérité, ni `$(…)`, ni les globs, ni les alias, ni les fonctions
shell ; il n'ouvre pas les scripts lancés (`bash scripts/x.sh`). Aller plus loin ferait de lui un
shell. Quand il ne peut pas savoir, il le dit (`cwd: null` → refus `unknown-repo` avec remède) au
lieu de deviner.

### 3.4 Ligne illisible

`parse_ok = false` → **aucun bloc** (on ne refuse pas ce qu'on ne sait pas lire) **mais** : si le
texte contient `git` puis `commit` (regex `\bgit\b.*\bcommit\b`, sur plusieurs lignes), un commit
est supposé `{all: true, amend: true, pathspecs: [], cwd: <cwd du payload>}` : un gate de trop
coûte quelques secondes, un gate sauté est une régression silencieuse. Et si le texte contient
aussi `\bcd\b` ou `git\s+-C`, alors `cwd: null` (refus `unknown-repo`).

Pourquoi : une ligne illisible (le quoting `'"'"'` d'un `gh pr create --body "$(printf …)"`)
retombait sur le checkout principal et faisait refuser à tort le travail d'un worktree, trois
sessions dans la même journée.

## 4. Les refus

Chaque message commence par `BLOCKED (<règle>)`, nomme la règle, et finit par le remède.
`<D>` = `DEFAULT_BRANCH`, `<ns>` = `GIT_CONFIG_NS`.

| Règle | Déclencheur | Passe | Pourquoi |
|---|---|---|---|
| `force-push` | `git push` avec `--force`, `-f`, un groupe court contenant `f` (`-fu`), `--force-with-lease[=…]`, `--force-if-includes`, `--mirror`, ou un refspec `+…` | `--dry-run`, `-n`, `--help` | une branche de fonctionnalité est partagée entre un agent et l'orchestrateur ; réécrire son historique détruit les commits de l'autre et l'historique de revue |
| `push-main` | refspec dont la destination (partie après `:`, sinon le refspec ; `refs/heads/` retiré) vaut `<D>` ; `--all` ou `--branches` ; `--delete <D>` ; **push nu** ou refspec `HEAD`/`@` alors que la branche courante du dépôt jugé est `<D>` | push d'une autre branche, push nu depuis une branche de travail | `<D>` ne bouge que par une PR squash-mergée aux checks verts ; la protection de branche ne bloque pas toujours un admin (et pas du tout sans protection) |
| `stacked-pr` | `gh pr create` dont la base vaut autre chose que `<D>` | pas de base (défaut du dépôt) ; base `<D>` ; dépôt où l'utilisateur a mis `git config <ns>.allowStackedPr true` | une PR enfant mergée dans sa base après que la parente a été squashée n'arrive nulle part : les deux PR affichent « merged » et vert, et il faut une quatrième PR pour réparer |
| `merge-admin` | `gh pr merge … --admin` | — | `--admin` contourne les checks requis |
| `merge-squash` | `gh pr merge` sans `--squash`/`-s`, ou avec `--merge`/`-m`/`--rebase`/`-r` | `--help` | historique linéaire, un commit par thème : réversible en une fois, et c'est sur lui que le déploiement se cale |
| `merge-api` | `gh api` avec `-X PUT`/`--method PUT` sur un chemin finissant par `/pulls/<n>/merge` | `…/update-branch`, lectures | ce chemin contourne les deux règles précédentes |
| `user-only-config` | écriture `git config` de `<ns>.allowStackedPr` ou de `<ns>.deliveryAcknowledged` | lectures, `--unset` ; `branch.<b>.noPullRequest` (l'orchestrateur s'en sert pour les expériences de lane D) | ces clés désactivent un garde-fou ou taisent un avertissement de travail perdu : c'est la décision de l'utilisateur, prise dans son propre terminal ; le message donne la commande à lui transmettre |
| `unknown-repo` | un commit, un push nu ou un push `HEAD`/`@` dont le `cwd` vaut `null` | un `cd`/`git -C` absolu ultérieur ; un push avec refspec explicite ; un git en lecture | sans dépôt, aucune autre règle ne peut juger ; remède : `git -C <chemin absolu> …` |

Le déverrouillage `stacked-pr` se lit dans le dépôt jugé : `git -C <root> config --bool
<ns>.allowStackedPr` = `true` retire les blocs `stacked-pr`.

## 5. `guard_bash.py` : déroulement

Noms de règles fixes (repris tels quels par la page `Hooks.md` du wiki d'un projet, § What is
refused) : ceux du §4, plus `secret-path`, `secret-content`, `wip-shared-list`,
`wip-entry-deleted`, `detached-head`, `default-branch`, `stale-branch`, `already-on-default`,
`gates`, `gates-tool-missing`, `gates-error` et `bad-config`.

1. Lit le payload ; ignore si `tool_input.command` est vide. Appelle le parseur.
2. Pour chaque push et chaque commit, `root = repo_root(cwd)` (ou `None`).
3. Applique le déverrouillage, puis les règles qui dépendent de l'état (`push-main` sur push nu ou
   `HEAD` : branche courante de `root`). S'il reste des blocs : tous les messages sur stderr,
   **exit 2**.
4. Pas de commit → exit 0. Sinon, pour chaque commit dont `root` existe (un `git commit` hors
   dépôt échouera tout seul), dans l'ordre ci-dessous ; le premier refus sort en exit 2.

### 5.1 L'ensemble des chemins

Union, par construction un sur-ensemble :

- l'index : `git diff --cached --name-status` (le statut est gardé pour 5.2 et 5.3) ;
- sous `-a` : `git diff --name-status` (fichiers suivis modifiés — `git commit -a` les indexe
  **après** que le hook a lu l'index, qui paraîtrait vide) ;
- sous `--amend` : `git diff-tree --no-commit-id --name-status -r HEAD` ;
- les pathspecs, plus `git diff --name-status HEAD -- <pathspecs>` ;
- pendant un merge (`git rev-parse -q --verify MERGE_HEAD` réussit) : le diff de l'index est
  remplacé par `git diff --cached --name-status MERGE_HEAD` — ce qui diffère de la branche
  fusionnée : les changements propres de la branche et les résolutions, pas tout ce que le merge
  apporte ;
- les chemins d'un `git add` / `git rm` / `git mv` placé **avant** le commit sur la même ligne
  (`git add x && git commit …`) : le hook juge la ligne avant qu'elle s'exécute, l'index ne
  contient donc pas encore `x` — sans cela, le scan de secrets et le choix des gates le
  manqueraient.

Les gates sont globaux de toute façon : un sur-ensemble coûte des secondes, jamais un refus à tort.

### 5.2 Secrets

- **Par chemin** : un chemin ajouté ou modifié qui correspond à `SECRET_PATH_RE` et pas à
  `SECRET_ALLOW_RE` est refusé. Cela inclut `git add -f` d'un fichier ignoré.
- **Par contenu** : pour chaque fichier ajouté ou modifié ≤ 1 Mo et non binaire (pas d'octet NUL
  dans les 8 premiers Ko), le blob indexé (`git show :<path>`, ou le fichier de travail sous `-a`)
  est cherché pour `SECRET_CONTENT_RE`. Sont ignorés : un fichier qui correspond à
  `SECRET_ALLOW_RE`, ou qui porte le marqueur `secret-scan: fixture` dans ses 5 premières lignes
  (fausses clés de test). Chaque motif court de `SECRET_CONTENT_RE` est borné à gauche
  (`(?<![A-Za-z0-9_-])sk-…`) : sans cela, `risk-assessment-for-payments-module`, un nom de tâche
  ou un slug d'entrée `wip/` en kebab-case passent pour une clé. Les tests les gardent comme faux
  positifs : `risk-assessment-for-payments-module`, `task-queue-processing-worker` et
  `[[2026-09-01-desk-booking-calendar-export]]` passent.
- **Le message ne recopie jamais la correspondance** : il nommerait le secret dans le
  transcript. Il donne seulement le chemin et le *type* de motif (« private key header »,
  « cloud access key »…). Remède : `git reset -- <path>` (ou `git rm --cached`), déplacer la valeur
  dans un fichier non suivi, et la **révoquer** si elle a déjà été poussée.
- Pourquoi le contenu : une clé de compte de service téléchargée porte le nom du projet et d'un
  identifiant de clé ; aucune règle de chemin ne l'attrape une fois renommée.

### 5.3 `wip/`

Seulement si `<root>/wip/done/` existe :

- un `TODO.md` ou `DONE.md` **ajouté** à la racine est refusé : une liste partagée fait conflit sur
  chaque PR parallèle, et de vieilles sessions ou mémoires connaissent encore cette convention ;
- un fichier **supprimé** sous `wip/todo/`, `wip/todo_nr/` ou `wip/done/` sans fichier du même nom
  ajouté ailleurs sous `wip/` (un `git mv` apparaît comme `R` ou comme D+A du même nom) est
  refusé : une entrée ne se supprime jamais, elle part dans `done/` avec un statut `dropped`.

### 5.4 Discipline de branche

Seulement si `origin/<D>` existe dans `root` (le tout premier commit d'un dépôt neuf passe) :

- HEAD détachée : refus, un commit sur HEAD détachée n'appartient à aucune branche.
- Branche courante = `<D>` : refus, avec la recette
  `git fetch --prune origin && git worktree add <WORKTREE_PREFIX><topic> -b <type>/<topic> origin/<D>`.
- `git for-each-ref --format='%(upstream:track)' refs/heads/<b>` vaut `[gone]` : refus « branche
  périmée » — sa PR a été mergée et le remote l'a supprimée. Pourquoi `[gone]` et pas seulement
  `git cherry` : un squash change le patch-id, `git cherry` ne voit donc rien.
- Branche en avance de 1 à 50 commits sur `origin/<D>` et `git cherry origin/<D> HEAD` a une ligne
  `-` : refus, des commits déjà sur `<D>` (rejoués ou cherry-pickés ; le hook ne peut pas
  distinguer les deux et le dit).
- Recette imprimée pour les deux derniers cas :
  `git fetch --prune origin && git switch -c <type>/<topic> origin/<D>`, puis cherry-pick des
  commits marqués `+` par `git cherry -v origin/<D> <ancienne-branche>`.
- Le hook ne fetch pas : il juge l'état du dernier fetch, et laisse donc passer une branche
  périmée plutôt que d'en bloquer une saine.

### 5.5 Pas d'autres refus de contenu

Les règles de contenu propres à un projet (fichiers générés à jour, clés de traduction
cohérentes…) vont dans `scripts/check.sh fast`, pas ici : le hook reste générique et ne connaît
que l'interface de `check.sh`.

### 5.6 Gates : `scripts/check.sh fast` du dépôt jugé

- L'ensemble des chemins (un par ligne) est écrit dans un fichier temporaire ;
  `<root>/scripts/check.sh fast --paths-from <tmp>` tourne avec `cwd=<root>`, sous le délai
  `HOOK_GATE_TIMEOUT` (défaut 280 s, sous le `timeout: 300` du hook). C'est la copie **du dépôt
  jugé** : une branche qui change ses gates est jugée sur ses propres gates.
- `check.sh` absent ou non exécutable : passe, avec une note sur stderr (le cas du bootstrap).
- exit 0 : passe.
- exit 1 : refus, avec les 40 dernières lignes de la sortie combinée et la ligne
  « Reproduce with: … » que `check.sh` imprime.
- exit 3 : refus « tool missing », qui cite la dernière ligne `SETUP: <commande>` de stderr et dit
  de lancer cette commande **dans un appel Bash à part**, puis de recommiter — le hook juge la
  ligne entière avant que rien ne s'exécute, donc `install && git commit` ne passe jamais.
  Pourquoi refuser : un outil absent qui ferait « sauter » le gate est une régression silencieuse.
- délai dépassé ou autre code : refus, avec la fin de la sortie et `scripts/check.sh fast` comme
  commande à lancer soi-même.
- **Les tests ne tournent pas ici** : statique et rapide au commit (secondes, à chaud), suites de
  tests en CI. Lancer les tests au commit fait payer chaque changement deux fois et oblige un
  worktree à moitié installé à tout installer pour un commit de résolution d'une ligne. Rien ne
  part rouge pour autant : `require_pull_request` refuse de finir un tour sur une PR rouge.

## 6. `post_edit.py`

- Le dépôt est celui **du fichier édité** (`tool_input.file_path`), pas `CLAUDE_PROJECT_DIR` :
  sinon le hook vérifierait le checkout principal pendant qu'on édite un worktree. Fichier hors
  dépôt ou sous `.git/` : silence.
- Si `<root>/scripts/check.sh` est exécutable, il lance `scripts/check.sh edit <chemin relatif>`
  (`cwd=<root>`, délai 50 s). exit 1 avec un rapport : imprime
  `{"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": "Post-edit check on <path>:\n<rapport>"}}`.
  Tout le reste : silence, exit 0. **Jamais exit 2.**
- Pourquoi signaler sans bloquer : une modification qui touche plusieurs fichiers (une chaîne
  ajoutée dans dix fichiers de langue, une signature changée et ses appelants) est légitimement
  incohérente au milieu ; un refus dit au modèle que sa dernière édition est rejetée et l'invite à
  défaire du bon travail. Le refus arrive **une fois**, au commit (§5.6).
- `PostToolUse` ne se déclenche pas pour un fichier écrit par une commande Bash : ce hook est un
  confort ; la garantie est le gate de commit.

## 7. `require_pull_request.py` (`Stop` et `SubagentStop`)

**Pourquoi.** Un commit qui ne devient pas une PR n'est pas livré : personne ne l'a revu, la CI ne
l'a jamais vu, il n'existe que sur la machine qui le porte. `Stop` est le seul événement qui se
déclenche quand le travail est plausiblement fini ; `SubagentStop` empêche un agent de rendre la
main avec des commits non livrés. Une PR rouge n'est pas un changement livré non plus.

Jugé sur le `cwd` du payload (pour un agent : son worktree). **Silence** (exit 0, rien sur stdout)
si l'un de ces cas est vrai : `stop_hook_active` vrai (sinon le tour ne finit jamais : on ne
bloque qu'une fois par tour) · pas un dépôt · HEAD détachée · branche = `<D>` ·
`git config --bool branch.<b>.noPullRequest` vrai · pas d'`origin/<D>` · 0 commit d'avance
(`git rev-list --count origin/<D>..HEAD`) · origine non GitHub · `gh` absent ou non authentifié.

Sinon, `gh pr list --head <b> --state all --limit 1 --json number,state,url` :

| Réponse | Sortie |
|---|---|
| `MERGED` | silence : le travail est livré, même si l'`origin/<D>` local n'a pas encore été fetché (une première version, qui ne demandait que les PR ouvertes, bloquait chaque fin de tour après un merge) |
| `CLOSED` | bloque : « #n was closed without being merged. If the work is abandoned, say so to the user and run `git config branch.<b>.noPullRequest true`; otherwise open a new pull request. » |
| aucune PR | bloque : « Branch <b> has N commit(s) that no pull request covers. » + si `git status --porcelain` n'est pas vide (indexé, modifié **ou non suivi**) : « Commit the remaining changes first. » + « Then `git push -u origin <b>`, `gh pr create --base <D>` with a body saying what changed and why, watch `gh pr checks <n> --watch`, and report the URL and the check state. If this branch is deliberately held back, say so and run `git config branch.<b>.noPullRequest true`. » |
| `OPEN` | `gh pr checks <n> --required --json name,bucket` ; si cela échoue (pas de check requis, `gh` trop ancien pour `--json`), refait sans `--required`, puis en texte (colonne 2 = `fail`, sortie lue quel que soit le code : 1 = un échec, 8 = en attente). Au moins un `fail` : bloque « Pull request #n has failing checks: <noms>. A change is not finished while its CI is red: fix them — or, if a failure is unrelated to this change, say so to the user explicitly. » `pending`, `skipping`, `cancel`, tout vert : silence |

Le hook **lit** GitHub, il n'écrit jamais : pousser et ouvrir une PR sont des actes sortants qui
restent délibérés. Chaque appel `gh` est sous délai ; un réseau lent ne bloque pas une session.
Limite connue : seul le dossier courant de la session est jugé — un orchestrateur qui travaille
dans un worktree par `git -C` sans y être n'est pas couvert ; le rapport final de `ship-parallel`
l'est.

## 8. `session_start.sh` et `session_start.py`

`session_start.sh` (POSIX `sh`, exécutable) est le seul hook capable de parler quand Python
manque, donc il n'utilise que des commandes internes du shell :

- `python3` présent : `exec python3 "$(dirname "$0")/session_start.py"`.
- `python3` absent, et un `scripts/lib/tooling.conf` trouvé en remontant depuis le dossier courant :
  « WARNING: python3 is not installed: every shipyard hook (commit gates, push and merge guards,
  pull-request check) is OFF in this session. Install Python 3.9+ and restart. »
- `python3` absent, sans `tooling.conf` : rien, ou la suggestion du §1.4 dans un dossier vide (le plugin n'a pas à alarmer un
  dépôt qui ne l'utilise pas).

Dans tous les cas, exit 0.

`session_start.py` imprime, **seulement quand c'est pertinent**, en moins de 15 lignes au total (ce
texte entre dans le contexte de chaque session) :

1. **Dépendances** : Python < 3.9, `git` absent, `scripts/lib/tooling.conf` absent (silence, ou la
   suggestion du §1.4 dans un dossier vide), `gh` absent ou non authentifié (« pull-request checks and the merge loop
   are degraded »).
2. **Branche** (toujours) : `Branch: <b> (N ahead, M behind origin/<D>)`, ou `detached`. Sur `<D>` :
   « The main checkout stays on <D>; start work in its own worktree: » + la recette
   (`git fetch --prune origin && git worktree add <WORKTREE_PREFIX><topic> -b <type>/<topic> origin/<D>`
   puis `scripts/worktree_setup.sh <WORKTREE_PREFIX><topic>`). Branche `[gone]` ou avec une ligne
   `-` de `git cherry` : « not safe to commit on » + la recette du §5.4.
3. **Outillage vendorisé** (nouveau avec le plugin) : si `scripts/lib/VENDORED.json` porte une
   version plus ancienne que `${CLAUDE_PLUGIN_ROOT}/.claude-plugin/plugin.json`, ou si
   `bin/vendor.py --check` voit un fichier modifié, la ligne « vendored tooling is <x>, plugin is
   <y> — run /shipyard:sync-tooling ». Pourquoi : les copies vendorisées sont ce que la CI et
   l'humain exécutent sans Claude ; une copie en retard ou modifiée à la main est une dérive qu'il
   faut voir, pas une personnalisation silencieuse.
4. **Équipe** (nouveau, `TEAM_MODE=team` seulement) : le login GitHub de la session
   (`gh api user --jq .login`, mis en cache une journée dans `<git-common-dir>/shipyard/identity`)
   est cherché dans CODEOWNERS par `scripts/owners.py --who`. Absent : « You (@login) are not a
   code owner of this repository yet — run /shipyard:join before starting work: the team records
   who owns which part of the code. » Présent : « You own: <motifs> ». Sans `gh` : rien.
5. **Worktrees et branches mortes** : les autres worktrees (`git worktree list --porcelain` :
   chemin, branche) et le nombre de branches locales dont l'amont est `[gone]`, puis « Once no
   agent is working in them: `scripts/cleanup_local.py` (dry run), then `--apply`. »
6. **Livraison hors de `<D>`** (si `gh_ready`) : les PR mergées depuis 14 jours (date calculée en
   Python) dont la base ≠ `<D>` ; pour chacune non acquittée
   (`git config --get-all <ns>.deliveryAcknowledged`), le hook demande
   `gh api repos/{owner}/{repo}/compare/<D>...<merge commit> --jq .status` — à GitHub, parce que le
   commit de merge d'une branche supprimée peut ne pas exister dans le clone. Statut autre que
   `identical`/`behind` : « PR #n merged into <base>, not into <D>: its work may never have reached
   <D>. » + remède (rouvrir contre `<D>`, ou faire acquitter par l'utilisateur). Pourquoi : c'est
   le filet de sécurité de la règle `stacked-pr` quand le même échec arrive autrement.
7. **Niveau Complet, crons** : au plus une fois par jour (tampon `SCHEDULED_STAMP` à la racine, une
   date UTC), il lance `scripts/check_scheduled_runs.py` s'il existe ; imprime son rapport s'il
   sort 1 ; écrit le tampon **seulement si le code ≠ 3** (une session hors ligne n'achète pas un
   jour de silence). Pourquoi au démarrage : GitHub désactive un workflow planifié après 60 jours
   sans activité du dépôt, et c'est précisément une session qui rouvre un dépôt resté calme qui doit
   le voir.

Toujours exit 0 ; chaque appel `gh` sous délai, l'ensemble sous ~30 s.

## 9. `.githooks/pre-commit` : les commits humains

Les hooks Claude Code ne voient que les commandes de Claude : un commit fait dans un terminal ou
un IDE passerait sans gate jusqu'à la CI. Le hook git natif ferme ce trou. Il est **vendorisé**
(`templates/githooks/pre-commit` → `.githooks/pre-commit`) et ne dépend plus du plugin :

```sh
#!/usr/bin/env bash
# Gates for commits made outside Claude Code (terminal, IDE). Bypass deliberately: --no-verify.
[ "${CLAUDECODE:-}" = "1" ] && exit 0   # Claude Code's PreToolUse hook already ran the gates
root=$(git rev-parse --show-toplevel 2>/dev/null) || exit 0
command -v python3 >/dev/null 2>&1 || { echo "pre-commit: python3 missing, gates skipped" >&2; exit 0; }
exec python3 "$root/scripts/precommit.py"
```

- `scripts/precommit.py` (vendorisé lui aussi, parce que les hooks du plugin ne sont pas dans le
  dépôt) fait le **contrôle des secrets** (chemin et contenu, avec les mêmes `SECRET_*` de
  `tooling.conf` que la garde du §5.2) puis lance `scripts/check.sh fast --paths-from` sur les
  fichiers indexés. Git a déjà indexé les fichiers de `-a` à ce stade. Il imprime les refus sur
  stderr et sort **1** (code de refus d'un hook git), 0 sinon. La discipline de branche et les
  règles `wip/` restent des hooks Claude Code.
- `CLAUDECODE=1` est posé par Claude Code dans ses shells : `precommit.py` sort 0 tout de suite
  dans ce cas, sinon chaque commit de Claude paierait ses gates deux fois.
- Activation par clone : `git config core.hooksPath .githooks` (le bootstrap la pose ; le README
  d'un projet la documente pour un clone neuf ; les worktrees partagent ce réglage).
- `--no-verify` reste l'échappatoire humaine assumée ; la CI reste le dernier filet.

## 10. Tests : `tests/test_hooks.py`

**Pourquoi en CI.** Les cas intéressants sont ceux qui *ressemblent* à une violation et n'en sont
pas. Sans table exécutée à chaque push, le premier changement de règle casse une garde en
silence — et une garde cassée est indiscernable d'une garde qui laisse passer. La première
version du contrôle de PR n'avait de cas GitHub que là où `gh` était authentifié : la seule
réponse qu'elle n'avait jamais vue est celle qui l'a cassée. D'où le `gh` factice.

Les tests vivent dans le dépôt du plugin (`tests/test_hooks.py`, assistants dans
`tests/_hooks_*.py`), plus dans chaque projet. Commande :

```bash
python -m unittest discover -s tests -v
```

**Outillage.**

- `payload(**kw)` construit le JSON ; `run_hook(name, payload, env=…)` lance
  `python3 plugins/shipyard/hooks/<name>` (ou `session_start.sh`) depuis le dépôt du plugin, avec
  `CLAUDE_PLUGIN_ROOT` posé, et renvoie `(code, stdout, stderr)`.
- Un bac à sable git dans `tempfile.mkdtemp()` : un dépôt nu `remote.git`, un clone `main/`
  (`remote.origin.url = https://github.com/acme/demo.git` **et**
  `url.<chemin du dépôt nu>.insteadOf = https://github.com/acme/demo.git`, pour que git parle au
  dépôt nu pendant que les hooks voient une origine GitHub), un worktree `wt/` sur `feat/x`.
  Environnement isolé : `HOME=<tmp>`, `GIT_CONFIG_NOSYSTEM=1`, `GIT_CONFIG_GLOBAL=<tmp>/gitconfig`
  (`user.name`/`email`, `init.defaultBranch`, `commit.gpgsign=false`) — sinon un `core.hooksPath`
  ou une signature de l'utilisateur changent le résultat.
- Dans le bac à sable : `scripts/lib/tooling.conf` (valeurs de test) et un `scripts/check.sh`
  factice qui écrit ses arguments et le contenu de `--paths-from` dans un fichier, puis sort avec
  le code demandé par `CHECK_STUB_EXIT` (et imprime `SETUP: stub-install` pour 3, ou dort pour le
  cas de délai).
- Un `gh` factice (script Python dans un `bin/` placé en tête de `PATH`) qui lit un scénario JSON
  (`GH_STUB_SCENARIO`) : `auth status` → code ; `pr list` → liste ; `pr checks` → buckets ou
  erreur « no required checks » ; `api …/compare/…` → statut ; option `sleep`.
- Variables de délai pour les tests : `HOOK_GH_TIMEOUT=1`, `HOOK_GATE_TIMEOUT=2`.

**Cas couverts** (au moins 80 ; chaque groupe est une table de tuples parcourue par `subTest`) :

- **Refus (exit 2)** : `git push --force origin feat/x` · `-f` · `-fu` · `+feat/x` ·
  `--force-with-lease` · `--force-with-lease=feat/x:abc` · `--force-if-includes` · `--mirror` ·
  `git push origin main` · `feat/x:main` · `HEAD:refs/heads/main` · `--all` · `--delete main` ·
  push nu sur main · `git push origin HEAD` sur main · `gh pr create --base feat/y` ·
  `--base=feat/y` · `-B feat/y` · `gh pr merge 12` · `--merge` · `--rebase` · `-r` ·
  `--admin --squash` · `gh api -X PUT repos/o/r/pulls/12/merge` ·
  `git config <ns>.allowStackedPr true` · `git config --add <ns>.deliveryAcknowledged 12` ·
  `sudo -u x git push -f` · `env A=1 git push -f` · `time git push --force` ·
  `git -c a.b=c -C <abs> push --force` · `bash -c 'git push --force'` ·
  `sh -lc "git push origin main"` · `eval "git push -f"`.
- **Faux positifs (exit 0)** : `git push --dry-run --force origin feat/x` · `git push --help` ·
  `git push -u origin feat/x` · push nu et `git push origin HEAD` sur `feat/x` ·
  `gh pr create --base main` · sans base · base empilée avec `allowStackedPr` posé ·
  `gh pr merge 12 --squash --delete-branch` · `-sd` · `--squash --body "never use --admin"` ·
  `gh pr merge --help` · `gh api -X PUT …/update-branch` · `git config --get <ns>.allowStackedPr` ·
  `git config branch.feat/x.noPullRequest true` · `git config --unset <ns>.allowStackedPr` ·
  `echo "git push --force"` · heredoc qui contient `git push --force origin main` ·
  `git commit -m "never git push --force"` (gates factices à 0) · `grep -- --force f`.
- **Parseur** (verdict, pas code) : `cd <wt> && git commit` → cwd wt · `git -C <wt> commit` ·
  `W=<wt>; git -C "$W" commit` · `export W=<wt>; cd $W && git commit` · préfixe
  `W=<wt> git -C "$W" commit` → `unknown-repo` (exit 2) · `cd "$INHERITED" && git commit` →
  `unknown-repo` · `cd $(git rev-parse --show-toplevel) && git commit` → `unknown-repo` ·
  `X=$(date); git commit -m x` → commit · `(cd /tmp); git commit` → cwd du payload ·
  `git add . && git commit -am x` → all · `--amend --no-edit` → amend · `-m x -- a.py b.py` →
  pathspecs · `--dry-run` → pas de commit · `git log --grep=commit` → pas de commit · heredoc
  `$(cat <<'EOF' … EOF)` → commit, `parse_ok` · quote non fermée + `git commit` → commit supposé
  all+amend · ligne illisible avec `cd` et `git commit` → `unknown-repo` · `ls | xargs git rm` →
  aucun bloc.
- **Gates** : `check.sh` 0 → 0 · 1 → 2 avec la fin de sortie · 3 → 2 citant `stub-install` et
  « own Bash call » · absent → 0 avec note · délai → 2 · `-a` sans rien d'indexé → le fichier
  modifié est dans `--paths-from` · `--amend` sans rien d'indexé → fichiers de HEAD présents ·
  pathspec → présent · merge en cours → ensemble = diff contre `MERGE_HEAD` · commit par
  `git -C <wt>` depuis un payload dont le cwd est `main/` sur main → jugé sur `wt/` (passe).
- **Secrets** : `.env` indexé → 2 · `.env.example` → 0 · `config/deploy.env` → 2 · `key.pem` → 2 ·
  `creds-1234.json` contenant `"type": "service_account"` → 2 · fichier avec
  `-----BEGIN OPENSSH PRIVATE KEY-----` → 2 · JSON ordinaire → 0 · `git add -f .env` → 2 · fichier
  suivi modifié pour contenir une clé, commit `-a` → 2 · stderr ne contient **pas** la fausse clé ·
  fixture marquée `secret-scan: fixture` → 0 · binaire contenant le motif → 0.
- **wip** : `TODO.md` ajouté à la racine avec `wip/done/` → 2 · sans `wip/` → 0 ·
  `git rm wip/todo_nr/x.md` → 2 · `git mv wip/todo/x.md wip/done/x.md` → 0.
- **Branche** : commit sur main (avec `origin/main`) → 2 + recette · premier commit d'un dépôt sans
  `origin/main` → 0 · HEAD détachée → 2 · amont `[gone]` (pousser, supprimer la branche du remote,
  `fetch --prune`) → 2 + recette · commit déjà sur main cherry-pické → 2 · branche fraîche → 0 ·
  worktree sur sa branche pendant que `main/` est sur main → 0.
- **Stop / SubagentStop** : `stop_hook_active` → silence · sur main → silence · 0 d'avance →
  silence · aucune PR → bloc avec `gh pr create --base main` · + fichier modifié → « Commit the
  remaining changes first » · + fichier **non suivi** seul → idem · MERGED → silence · CLOSED →
  bloc · OPEN vert → silence · OPEN avec un `fail` → bloc qui nomme le check · OPEN `pending` →
  silence · `--required` en erreur → repli sur tous les checks · `noPullRequest` → silence · `gh`
  absent du PATH → silence · `gh auth status` à 1 → silence · origine non GitHub → silence · `gh`
  qui dort → silence dans le délai · payload `SubagentStop` dont le cwd est `wt/` avec des commits
  et sans PR → bloc (jugé sur le worktree, pas sur `main/`) · sortie = JSON valide avec `decision`
  et `reason`.
- **SessionStart** : sur main → ligne `Branch:` + recette · autre worktree → listé + pointeur
  `cleanup_local.py` · branche `[gone]` → comptée · branche courante périmée → « not safe to commit
  on » · `tooling.conf` absent → silence, ou la suggestion du §1.4 dans un dossier vide · `gh` absent → mention dégradée, exit 0 ·
  PR mergée dans `feat/y` avec compare `ahead` → signalée ; acquittée → plus signalée · (Complet)
  tampon : un seul passage par jour ; code 3 → pas de tampon · `session_start.sh` avec un `PATH`
  sans `python3` → `WARNING`, exit 0 · version vendorisée en retard ou fichier modifié → ligne
  `/shipyard:sync-tooling` · équipe : login absent de CODEOWNERS → invite à `/shipyard:join`,
  présent → « You own: … », sans `gh` → rien.
- **post_edit** : édition dans `wt/` → le `check.sh` de `wt/` est appelé (pas celui de `main/`) et
  `additionalContext` est un JSON valide quand il sort 1 · sortie 0 → rien · fichier hors dépôt →
  rien · `check.sh` absent → rien · `check.sh` qui plante → exit 0.
- **Inertie** : sans `tooling.conf`, chaque hook sort 0 sans rien imprimer (sauf `SessionStart`, qui
  suggère `/shipyard:bootstrap` dans un dossier vide).
- **pre-commit** : `CLAUDECODE=1` → 0 immédiat · sans → secrets contrôlés et gates factices
  appelés, refus → 1.
- **Câblage** : `hooks.json` est un JSON valide ; chaque commande référencée (après substitution de
  `${CLAUDE_PLUGIN_ROOT}`) existe et est exécutable ou est un `.py` existant ; chaque hook compile
  (`py_compile`) ; aucun import hors bibliothèque standard ; un stdin invalide donné à chaque hook
  → exit 0.

La suite tourne en quelques secondes, sans réseau, dans le job `tests` de la CI du dépôt, sur
Linux (Python 3.9 et 3.12) et macOS.

### 10.1 Ajouter ou modifier une règle

1. Écrire le cas (refus **et** faux positif voisin) dans la table du groupe, voir échouer le test.
2. Changer le hook. Un message de refus nomme la règle et finit par le remède.
3. Mettre à jour ce document et l'entrée de `CHANGELOG.md`. Les hooks ne sont pas vendorisés : un
   changement de règle est une version patch ou mineure du plugin ; seul un changement d'un
   gabarit (`templates/`) demande « run `/shipyard:sync-tooling` » dans le changelog.

## 11. Ce que les hooks ne couvrent pas

- **Ce qu'écrit une commande Bash** : `PostToolUse` ne se déclenche pas ; la garantie est le gate
  de commit.
- **Un merge par l'interface web**, ou par une API autre que celles lues au §4 : seule la
  protection de branche se tient derrière.
- **`git merge`, `git rebase --continue`, `git revert`, `git cherry-pick`**, et tout commit fait
  *à l'intérieur* d'un script lancé (`bash scripts/x.sh`) : le hook ne voit que la ligne qu'on lui
  donne (le `pre-commit` git couvre les commits normaux, pas `merge` sans conflit).
- **La fraîcheur d'`origin`** : les hooks ne fetchent jamais ; un silence n'est pas une preuve.
- **Publier** : le hook de PR lit GitHub, il ne pousse ni n'ouvre rien.
- **Une session sans le plugin** : une session de code distant ne charge pas les marketplaces du
  projet ; les hooks n'y tournent pas, sauf si le plugin est synchronisé avec le compte. Les
  copies vendorisées (`pre-commit`, CI) restent actives, elles.
- **L'exécution elle-même** : un script de hook absent ou non exécutable sort 127, qui ne bloque
  pas ; un hook qui dépasse son délai ne bloque pas non plus. Les hooks réduisent une classe
  d'erreurs, ils ne la rendent pas impossible.

## 12. Envisagé, non retenu

- **Hook `WorktreeCreate`** pour lancer `worktree_setup.sh` automatiquement : il *remplace* la
  création du worktree (le hook doit la faire et imprimer le chemin) ; un bug y bloquerait tous
  les agents isolés à la fois. Le setup reste la première étape du prompt d'implémenteur.
- **`permissionDecision: "allow"` en `PreToolUse`** pour auto-approuver les commandes jugées sûres :
  le parseur deviendrait une frontière de sécurité, ce qu'il n'est pas (§3.3). L'autonomie vient de
  l'allowlist et du mode de l'utilisateur.
- **Refuser un formateur** (pour éviter qu'un reformatage massif se glisse dans un diff
  fonctionnel) : cela force un outil sûr à passer par l'utilisateur et continue de refuser une fois
  la dette payée. Le format est imposé dans l'autre sens : `format --check` est un gate.
- **Un `PostToolUse` bloquant** : voir §6.
- **Une garde par heuristique** pour les règles de jugement (texte en dur, doc à jour) : elle
  crierait au loup ; ces règles restent en prose, et une revue les mesure.

## 13. Décisions et historique

Chaque ligne est une décision, avec sa raison ; les incidents cités ont été observés à l'usage.

- **Pourquoi des hooks.** Les règles qu'un script peut décider sont des refus ; les règles de
  jugement restent en prose, parce qu'une garde qui crie au loup est pire que la prose.
- **Pourquoi un parseur et pas un grep.** Le quoting, les `echo` et les heredocs qui documentent
  une commande interdite.
- **Pourquoi « je ne sais pas » plutôt que juger le checkout de lancement.** Des lignes illisibles
  et un `$W` non expansé ont fait passer le travail d'un worktree pour des commits sur la branche
  par défaut.
- **Pourquoi `[gone]` et pas seulement `git cherry`.** Un merge en squash change le patch-id.
- **Pourquoi des gates rapides au commit et les tests en CI.** Les tests étaient payés deux fois ;
  rien ne part rouge parce que le hook `Stop` refuse une PR rouge.
- **Pourquoi un hook `Stop` et `SubagentStop`.** Un commit non poussé n'est pas livré ; le hook
  bloque une fois par tour ; il demande tous les états de PR parce qu'une requête limitée aux PR
  ouvertes bloquait indéfiniment après un merge.
- **Pourquoi les PR empilées sont refusées.** Une enfant mergée dans une parente déjà squashée
  n'arrive nulle part alors que les deux affichent « merged » et vert.
- **Pourquoi le force-push, le push sur la branche par défaut et `--admin` sont refusés même avec
  une protection de branche.** L'agent merge ses propres PR ; un jeton de propriétaire peut
  contourner la protection.
- **Pourquoi les secrets sont aussi cherchés par contenu.** Les clés téléchargées portent des
  identifiants, pas des noms de rôle.
- **Pourquoi `PostToolUse` signale au lieu de bloquer.** Une modification sur plusieurs fichiers
  est incohérente en son milieu.
- **Pourquoi les tests tournent en CI avec un `gh` factice.** Une garde cassée ressemble à une
  garde qui passe.
- **Pourquoi les hooks vivent dans le plugin** (nouveau). Le code générique est écrit et testé une
  fois, et un correctif atteint tous les projets à `/plugin update`, au lieu d'être régénéré (et de
  varier) à chaque bootstrap. Contrepartie : les règles en vigueur sont celles de la version du
  plugin, et une session sans le plugin n'en a aucune (§11).
- **Pourquoi les hooks sont inertes sans `tooling.conf`** (nouveau). Un plugin activé dans un
  dépôt qui n'a rien demandé ne doit rien refuser (§1.4).
- **Pourquoi `pre-commit` est vendorisé et plus court que la garde** (nouveau). Il tourne sans
  Claude, donc sans plugin : il porte seulement ce qu'un terminal ou un IDE peut contourner sans
  que la CI le voie venir (secrets, gates).
- **Envisagé et non retenu** : voir §12.

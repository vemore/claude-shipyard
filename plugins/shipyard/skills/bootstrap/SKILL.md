---
name: bootstrap
description: "Démarre un nouveau projet dans un dossier vide avec l'outillage shipyard — un questionnaire unique au début (stack, forge, déploiement, autonomie, risque, solo ou équipe et zones de code), puis, sans autre validation, dépôt GitHub, squelette de la stack, CLAUDE.md, wiki LLM (.llmwiki/), backlog wip/ à un fichier par entrée, copies vendorisées des scripts de process, CI scopée, CODEOWNERS en équipe et protection de branche ; les hooks, agents et skills de livraison viennent du plugin. Use when starting a project from an empty folder with the shipyard plugin. Triggers — « nouveau projet », « initialise un projet », « démarre un projet », « bootstrap », « set up a new repo », « start a new project »."
disable-model-invocation: true
---

# shipyard:bootstrap

Tu installes, dans un dossier vide, un projet prêt à être développé par plusieurs agents
Claude Code en parallèle. Le **plugin** apporte ce qui est générique et testé une fois : les
hooks (garde-fous git, gates au commit, PR obligatoire et verte), les agents
`shipyard:implementer-simple`, `shipyard:implementer-complex` et `shipyard:reviewer`, et les
skills `ship-parallel`, `wip-refine`, `join`, `sync-tooling`. **Toi**, tu ne produis que ce qui
est propre au projet. **Toutes les questions se posent au début (§2) ; ensuite tu ne t'arrêtes
plus** que dans les trois cas de §10.

Les annexes sont dans `${CLAUDE_PLUGIN_ROOT}/skills/bootstrap/references/` ; « annexe N »
désigne le fichier `0N-*.md` de ce dossier. Lis maintenant l'annexe 01 (la doctrine : le
*pourquoi* de tout ce qui suit) et l'annexe 00 (le contrat d'un projet). Les autres se lisent
au moment où une section les cite.

## 0. Ce que tu produis

| Résultat | Où | Par |
|---|---|---|
| Une source unique pour les valeurs du projet | `scripts/lib/tooling.conf` | toi, §4 |
| Les décisions et leurs raisons | `.llmwiki/Project.md` | toi, §4 |
| Activation du plugin, marketplace, permissions | `.claude/settings.json` | toi, §4 (annexe 03 §2) |
| Zones de code et leurs owners (équipe) | `.github/CODEOWNERS` | toi, §4 |
| Scripts de process que la CI et l'humain lancent, et leurs selftests | `scripts/…`, `.githooks/pre-commit` | `bin/vendor.py`, §4 |
| Squelette de la stack, un test, des gates rapides réels | `src/`…, `scripts/check.sh` | WP-A (annexe 05) |
| Mémoire : CLAUDE.md court, wiki, `Team.md` en équipe, backlog initial | `CLAUDE.md`, `.llmwiki/`, `wip/` | WP-D (annexes 03, 04, 06) |
| CI scopée, dépendances | `.github/` | WP-F (annexe 08) |
| Skills de projet `deploy` / `release` (si besoin) | `.claude/skills/` | WP-E (annexe 07) |
| Dépôt GitHub réglé et branche protégée | forge | toi, §3 et §8 (annexe 08 §7) |

Rien n'est supposé sur la machine, le compte ou l'hébergement : tout vient du questionnaire.
Un **mode test** (§11) exécute tout sans aucune action sortante.

## 1. Pré-vol (lecture seule)

```bash
pwd; ls -A                      # doit être vide
git --version; python3 --version          # python3 >= 3.9 : hooks et scripts en dépendent
gh --version && gh auth status            # scopes « repo » et « workflow » nécessaires
gh api user --jq '.login + " " + (.plan.name // "unknown")'
gh api user/orgs --jq '.[].login'
python3 -c 'import json,os; p=os.path.expanduser("~/.claude/settings.json"); print(json.load(open(p)).get("permissions",{}).get("defaultMode","default") if os.path.exists(p) else "default")'
python3 -c 'import json; print(json.load(open("${CLAUDE_PLUGIN_ROOT}/.claude-plugin/plugin.json"))["version"])'
```

- **Dossier non vide** : arrête-toi et dis-le. La reprise d'un projet existant n'est pas
  couverte par ce skill ; ne pas improviser.
- Un outil manque : rassemble **tous** les manques dans un seul message. Une authentification
  interactive se fait par l'utilisateur : `! gh auth login -s repo,workflow`.
- Note le login, le plan GitHub (souvent `unknown`), le mode de permissions et la version du
  plugin : ils servent au questionnaire et au contrat.

## 2. Questionnaire — annexe 02

1. **Description libre d'abord**, en un seul message si l'argument du skill ne la donne pas :
   ce que fait le projet, pour qui, stack pressentie, cible de déploiement, 3 à 8 premières
   fonctionnalités, solo ou en équipe, contraintes.
2. **Au plus trois rondes** `AskUserQuestion` (≤ 4 questions chacune). Chaque option par
   défaut est déduite de la description et du pré-vol, et marquée « (Recommandé) ». Ne pose
   jamais une question dont la réponse se déduit : affiche la valeur déduite dans le
   récapitulatif, où elle reste modifiable. En équipe, la personne qui lance le bootstrap dit
   de quelles parties du code elle sera responsable ; les suivantes le diront avec
   `/shipyard:join`.
3. **Avant le récapitulatif, vérifie en lecture seule ce qui ferait échouer l'exécution** :
   - la toolchain de la stack choisie (`uv --version`, `node --version`, `go version`…) ;
   - le nom : `gh repo view <owner>/<slug>` doit échouer (nom libre) ;
   - les droits sur l'organisation, si l'owner en est une
     (`gh api orgs/<org>/memberships/<login> --jq .role`).
   Un manque se règle maintenant (installation par l'utilisateur, autre nom), pas après.
4. **Un récapitulatif** (aperçu complet : valeurs, fichiers, actions sortantes, résultats du
   point 3) qui vaut **feu vert unique** pour tout ce qui suit — création du dépôt, push,
   réglages, merge de la PR de bootstrap, protection de branche, PR `docs/` de §8 si besoin.
   Si l'utilisateur ajuste, ne repose que ce qui change.

Après le feu vert, une décision non couverte se prend avec les réponses et les défauts de
l'annexe 02, et s'écrit dans `.llmwiki/Project.md` § Decisions avec sa raison.

## 3. Dépôt et worktree de bootstrap

Dans le dossier du projet (le « checkout principal ») :

```bash
git init -b <DEFAULT_BRANCH>
# .gitignore : modèle GitHub de chaque langage (gh api gitignore/templates/<Lang> --jq .source)
#   + les lignes demandées par les annexes (06 §6 notamment) : marqueurs ancrés « / »,
#     .claude/settings.local.json, .claude/worktrees/, CLAUDE.local.md, .env, .env.*,
#     !.env.example, <DEPLOY_ENV_FILE>, evals/runs/, .obsidian/, __pycache__/ (les copies
#     vendorisées sont en Python quelle que soit la stack)
git check-ignore --no-index -v scripts/lib/tooling.conf scripts/lib/conf.py \
  scripts/selftest/test_wip.py .githooks/pre-commit wip/todo/.gitkeep .llmwiki/INDEX.md
#   doit ne rien imprimer : un modèle de langage ignore parfois un dossier de l'outillage
#   (le modèle Python contient « lib/ », qui ignore scripts/lib/) — ancre la règle (« /lib/ »)
# LICENSE    : gh api licenses/<spdx> --jq .body, année et titulaire remplacés (sauf « propriétaire »)
# README.md  : titre + une phrase ; WP-D l'écrit pour de vrai
git add -A && git commit -m "chore: initial commit"
gh repo create <owner>/<slug> --<private|public> --source . --remote origin --push
gh api -X PATCH repos/<owner>/<slug> ...      # réglages : annexe 08 §7
gh api repos/<owner>/<slug>/branches/<DEFAULT_BRANCH>/protection 2>&1 | grep -q 'Upgrade to GitHub Pro' \
  && echo "protection: unavailable" || echo "protection: available"   # lecture seule ; 404 « not protected » = disponible
git fetch origin
git worktree add --no-track -b chore/bootstrap ../<slug>-bootstrap origin/<DEFAULT_BRANCH>
```

Ce commit initial est **le seul** qui ira jamais directement sur la branche par défaut. Le
checkout principal reste ensuite sur elle, sans jamais commiter (annexe 01). La sonde de
protection juge le dépôt réel (une organisation a son propre plan) : son verdict va dans
`Project.md`.

## 4. Le contrat et les copies vendorisées

Dans le worktree de bootstrap, avant tout lot :

1. `scripts/lib/tooling.conf` (annexe 00 §2), une ligne de commentaire par clé — dont
   `COMPONENTS` et un `COMPONENT_<ID>_RE` par composant, `TEAM_MODE`, `AUTONOMY`,
   `RELEASE_MODE` — avec les valeurs du questionnaire (correspondances : annexe 02 §7).
2. `.llmwiki/Project.md` avec le gabarit de l'annexe 02 §6 : identité, composants (répertoires,
   audit des dépendances, nom du job CI), skills, livraison, verdict de la sonde de
   protection, risque, agents (modèles fixés par le plugin), équipe, niveau de gates, posture
   de permissions, fonctionnalités initiales mot pour mot, éléments différés **avec le nom de
   fichier de leur future entrée `wip/todo_nr/`**, et une entrée `Decisions & History` par
   réponse.
3. `.claude/settings.json` (annexe 03 §2) : la marketplace `claude-shipyard`,
   `"enabledPlugins": {"shipyard@claude-shipyard": true}` et les permissions de la posture
   choisie — **au niveau du projet**, pour que les garde-fous ne jugent aucun autre dépôt de
   l'utilisateur. Pas de bloc `hooks` : ils viennent du plugin.
4. En équipe : `.github/CODEOWNERS` (annexe 08 §7.3) — en tête le commentaire qui dit qu'il
   est tenu par `/shipyard:join`, puis les chemins d'outillage (`/.claude/`, `/scripts/`,
   `/.github/`, `/CLAUDE.md` ; jamais `wip/` ni `.llmwiki/`) et la zone déclarée, au login de
   la personne qui bootstrappe.
5. Les copies vendorisées :
   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/bin/vendor.py" <worktree>
   python3 "${CLAUDE_PLUGIN_ROOT}/bin/vendor.py" --check <worktree>    # doit dire ok
   ```
   Elles ne se modifient jamais à la main : une évolution passe par le plugin, puis
   `/shipyard:sync-tooling`.

Ces fichiers sont le contrat du projet : chaque lot les lit, aucun ne les modifie.

## 5. Fan-out — les lots en parallèle

Lance les lots **dans un seul message**, `subagent_type: "general-purpose"`,
`model: "sonnet"`, sans `isolation` (ils partagent le worktree de bootstrap et ne se touchent
pas : la propriété des fichiers est fixée par l'annexe 00 §3). WP-E n'existe que s'il y a une
cible de déploiement ou des releases planifiées.

| Lot | Écrit | Lit |
|---|---|---|
| **WP-A** stack | code et tests de la stack, manifestes, configs, `scripts/check.sh`, `scripts/selftest/test_check.py`, `.env.example` | 00, 05, Project.md |
| **WP-D** connaissance | `CLAUDE.md` (racine et composants), `README.md`, `.llmwiki/**` sauf Project.md (dont `Team.md` en équipe), `wip/**`, `.claude/rules/**` | 00, 01, 03 §1, §3, §4, §6, 04, 06 |
| **WP-F** CI | `.github/**` sauf CODEOWNERS | 00, 08 |
| **WP-E** skills de projet | `.claude/skills/{deploy,release}/**`, `<DEPLOY_ENV_FILE>.example` | 00, 07 |

Prompt de chaque lot (remplis, ne raccourcis pas les règles) :

```text
Tu es le lot <WP-X> du bootstrap du projet <slug>. Worktree : <chemin absolu>.
Spécification : <chemin absolu du dossier references/> — lis l'annexe 00 (contrat), puis : <annexes du lot>.
Valeurs : <worktree>/scripts/lib/tooling.conf et <worktree>/.llmwiki/Project.md (lecture seule).
Les scripts de <worktree>/scripts/ listés dans <worktree>/scripts/lib/VENDORED.json sont des
copies du plugin shipyard : tu les utilises, tu ne les modifies jamais.
Tu écris uniquement : <fichiers du lot, annexe 00 §3>. D'autres agents écrivent le reste en
ce moment même dans ce worktree.

Règles :
1. Commence chaque commande Bash par `cd <worktree> && ` : ton répertoire de départ est le
   checkout principal, qui ne contient que le commit initial.
2. N'exécute aucune commande git qui écrit (add, commit, stash, checkout, switch, reset) :
   l'index est partagé ; l'orchestrateur commite. Les essais git (dépôts bac à sable) se font
   dans tes tests, sous un dossier temporaire.
3. Le contrat (annexe 00) prime sur tout. Une interface qui y manque : ne l'invente pas,
   signale-la. Une ligne nécessaire hors de tes fichiers (.gitignore, README, une entrée
   wip/) : décris-la dans ton rapport.
4. Langue : documentation en <langue de doc> ; messages, identifiants, noms de fichiers en anglais.
5. Aucun secret, hôte, URL privée ou identifiant réel dans un fichier ; aucun nom de
   personne ou d'organisation hors de ce que Project.md et CODEOWNERS contiennent.
6. Lance les tests et selftests de tes fichiers ; corrige jusqu'au vert. Un test qui dépend
   d'un fichier d'un autre lot peut rester rouge tant que ce fichier n'existe pas : dis-le
   dans ton rapport, n'écris jamais de bouchon à sa place dans un fichier qui sera commité.
   Disjoncteur : trois tentatives sur le même échec, puis arrête et classe-le TEST_ISSUE,
   IMPL_ISSUE, DOC_ISSUE ou UNCLEAR, sans jamais assouplir un test.
7. Une valeur que tu ne peux pas connaître avant la fin des autres lots : laisse un marqueur
   `<!-- FILL: <quoi> -->` et cite-le dans ton rapport ; l'orchestrateur le remplit.
8. Rapport bref : fichiers écrits, commandes de vérification lancées et leur résultat,
   interfaces manquantes, lignes demandées ailleurs, marqueurs FILL, `<TODO>` laissés,
   écarts à la spec et pourquoi.
```

## 6. Intégration

Attends les rapports. Puis, dans le worktree de bootstrap :

1. Ajoute les lignes demandées hors des lots ; écris les entrées `wip/` que les lots ont
   décrites (un `<TODO>` de skill, un outil non installable) ; remplis les marqueurs
   `<!-- FILL: … -->`. Une interface signalée manquante se tranche dans `tooling.conf`,
   `Project.md` et les fichiers concernés — jamais en modifiant une copie vendorisée ni le
   plugin.
2. `scripts/worktree_setup.sh .` (dépendances, codegen) puis
   `git config core.hooksPath .githooks`.
3. Tout doit être vert :
   ```bash
   scripts/selftest.sh
   scripts/check.sh all
   python3 scripts/wiki_lint.py
   python3 scripts/wip.py check
   python3 "${CLAUDE_PLUGIN_ROOT}/bin/vendor.py" --check .
   ```
4. Essais à blanc des hooks du plugin, contre ce projet (payload JSON sur stdin, `cwd` = le
   worktree) : `python3 "${CLAUDE_PLUGIN_ROOT}/hooks/guard_bash.py"` refuse
   `git push --force origin HEAD` et `gh pr merge 1 --merge` (sortie 2, avec le remède) et
   laisse passer `git status` (sortie 0, rien imprimé).
5. Cohérences croisées :
   - **aucun fichier produit n'est ignoré** : `git status --porcelain --ignored -- scripts
     .claude .llmwiki wip .github` ne liste aucune ligne `!!` hors caches ;
   - les skills cités par `CLAUDE.md` et `INDEX.md` existent (ceux du plugin sous
     `/shipyard:…`, ceux du projet sous `.claude/skills/`) ;
   - chaque script cité par un skill de projet ou `ci.yml` existe et est exécutable ; chaque
     chemin entre backticks de `CLAUDE.md` et `README.md` existe (hors syntaxes génériques) ;
   - les `name:` des jobs de `ci.yml` = les noms de `Project.md` ; `ci_scope.py` sort une ligne
     par composant de `COMPONENTS`, et un fichier de chaque composant le marque `true` ;
   - en équipe : `scripts/owners.py --who <login>` répond par la zone déclarée ;
   - `wc -l CLAUDE.md` ≤ `CLAUDE_MD_BUDGET` ; les pages wiki ≤ `WIKI_PAGE_BUDGET` ;
   - aucun gabarit resté non rempli (`<…>` qui désignait une valeur du questionnaire,
     `<!-- IF`, `<!-- FILL`) ; aucun secret (`SECRET_CONTENT_RE` sur l'arbre) ; aucun hôte réel.
6. Corrige toi-même ce qui est petit. Ce qui ne l'est pas : `SendMessage` au lot concerné avec
   le constat, ou un nouvel agent sur ce lot. Disjoncteur de §10.

## 7. Livrer le bootstrap

Les hooks du plugin ne jugent pas encore ce dépôt dans cette session (le plugin s'active par
le `settings.json` que tu viens d'écrire, lu au prochain démarrage) : les vérifications de §6
en tiennent lieu.

```bash
git add -A && git commit -m "chore: bootstrap with shipyard <version>"
git push -u origin chore/bootstrap
gh pr create --base <DEFAULT_BRANCH> --title "chore: bootstrap with shipyard <version>" --body "<quoi, pourquoi, décisions clés, lien vers .llmwiki/Project.md>"
gh pr checks <n> --watch
```

Corrige ce qui échoue dans le worktree, en commits ordinaires (jamais d'amend poussé, jamais
de force-push), jusqu'au vert. Puis, au titre du feu vert de §2 et quelle que soit
l'autonomie choisie pour la suite :

```bash
gh pr merge <n> --squash --match-head-commit "$(git rev-parse HEAD)"
git -C <checkout principal> fetch --prune origin
git -C <checkout principal> merge --ff-only origin/<DEFAULT_BRANCH>
```

Pas de `--delete-branch` : avec des worktrees, gh essaie de passer la branche locale sur la
branche par défaut, déjà prise par le checkout principal, et échoue après un merge réussi —
le réglage `delete_branch_on_merge` du dépôt supprime la branche distante, `cleanup_local.py`
la locale.

**PR encore rouge après le disjoncteur** : ne la merge pas. Saute §8 et le retrait du
worktree de §9, et rapporte la PR avec la classe de son échec.

## 8. Protection de la branche par défaut — annexe 08 §7

Après le merge (les noms des checks existent alors) : `gh api -X PUT …/protection`, puis
relis-la avec `GET` et compare aux valeurs attendues que WP-D a écrites dans
`ParallelDelivery.md`. Jamais `require_code_owner_reviews` au bootstrap (annexe 08 §7.3).
Si `Project.md` dit la protection indisponible (sonde de §3), ne l'appelle pas : WP-D a déjà
écrit l'entrée `wip/todo_nr/` et la page le dit.

Si le `PUT` répond 403 malgré la sonde, ou si la relecture diffère des valeurs attendues,
consigne-le par une petite PR `docs/protection-<YYYY-MM-DD>` — `Project.md`,
`ParallelDelivery.md`, `KnownLimits.md`, une entrée `wip/todo_nr/` — faite dans un worktree
neuf comme toute autre PR et mergée en squash une fois verte, au titre du même feu vert.

## 9. Nettoyage et rapport

```bash
git worktree remove ../<slug>-bootstrap
python3 scripts/cleanup_local.py && python3 scripts/cleanup_local.py --apply
git status && git worktree list && git branch -vv   # seulement la branche par défaut, à jour
```

Si le récapitulatif l'a accepté, ajoute le paragraphe `autoMode.environment` (annexe 03 §2) à
`~/.claude/settings.json`, en relisant le fichier avant d'écrire.

Rapport à l'utilisateur, dans sa langue :
- l'URL du dépôt, de la PR de bootstrap et l'état de ses checks ;
- ce qui est installé, en un tableau ; la version de shipyard vendorisée ;
- les décisions prises sans lui après le feu vert, et pourquoi ;
- les vérifications de §6 et leur résultat ; la protection (relue ou indisponible) ;
- ce qui est différé, sous forme d'entrées `wip/todo_nr/` ;
- **la suite** :
  1. quitter puis relancer Claude Code dans le dossier et accepter de faire confiance au
     dossier : le plugin s'active pour ce projet, et le message de `SessionStart` apparaît ;
     `git push --force` doit être refusé ;
  2. en équipe : chaque coéquipier clone le dépôt, l'ouvre dans Claude Code (le
     `settings.json` du projet lui propose la marketplace et le plugin), puis lance
     `/shipyard:join` — le hook de démarrage le lui rappelle tant qu'il n'est pas owner ;
  3. lancer `/shipyard:ship-parallel` (ou « attaque wip/todo en parallèle ») sur le backlog ;
  4. `/shipyard:wip-refine` quand `wip/todo_nr/` dépasse `REFINE_THRESHOLD` ; après une mise à
     jour du plugin, `/shipyard:sync-tooling`.

## 10. Garde-fous du bootstrap

- **Après le feu vert, trois raisons seulement de t'arrêter** :
  1. un identifiant, un outil ou un accès que seul l'utilisateur peut fournir et que §2.3
     n'a pas pu vérifier ;
  2. une action sortante ou irréversible que le feu vert ne couvre pas ;
  3. une contradiction entre deux réponses, découverte en travaillant.
  Tout le reste se décide avec les réponses et les défauts de l'annexe 02, et s'écrit dans
  `Project.md` § Decisions.
- **Disjoncteur** : trois tentatives sur le même échec (un lot, un check CI), puis tu arrêtes
  cette ligne, tu la classes (`TEST_ISSUE`, `IMPL_ISSUE`, `DOC_ISSUE`, `UNCLEAR`), tu continues
  le reste et tu la rapportes (§7 dit ce qui en découle pour la PR de bootstrap). Jamais de
  test assoupli, sauté ou supprimé pour passer.
- Jamais de secret, d'hôte réel, d'URL privée ni d'identifiant dans un fichier suivi : les
  cibles de déploiement vont dans `DEPLOY_ENV_FILE` (non suivi) avec un modèle
  `<DEPLOY_ENV_FILE>.example` suivi.
- Jamais de force-push, jamais de push sur la branche par défaut après le commit initial,
  merge en squash seulement — les règles que les hooks imposeront dès la prochaine session.
- Jamais de modification d'une copie vendorisée ni du plugin pendant un bootstrap : un défaut
  du plugin se signale dans le rapport (et sur le dépôt du plugin), le projet le contourne
  par une entrée `wip/`.
- Rien n'est écrit hors du dossier du projet, sauf : le worktree de bootstrap (dossier
  parent), le remote local du mode test, et le paragraphe `autoMode.environment` accepté au
  récapitulatif.

## 11. Mode test

Déclenché par l'argument `--test <fichier-de-réponses>` (format : annexe 02 §8). Il sert à
valider le plugin lui-même — en local, avec `claude --plugin-dir <dépôt>/plugins/shipyard` ; il
ne pose aucune question et ne fait **aucune action sortante** (les lectures publiques —
modèles `.gitignore` et licences — restent permises ; sans réseau, écris un `.gitignore`
minimal).

- §2 : les réponses viennent du fichier ; les vérifications de §2.3 sont faites, le
  récapitulatif est imprimé, pas demandé.
- §3 : après le commit initial, `git clone --bare <dossier> <dossier>/../<slug>-origin.git`
  sert de remote `origin` (`git remote add`, `git fetch`, `git branch -u origin/<défaut>`) — un
  clone, pas un push sur la branche par défaut ; pas de `gh repo create`, pas de réglages
  GitHub, sonde de protection remplacée par « non applicable ». Si la session qui exécute le
  test a d'autres hooks actifs, fais `git init` et le commit en deux commandes séparées, avec
  `git -C <chemin littéral>`.
- §4 à §6 inchangés — c'est ce qu'on teste.
- §7 : commit sur `chore/bootstrap` et push vers le remote local ; pas de PR. §8 et §9 sautés.
- Rapport : résultat de chaque commande de §6 et liste des écarts à la spécification.

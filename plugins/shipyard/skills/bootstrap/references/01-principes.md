# Annexe 1 — La doctrine

> Les raisons derrière tout le reste. Chaque principe tient en une règle en gras, son
> **pourquoi**, et le **mécanisme** qui l'applique (le plugin, une annexe, un fichier du projet).
> Un agent qui trouve un garde-fou « redondant » relit d'abord cette page : la plupart de ce qui
> paraît dupliqué a été argumenté une fois et gardé exprès. Les incidents cités viennent d'un
> projet antérieur, d'où ces pratiques sont tirées ; ils servent de preuve, pas d'anecdote.
>
> Où vivent les mécanismes : les **hooks**, les **agents** et les skills de livraison
> (`/shipyard:ship-parallel`, `/shipyard:wip-refine`, `/shipyard:join`,
> `/shipyard:sync-tooling`) sont dans le plugin ; les scripts que la CI et l'humain lancent sans
> Claude sont **vendorisés** dans le projet (`scripts/`, `.githooks/pre-commit`) ; ce qui est
> propre au projet (`scripts/lib/tooling.conf`, `scripts/check.sh`, le wiki, `wip/`, la CI) est
> écrit au bootstrap. Ce que le wiki du projet en dit : annexe 04.

## 1. Connaissance

**1.1 — Une règle qu'un script peut trancher devient un hook ; une règle qui demande du
jugement devient une ligne de `CLAUDE.md` et une page de wiki.**
Pourquoi : une règle en prose n'est appliquée que si l'agent relit le fichier au bon moment, et
la CI ne l'attrape qu'après le push. À l'inverse, un garde heuristique qui crie au loup est pire
que la prose : il apprend à l'agent à contourner. Mécanisme : les hooks du plugin pour les règles
communes à tous les projets, `scripts/check.sh fast` (annexe 05) pour celles propres au projet ;
`CLAUDE.md` (annexe 03) ne garde qu'une ligne par règle de jugement, le détail vit dans le wiki.

**1.2 — Un fait a un seul propriétaire.**
Pourquoi : deux copies d'un même fait divergent, et l'agent ne sait pas laquelle croire. Une
page possède le fait, les autres y renvoient ; une valeur partagée par des scripts vit dans
`scripts/lib/tooling.conf`. Mécanisme : annexe 00 §1, annexe 06 §1.

**1.3 — Un document que le changement rend faux est corrigé dans le même commit.**
Pourquoi : dans un projet antérieur, le README a dérivé pendant dix mois faute d'une règle qui
dise quand un changement l'implique. Corriger « plus tard » ne se fait pas. Mécanisme : annexe 06
§3 (table de déclenchement du README, documents qui bougent ensemble) ; le relecteur traite un
doc falsifié comme un défaut de sévérité Medium au moins (agent `shipyard:reviewer`).

**1.4 — Les réponses se capitalisent.**
Pourquoi : une synthèse (cause racine, comparaison, mesure) laissée dans le chat ou le corps
d'une PR sera reconstruite à prix plein par la tâche suivante. Elle va dans la page qui possède
le sujet, dans la même PR. Mécanisme : annexe 06 §1.

**1.5 — Les procédures vivent dans les skills, les faits dans le wiki, les règles transversales
dans `CLAUDE.md`.**
Pourquoi : chacun a un coût de contexte différent. `CLAUDE.md` est chargé à chaque session, donc
il est court ; une page wiki n'est lue que si la tâche la touche ; un skill n'est chargé que
quand on exécute la procédure. Mécanisme : annexes 03, 06, 07.

**1.6 — Une règle voyage avec son pourquoi.**
Pourquoi : une règle sans raison est soit retirée comme redondante, soit appliquée à l'aveugle
hors de son domaine. Chaque page wiki finit par `## Decisions & History`, chaque refus d'un hook
nomme sa raison et son remède. Mécanisme : §9 ci-dessous, annexe 06 §1.

## 2. Parallélisme sans collision

**2.1 — Aucun fichier n'est touché par toutes les PR.**
Pourquoi : dans un projet antérieur, un `TODO.md` et un `DONE.md` partagés faisaient entrer en
conflit *chaque* paire de PR — le seul conflit que le travail parallèle ne pouvait pas éviter.
D'où un fichier par entrée de backlog, aucun index, aucun changelog édité à la main par chaque
PR. Mécanisme : annexe 06 §4 (`wip/`) ; le hook Bash du plugin refuse un `TODO.md` racine.

**2.2 — On découpe par fichiers touchés, pas par étiquette ; une dépendance attend la vague
suivante, jamais une PR empilée.**
Pourquoi : deux thèmes qui éditent le même écran ou la même tête de migration entrent en
conflit quoi que dise leur étiquette. Et une PR empilée sur une autre a, dans un projet
antérieur, vu son travail n'arriver nulle part : la PR parente a été squashée, l'enfant a été
mergé dans une branche déjà morte, les deux affichaient « merged » et vert, et il a fallu une
quatrième PR pour réparer. Mécanisme : `/shipyard:ship-parallel` §1 ; le hook Bash refuse
`gh pr create --base` autre que la branche par défaut.

**2.3 — Le checkout principal reste sur la branche par défaut, à jour, et ne commite jamais.**
Pourquoi : c'est de lui que partent les worktrees (`origin/<défaut>` fraîchement fetché), lui que
`ship-parallel` fait avancer en fast-forward après chaque merge, lui qui porte les secrets que
`worktree_setup.sh --deploy` lie au seul worktree de déploiement, et lui que le nettoyage
épargne. Un checkout principal endormi sur une vieille branche fait partir les worktrees d'une
base périmée et laisse un nettoyage juger contre un état faux. Les **règles** en vigueur, elles,
ne dépendent plus de lui : ce sont celles de la version installée du plugin (§7.1). Le travail se
fait dans des worktrees. Mécanisme : `CLAUDE.md` § Git (annexe 03), le message du hook
`SessionStart`, `scripts/worktree_setup.sh` (vendorisé).

**2.4 — Merges en série ; une branche se met à jour en y mergeant la branche par défaut, jamais
par rebase ni force-push.**
Pourquoi : une protection « branche à jour obligatoire » rend les merges séquentiels de toute
façon. Un rebase exige un force-push, qui détruit l'historique de revue et les commits d'un
agent qui travaille encore dans son worktree ; le squash final efface le commit de merge.
Mécanisme : `/shipyard:ship-parallel` §3, le refus du force-push par le hook Bash, la protection
de branche (annexe 08 §7).

**2.5 — Une PR qui touche `.claude/` merge en dernier dans sa vague.**
Pourquoi : `.claude/` porte encore les réglages, les permissions, les règles par chemin et les
skills du projet ; faire avancer le checkout principal après un tel merge change ce que lisent
les agents encore en cours. Mécanisme : `/shipyard:ship-parallel` §1.

**2.6 — Un agent n'atteint que ce dont sa tâche a besoin.**
Pourquoi : un implémenteur ne déploie ni ne signe ; lui donner les secrets de déploiement
n'ajoute que du risque. Aucun secret n'est lié dans un worktree par défaut ; `--deploy` le fait
pour le seul worktree de déploiement. Mécanisme : `scripts/worktree_setup.sh` (vendorisé).

## 3. Risque

**3.1 — Le chemin vers la production se choisit à la planification, selon le risque.**
Pourquoi : un compteur de taille appliqué une fois le code écrit arrive trop tard. Dans un
projet antérieur, une PR de +6 900 lignes mergée et déployée le jour de son ouverture a demandé
six PR de correction le même jour, dont un crash et des failles. Les lanes A/B/C/D sont
décidées en planifiant, d'après ce que la PR va toucher. Mécanisme : `/shipyard:ship-parallel`
§1 (lanes), clés `LANE_C_RE` et `SIZE_THRESHOLD` (annexe 00 §2).

**3.2 — L'auteur ne note jamais son propre travail.**
Pourquoi : l'agent qui écrit le code écrit aussi les tests qui le jugent, et le hook qui refuse
une PR rouge récompense le chemin le plus court vers le vert (cas manquant, assertion
relâchée). Deux revues indépendantes d'un projet antérieur ont trouvé, l'une une migration qui
rendait la base inouvrable avec six checks verts, l'autre une réparation non durable confirmée
sur les données de production. D'où des critères d'acceptation écrits *avant* (lanes B et C) et
une revue par un agent frais. Mécanisme : agent `shipyard:reviewer`, `/shipyard:ship-parallel` §3.

**3.3 — Dans le doute, la lane la plus stricte et la note « complex ».**
Pourquoi : monter d'une lane coûte une revue, en rater une coûte une correction en production ;
sous-noter une tâche coûte une reprise, la sur-noter ne coûte que des tokens. Mécanisme :
`/shipyard:ship-parallel` §1, agents `shipyard:implementer-complex` et
`shipyard:implementer-simple`.

**3.4 — Trois essais sur un même échec, puis on s'arrête et on classe.**
Pourquoi : un agent qui boucle sur un check rouge finit par affaiblir le test plutôt que
corriger le code. Le disjoncteur rend un rapport classé `TEST_ISSUE`, `IMPL_ISSUE`, `DOC_ISSUE`
ou `UNCLEAR`, chacun avec une action d'orchestrateur. Mécanisme : prompt d'implémenteur de
`/shipyard:ship-parallel` §2, agents du plugin.

## 4. Garde-fous mécaniques

**4.1 — Un garde analyse la commande ; il ne la greppe pas. Ce qu'il ne sait pas lire, il le
dit.**
Pourquoi : un grep se déclenche sur un message de commit, un `echo`, un heredoc qui documente la
commande interdite. Un parseur (heredocs retirés, `shlex`, segments, `cd` suivis) évite ces
faux positifs ; quand il ne peut pas déterminer le dépôt, il refuse en expliquant et en donnant
le remède, au lieu de juger le mauvais dépôt — erreur qui a bloqué trois sessions en un jour.
Mécanisme : le parseur du hook Bash du plugin (faits : annexe 04 §2).

**4.2 — Un garde juge le dépôt où la commande s'exécute.**
Pourquoi : le `cwd` du lancement est le checkout principal ; le commit, lui, a lieu dans un
worktree. Juger le mauvais dépôt refuse du travail légitime ou laisse passer du travail
interdit. Le code du garde vient du plugin, mais `tooling.conf` et `scripts/check.sh` sont lus
**dans le dépôt jugé** : une branche qui change un gate est jugée sur ses propres gates.
Mécanisme : hooks du plugin (`cwd` du payload, `cd`, `git -C`, dépôt du fichier édité).

**4.3 — Gates statiques rapides au commit, tests en CI, et une seule définition des gates.**
Pourquoi : faire tourner les tests à chaque commit les paie deux fois ; et des gates définis à
trois endroits (hook, CI, doc) ont divergé dans un projet antérieur. `scripts/check.sh` est la
commande unique du hook, de la CI et de l'humain. Mécanisme : annexe 05, annexe 08.

**4.4 — Un outil absent est un refus qui nomme l'installation, jamais un gate sauté.**
Pourquoi : un gate sauté en silence est une régression invisible ; une erreur « command not
found » avalée ressemble à un succès. Mécanisme : `check.sh` code 3 + ligne `SETUP:` (annexe
05), refus `gates-tool-missing` du hook Bash.

**4.5 — Pendant une modification en plusieurs fichiers, on signale ; au commit, on refuse.**
Pourquoi : un état intermédiaire est légitimement incohérent (une chaîne ajoutée dans 3 langues
sur 10). Un hook post-édition qui bloque dit au modèle que sa modification a été rejetée et
l'invite à défaire du bon travail. Mécanisme : hook `PostToolUse` du plugin (`additionalContext`,
jamais bloquant), refus au commit par le hook Bash.

**4.6 — Les hooks ne font jamais de `fetch` ; leurs lectures réseau ont un délai et se taisent
hors ligne.**
Pourquoi : un `fetch` écrit dans les refs partagées par tous les worktrees, en douce, sous une
autre session ; un hook qui attend le réseau gèle la session. Conséquence assumée : les hooks
sont aussi frais que le dernier `git fetch --prune`, et c'est pour ça que cette commande reste
dans `CLAUDE.md`. Mécanisme : hooks du plugin.

**4.7 — Un garde non testé est indiscernable d'un garde cassé.**
Pourquoi : la première version du hook « pas de fin sans PR » ne demandait que les PR
*ouvertes* et a bloqué indéfiniment après un merge ; ses seuls cas dépendant de GitHub étaient
sautés là où `gh` n'était pas authentifié. Un selftest piloté par une table, avec `gh`
bouchonné, tourne à chaque changement. Mécanisme : les hooks sont testés dans la CI du plugin ;
les copies vendorisées apportent leurs selftests, que le job `tooling` du projet lance par
`scripts/selftest.sh` (annexe 08).

**4.8 — Un hook rend toujours la main, et ses propres pannes se voient.**
Pourquoi : un Stop qui bloque à chaque tentative empêche la session de finir ; un hook qui
plante en bloquant tout est pire que le risque qu'il couvre. Le hook Stop ne bloque qu'une fois
par tour ; une erreur interne laisse passer ; mais une dépendance manquante (`python3`) est
annoncée au démarrage, pour qu'« ouvert » ne veuille jamais dire « muet ». Mécanisme : hooks du
plugin (faits : annexe 04 §2).

## 5. Livraison

**5.1 — Fini veut dire : une PR verte contre la branche par défaut.**
Pourquoi : un commit qui n'est dans aucune PR n'a été ni relu ni testé par la CI, et il est
invisible pour tout le monde sauf la machine qui le porte. Une PR rouge n'est pas livrée non
plus. Mécanisme : hook du plugin sur `Stop` et `SubagentStop`.

**5.2 — Aucun échec silencieux.**
Pourquoi : dans un projet antérieur, une session sans accès à la cible a mergé cinq PR, n'a pas
pu déployer, et la boucle s'est terminée comme un succès ; la production a manqué un endpoint
plusieurs jours. Même famille : un workflow planifié que GitHub désactive après 60 jours
d'inactivité, un outil manquant, un hook muet, une copie vendorisée en retard sur le plugin.
Chaque cas a son signal : sonde de déploiement à la planification et entrée « merged, not
deployed », refus nommant l'installation, message de `SessionStart` sur l'outillage vendorisé.
Mécanisme : `/shipyard:ship-parallel` §1 et §4, skill `deploy` du projet (annexe 07), annexe 05,
hook `SessionStart`.

**5.3 — On déploie après chaque merge, depuis un arbre propre au commit mergé, et on vérifie le
contenu réel.**
Pourquoi : déployer par lot rend une régression impossible à attribuer. Et un endpoint de santé
peut répondre « ok » pendant que tous les clients reçoivent une erreur — c'est arrivé deux jours
durant : on lit ce que la santé déclare et on exerce le chemin que la PR a changé. Mécanisme :
`/shipyard:ship-parallel` §4, skill `deploy` du projet (annexe 07 §3).

**5.4 — Un problème trouvé après le merge est une nouvelle PR ; une production cassée est
d'abord remise en arrière.**
Pourquoi : commiter sur une branche mergée n'arrive nulle part (le hook le refuse une fois la
branche supprimée), et réparer en production sous pression coûte plus qu'un rollback. Mécanisme :
`/shipyard:ship-parallel` §5, skill `deploy` §5.

**5.5 — Une seule approbation en amont, puis l'autonomie — sauf lane C, zone d'un autre owner,
et action irréversible non couverte.**
Pourquoi : chaque interruption coûte à l'utilisateur un changement de contexte, et l'attente
sur l'utilisateur pèse autant que le travail des agents. Le plan est approuvé une fois ; il
couvre merges et déploiements, dans la limite de l'autonomie choisie (`AUTONOMY`). Restent hors
de cette approbation : le merge d'une PR lane C, le merge d'une PR qui touche la zone d'un autre
owner (§8.1), et toute action irréversible ou sortante que le plan ne nommait pas. Mécanisme :
annexe 02 (questionnaire), `/shipyard:ship-parallel`.

**5.6 — On ne demande à l'utilisateur que ce qui est à lui de décider.**
Pourquoi : une question dont la réponse se déduit du code, du wiki ou d'un défaut raisonnable
est un coût sans valeur. Les décisions de l'utilisateur : périmètre, priorité, acceptation d'un
risque, action sortante, et les échappatoires (`<ns>.allowStackedPr`) qu'un agent ne pose jamais
lui-même. Mécanisme : annexe 02, refus des `git config` réservés par le hook Bash.

**5.7 — Un problème trouvé hors du périmètre devient une entrée `wip/`, jamais une correction en
passant, jamais un oubli.**
Pourquoi : une correction glissée dans une PR étrangère élargit sa revue et son rollback ; un
constat oublié revient plus cher. Par défaut il va dans `wip/todo_nr/` : sinon le périmètre de
la livraison en cours grandirait à chaque session. Mécanisme : annexe 06 §4.

**5.8 — L'environnement local est laissé propre, et rien n'est supprimé sans preuve.**
Pourquoi : le premier nettoyage manuel d'un projet antérieur a trouvé vingt branches déjà
mergées et deux worktrees morts ; un nettoyage lancé depuis une autre session a supprimé un
worktree en pleine installation, que rien ne distinguait d'un worktree abandonné. D'où un
nettoyage en dry-run par défaut, qui prouve via GitHub qu'une branche est mergée et respecte
verrous, marqueur de setup et modifications récentes. Mécanisme : `scripts/cleanup_local.py`
(vendorisé).

## 6. Élagage et mesure

**6.1 — On élague autant qu'on ajoute.**
Pourquoi : dans un projet antérieur, `CLAUDE.md` avait atteint 204 lignes, dont 40 % de
process : chaque incident était devenu une règle, aucune n'avait été retirée. Budgets
(`CLAUDE_MD_BUDGET`, `WIKI_PAGE_BUDGET`) et passe d'élagage avant chaque release, ou toutes les
`PRUNE_EVERY_MERGES` PR en livraison continue, qui propose de retirer les règles qui n'ont servi
à rien. Mécanisme : annexe 06 §3.

**6.2 — L'outillage qui gêne est une entrée `wip/`, et la meilleure correction est souvent une
suppression.**
Pourquoi : un skill, un hook ou une règle qui a forcé un détour est un défaut comme un autre ;
le contourner sans le dire le laisse piéger la session suivante. Préférer remplacer une règle à
en ajouter une à côté. Un défaut du plugin lui-même (un hook, un skill, une copie vendorisée) est
aussi une entrée `wip/` (`Area: tooling`), qui nomme la version du plugin ; on ne le corrige
jamais dans le projet (§7.3). Mécanisme : annexe 06 §4 (entrées outillage).

**6.3 — Mesurer plutôt que se souvenir (niveau Complet).**
Pourquoi : le process d'un projet antérieur a d'abord été réglé à l'anecdote ; la mesure a
montré des choses contre-intuitives (les lectures de cache pesaient 69 % du coût, l'attente de
CI 17 % du temps d'outil). Taux de reprise, taux d'échec des changements, premier run vert, coût
par skill. Mécanisme : niveau d'outillage Complet (annexe 02) ; tant qu'une mesure n'est pas
installée, une entrée `wip/todo_nr/` l'attend (annexe 06 §7).

## 7. Outillage partagé

**7.1 — Les règles en vigueur sont celles de la version installée du plugin.**
Pourquoi : les hooks, les agents et les skills de livraison sont chargés depuis le plugin, pas
depuis le dépôt. Un correctif de garde-fou atteint donc tous les projets à la mise à jour du
plugin, au lieu d'exister dans un projet et pas dans le suivant ; et aucune PR de projet ne peut
affaiblir un garde-fou en passant. Conséquences assumées : changer un hook est une version du
plugin, pas une PR du projet ; deux personnes dont le plugin n'est pas à la même version sont
jugées par des règles différentes jusqu'à ce que les deux le mettent à jour. Le checkout
principal reste sur la branche par défaut pour les autres raisons de §2.3. Mécanisme :
`.claude/settings.json` (`enabledPlugins`, annexe 03 §2), `/plugin update`.

**7.2 — Le code générique est écrit et testé une fois ; une valeur propre au projet est une clé
de `tooling.conf`, jamais une ligne de code.**
Pourquoi : quand chaque bootstrap régénérait les hooks et les scripts, chaque projet en avait
une variante, testée par ses seuls selftests, et un correctif trouvé dans l'un n'atteignait pas
les autres. Un script générique qui contient une table propre au projet (les chemins de chaque
composant, par exemple) redevient une variante : la table va dans `tooling.conf`
(`COMPONENT_<ID>_RE`), le script la lit. Ce qui est réellement propre au projet et ne se réduit
pas à une valeur — les commandes de la stack — vit dans `scripts/check.sh`, écrit pour lui.
Mécanisme : annexe 00 §2, annexe 05.

**7.3 — Ce que la CI et l'humain lancent sans Claude est vendorisé, et chaque copie est
identique à son gabarit.**
Pourquoi : un runner GitHub et un terminal n'ont pas le plugin ; les scripts de process et le
hook git doivent donc vivre dans le dépôt. Mais une copie modifiée localement redevient une
variante (§7.2) qu'aucune mise à jour ne corrigera plus. D'où une empreinte par fichier
(`scripts/lib/VENDORED.json`), vérifiée par la CI et par le hook `SessionStart` : une copie
modifiée est une dérive signalée, pas une personnalisation silencieuse. Un besoin que la copie
ne couvre pas est une clé de `tooling.conf` ou une évolution du gabarit dans le plugin, jamais
une retouche de la copie. Mécanisme : `bin/vendor.py` du plugin, `/shipyard:sync-tooling`, le
step d'empreintes du job `tooling` (annexe 08 §2).

**7.4 — Un outillage qui ne connaît pas le dépôt se tait, et dit pourquoi une fois.**
Pourquoi : le plugin peut être activé dans un dépôt qui n'a pas été bootstrappé (un clone
ancien, un dépôt voisin) ; y appliquer des règles sans `tooling.conf` reviendrait à juger un
projet sur les défauts d'un autre. Sans `scripts/lib/tooling.conf` dans le dépôt jugé, tous les
hooks sont inertes, et `SessionStart` le dit en une ligne. Mécanisme : hooks du plugin ;
activation au niveau du projet seulement (annexe 03 §2.2), pour que les garde-fous n'atteignent
pas les autres dépôts de l'utilisateur.

## 8. Équipe

**8.1 — Le propriétaire d'un chemin décide des changements qui le touchent.**
Pourquoi : plusieurs personnes lancent chacune des agents en parallèle ; sans propriétaire, une
PR peut réécrire une zone que son auteur ne connaît que par le code, sans les décisions et
l'historique qui l'expliquent. Celui qui possède la zone relit et approuve ; en attendant, ses
autres PR avancent. Son approbation tient lieu du feu vert de la lane C pour ses chemins.
Mécanisme : `.github/CODEOWNERS` (demande de revue automatique), `/shipyard:ship-parallel` (ne
merge une PR qui touche une zone étrangère qu'après l'approbation d'un owner de cette zone).

**8.2 — La propriété est déclarée par chacun et versionnée dans git.**
Pourquoi : qui possède quoi doit être lisible par un script (`scripts/owners.py`) et par un
agent, et une propriété devinée (d'après `git blame`, ou attribuée par un outil) se trompe en
silence. Chacun déclare ses zones lui-même, par une PR que les owners actuels approuvent comme
toute autre ; l'historique dit qui possédait quoi et depuis quand. Mécanisme : `/shipyard:join`,
`.github/CODEOWNERS`, `.llmwiki/Team.md` (annexe 06 §2), le message `SessionStart` qui demande à
un nouveau venu de rejoindre avant de travailler.

**8.3 — Le process avant la contrainte de branche.**
Pourquoi : GitHub ne laisse pas l'auteur d'une PR l'approuver ; une protection
`require_code_owner_reviews` empêcherait donc un owner seul de sa zone de merger ses propres PR,
et bloquerait tout le travail sur cette zone dès qu'il est absent. L'approbation des owners est
d'abord une règle de `ship-parallel` ; la règle de branche ne s'ajoute que quand chaque zone a
plusieurs owners. Mécanisme : annexe 08 §7.3, questionnaire (annexe 02).

## 9. Comment semer ces raisons dans le projet

Le projet généré ne contient pas cette annexe : ses agents n'auront que ses propres fichiers.
WP-D recopie donc les raisons utiles dans le `## Decisions & History` de chaque page wiki, sous
la forme (en anglais, ou dans la langue de la doc) :

```markdown
- **<Decision title> (<bootstrap date>, inherited at bootstrap).** <the why, two or three
  sentences, generic — "an earlier project saw…", never an invented incident in this one>.
  Mechanism: `<file>` or "the shipyard plugin's <hook / agent / skill>".
```

| Page | Principes à semer |
|---|---|
| `Hooks.md` | 1.1, 4.1 à 4.8, 5.1, 5.6 (échappatoires réservées), 7.1, 7.4 |
| `ParallelDelivery.md` | 2.1 à 2.5, 3.1 à 3.4, 5.2 à 5.5, 5.8 |
| `Documentation.md` | 1.2 à 1.6, 6.1, 6.2 |
| `Security.md` | 2.6, et la détection des secrets par chemin **et** contenu (annexe 04 §5) |
| `Testing.md` | 4.3, 4.4, 4.7, 7.2, 7.3 |
| `Team.md` (équipe) | 8.1 à 8.3 |
| `Deployment.md` (s'il existe) | 5.2, 5.3, 5.4 |
| `Project.md` (orchestrateur) | 5.5, 5.6 — ce que l'utilisateur a autorisé, et ce qui reste à lui |

`CLAUDE.md` ne reçoit que la règle en une ligne, avec le renvoi à la page ; jamais la raison
(budget, principe 1.5). Une raison semée au bootstrap est une décision comme une autre : elle
peut être révisée plus tard, mais par une entrée `wip/` qui la cite, pas par un agent qui la
juge redondante en passant.

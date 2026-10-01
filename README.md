# shipyard

[![CI](https://github.com/vemore/claude-shipyard/actions/workflows/ci.yml/badge.svg)](https://github.com/vemore/claude-shipyard/actions/workflows/ci.yml)
[![Licence : MIT](https://img.shields.io/badge/licence-MIT-blue.svg)](LICENSE)

Un plugin [Claude Code](https://code.claude.com) pour **démarrer un projet avec tout
l'outillage de développement agentique, puis le livrer en parallèle** : un agent et un worktree par
thème, une pull request verte par thème, sans collision.

*English summary: [In short](#in-short).*

## Ce que ça fait

Dans un dossier vide, `/shipyard:bootstrap` pose **un questionnaire**, puis, sans autre validation,
installe :

- **Un dépôt GitHub** prêt à livrer : CI scopée par composant, protection de la branche par défaut
  (quand le plan GitHub le permet), réglages du dépôt.
- **Des hooks garde-fous** qui refusent mécaniquement ce qu'un script peut trancher : force-push, push
  sur la branche par défaut, PR empilée, merge hors squash ou avec `--admin`, secret commité (par
  chemin et par contenu), commit sur la mauvaise branche, gates rouges, fin de tour sur des commits
  sans PR ou sur une PR rouge. [Détail et limites](docs/hooks.md).
- **Un wiki pour les LLM** (`.llmwiki/`) : un fait, une page, une date de mise à jour, un `## Decisions
  & History` qui garde le *pourquoi* ; et un `CLAUDE.md` court qui renvoie au wiki.
- **Un backlog à un fichier par entrée** (`wip/todo/`, `wip/todo_nr/`, `wip/done/`) : jamais de liste
  partagée, donc jamais de conflit entre deux PR parallèles.
- **La livraison en parallèle** : `/shipyard:ship-parallel` regroupe les entrées par thème, lance un
  agent implémenteur par PR dans son worktree, fait relire les changements risqués, merge en squash
  les PR vertes une par une, déploie ce que chaque merge a changé et nettoie.
- **Pour une équipe** : des **code owners** (`.github/CODEOWNERS`, `.llmwiki/Team.md`), un contrôle au
  démarrage de session que la personne en fait partie, et l'approbation d'un owner avant de merger une
  PR qui touche la zone d'un autre.

Le raisonnement tient en quelques règles : une règle qu'un script peut décider devient un hook, une
règle de jugement reste en prose ; un fait a un seul propriétaire ; aucun fichier n'est touché par
toutes les PR ; le checkout principal reste sur la branche par défaut et le travail se fait dans des
worktrees ; se tromper doit coûter un run lent, jamais un merge non testé.

## Installation

Dans Claude Code :

```text
/plugin marketplace add vemore/claude-shipyard
/plugin install shipyard@claude-shipyard
```

Pour que tous les clones d'un projet l'aient, déclarer la marketplace et activer le plugin dans le
`.claude/settings.json` **du projet** (versionné) :

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

Claude Code propose alors l'installation à l'ouverture du dossier. Le plugin peut être activé dans
n'importe quel dépôt : **sans `scripts/lib/tooling.conf`, ses hooks sont inertes** et seul un message
d'une ligne s'affiche au démarrage de la session.

## Utilisation

1. **Démarrer un projet.** Dans un dossier **vide**, lancer Claude Code puis :

   ```text
   /shipyard:bootstrap Une API de réservation de salles pour des clubs de sport, en Python
   ```

   La skill demande d'abord une description libre si l'argument ne la donne pas, puis au plus trois
   rondes de questions (stack, dépôt, déploiement, autonomie, zones sensibles, équipe ou solo…) et un
   récapitulatif qui vaut **feu vert unique**. Ensuite elle ne s'arrête plus (sauf accès ou décision que
   seul l'utilisateur peut donner) : dépôt, squelette, tests, wiki, backlog, CI, PR de bootstrap mergée.
   Elle ne se déclenche que sur demande explicite : elle crée un dépôt distant.
2. **Redémarrer Claude Code** dans le dossier : les hooks se chargent au démarrage de la session. Le
   message de début de session doit apparaître, et `git push --force` doit être refusé.
3. **Livrer.** `/shipyard:ship-parallel` (ou « attaque `wip/todo` en parallèle ») : un plan par thème,
   un agent par PR, merges en série, déploiement et rapport.
4. **En équipe.** Chaque membre lance `/shipyard:join` : la skill demande de quelles zones il sera
   responsable, met à jour `CODEOWNERS` et `Team.md` dans un worktree neuf et ouvre la PR, qui attend
   l'approbation des mainteneurs.
5. **Trier le backlog.** `/shipyard:wip-refine` quand `wip/todo_nr/` grossit : chaque entrée est
   confrontée au code (déjà corrigée, obsolète, à fusionner, à préciser, prête) et la skill propose ce
   qui passe en `wip/todo/`. L'utilisateur décide, puis une PR applique le tri.
6. **Mettre à jour.** `/plugin update`, redémarrer Claude Code, puis `/shipyard:sync-tooling` : le hook
   de début de session signale quand les copies vendorisées du projet sont en retard sur le plugin.

## Ce qui vit dans le plugin, ce qui vit dans le projet

| Dans le plugin (mis à jour par `/plugin update`) | Dans le projet (versionné dans son git) |
|---|---|
| Les hooks Claude Code et leur parseur | `scripts/lib/tooling.conf` : **toutes** les valeurs propres au projet |
| Les agents `implementer-simple`, `implementer-complex`, `reviewer` | `.claude/settings.json` : activation du plugin, marketplace, permissions |
| Les skills `bootstrap`, `join`, `ship-parallel`, `wip-refine`, `sync-tooling` | Les **copies vendorisées** des scripts que la CI et l'humain lancent sans Claude, leurs selftests, et `scripts/lib/VENDORED.json` |
| Les gabarits de ces copies (`templates/`) et `bin/vendor.py` | `scripts/check.sh` (propre à la stack), le code, la CI, le wiki, `wip/` |
| | En équipe : `.github/CODEOWNERS` et `.llmwiki/Team.md` |

Pourquoi : le code générique est écrit et testé **une fois**, et un correctif atteint tous les projets
à la mise à jour du plugin, au lieu d'être régénéré (et de varier) à chaque bootstrap. Ce que la CI
exécute reste dans le dépôt, parce qu'un runner GitHub n'a pas le plugin. Les copies sont
**identiques** au gabarit de leur version (empreintes dans `VENDORED.json`) : une copie modifiée à la
main est une dérive signalée, pas une personnalisation silencieuse. Détail :
[docs/scripts.md](docs/scripts.md).

## Modèles

Les modèles des agents sont fixés par le plugin : **Sonnet** pour les trois agents (effort `high` pour
`implementer-complex` et `reviewer`, `low` pour `implementer-simple`), **Haiku** pour le volume.

| Agent | Modèle | Effort | Rôle |
|---|---|---|---|
| `shipyard:implementer-complex` | Sonnet | high | une PR au choix de conception ouvert, plusieurs sous-systèmes, lane B ou C |
| `shipyard:implementer-simple` | Sonnet | low | une PR dont le correctif est explicite et local |
| `shipyard:reviewer` | Sonnet | high | relecture indépendante d'une PR risquée |
| agent générique | Haiku | | le **volume** : traductions, balayages mécaniques, lancés par l'orchestrateur |

Chaque implémenteur tourne dans son propre worktree. Un projet qui veut d'autres modèles définit ses
propres agents dans `.claude/agents/` et le dit dans `.llmwiki/Project.md` : `ship-parallel` utilise
alors leurs noms.

## Prérequis et limites

- **Linux, macOS ou WSL.** Pas de Windows natif.
- **Python 3.9 ou plus** (hooks et scripts, bibliothèque standard seulement), **git**, et un compte
  **GitHub avec `gh`** authentifié (portées `repo` et `workflow`). Rien n'est supposé de plus sur la
  machine : la toolchain de la stack choisie est vérifiée avant le feu vert.
- **Sessions de code distant (cloud).** Elles ne chargent pas les marketplaces déclarées par un projet :
  les hooks du plugin n'y tournent donc pas, sauf si le plugin est synchronisé avec le compte. Les copies
  vendorisées (hook git `pre-commit`, scripts, CI) fonctionnent, elles, puisqu'elles sont dans le dépôt.
- **Protection de branche.** GitHub ne la propose, sur un dépôt privé, qu'avec un plan payant : il faut
  un dépôt public ou un plan payant. Sinon, seuls les hooks protègent la branche par défaut, et le
  bootstrap le consigne dans le backlog au lieu de l'ignorer.
- **Les hooks ne sont pas une frontière de sécurité.** Ils réduisent une classe d'erreurs fréquentes :
  un merge par l'interface web, un commit fait dans un script lancé ou `--no-verify` passent à travers.
  La CI et la protection de branche restent derrière. La liste complète est dans
  [docs/hooks.md](docs/hooks.md#11-ce-que-les-hooks-ne-couvrent-pas).
- Les hooks sont lus **au démarrage** de la session : après une installation ou une mise à jour du
  plugin, il faut redémarrer Claude Code.

## Documentation

- [docs/contrat-plugin.md](docs/contrat-plugin.md) : le contrat du plugin (noms, fichiers, interfaces,
  répartition plugin / projet). Il l'emporte sur le reste.
- [docs/hooks.md](docs/hooks.md) : ce que font les hooks, pourquoi, et ce qu'ils ne couvrent pas.
- [docs/scripts.md](docs/scripts.md) : les scripts vendorisés, `bin/vendor.py` et le circuit des mises à
  jour.
- [CHANGELOG.md](CHANGELOG.md) : une section par version (copie identique dans
  `plugins/shipyard/CHANGELOG.md`).

## Contribuer

```bash
git clone https://github.com/vemore/claude-shipyard
cd claude-shipyard

# Les tests du plugin (hooks, vendoring) et les selftests des scripts vendorisés
python -m unittest discover -s tests -v
python -m unittest discover -s plugins/shipyard/templates/scripts/selftest -v

# Valider les manifestes avec le CLI, et essayer le plugin local
claude plugin validate plugins/shipyard
claude --plugin-dir plugins/shipyard
```

Les tests n'ont besoin ni de réseau, ni d'un `gh` authentifié : ils utilisent un `gh` factice et des
dépôts git jetables. La CI les lance sur Linux (Python 3.9 et 3.12) et sur macOS.

Règles de contribution :

- Une pull request par thème, contre `main`, avec un corps qui dit **ce qui change et pourquoi**. La
  CI doit être verte.
- Une règle de hook ou un comportement de script change avec **son test** (le refus *et* le faux
  positif voisin) et avec sa documentation (`docs/hooks.md`, `docs/scripts.md`).
- Python 3.9, bibliothèque standard seulement, pour tout ce qui tourne chez l'utilisateur ; les messages
  que voit le modèle ou l'utilisateur sont en anglais.
- Une nouvelle version change `version` dans `plugins/shipyard/.claude-plugin/plugin.json` (c'est ce qui
  distribue la mise à jour), ajoute une section à `CHANGELOG.md` et reçoit le tag `v<version>`. Le
  changelog existe en **deux exemplaires identiques**, `CHANGELOG.md` à la racine (la source) et
  `plugins/shipyard/CHANGELOG.md` (un plugin installé n'emporte que son dossier, et
  `/shipyard:sync-tooling` y lit les changements entre deux versions) : les deux se mettent à jour
  ensemble, et la CI échoue s'ils diffèrent. Un
  changement qui modifie un gabarit vendorisé est au moins une version **mineure**, et son entrée de
  changelog dit « run `/shipyard:sync-tooling` ».
- Ce dépôt est public : jamais de secret, d'adresse électronique, d'hôte ou d'URL privée dans un fichier.

## Licence

[MIT](LICENSE).

---

## In short

**shipyard** is a [Claude Code](https://code.claude.com) plugin that **bootstraps a project with agent
tooling, then ships it in parallel**.

- **Bootstrap.** `/shipyard:bootstrap <description>` in an empty folder asks one questionnaire, then,
  on a single go-ahead, creates the GitHub repository, a short `CLAUDE.md`, an LLM wiki
  (`.llmwiki/`), a one-file-per-entry backlog (`wip/`), component-scoped CI and branch protection.
- **Parallel delivery.** `/shipyard:ship-parallel` groups backlog entries by theme, runs one agent per
  pull request in its own git worktree, has risky changes independently reviewed, squash-merges each
  green pull request in turn, deploys what changed and cleans up.
- **Guard hooks.** Rules a script can decide are mechanical refusals: force-push, push to the default
  branch, stacked pull requests, non-squash or `--admin` merges, committed secrets, red commit gates,
  finishing a turn on commits without a green pull request. They are inert in a repository without
  `scripts/lib/tooling.conf`.
- **Teams.** Code owners (`.github/CODEOWNERS`), `/shipyard:join` for each member, and owner approval
  before merging a pull request that touches someone else's area.

**Install**

```text
/plugin marketplace add vemore/claude-shipyard
/plugin install shipyard@claude-shipyard
```

Or per project, in `.claude/settings.json`: `extraKnownMarketplaces` (the `claude-shipyard` GitHub
source `vemore/claude-shipyard`) plus `enabledPlugins` (`"shipyard@claude-shipyard": true`), as shown
in the French section above.

**Use** `/shipyard:bootstrap` in an empty folder, restart Claude Code (hooks load at session start),
then `/shipyard:ship-parallel`. Each team member runs `/shipyard:join`; `/shipyard:wip-refine` sorts
the backlog. To update: `/plugin update`, restart, then `/shipyard:sync-tooling` (the project holds
vendored copies of the scripts that CI and humans run without Claude).

**Models.** Sonnet with high effort for complex implementation and review, Sonnet with low effort for
simple changes, Haiku for bulk work. A project can override them with its own agents in
`.claude/agents/`.

**Requirements and limits.** Linux, macOS or WSL; Python 3.9+; git; GitHub with an authenticated `gh`.
Claude Code cloud sessions do not load a project's marketplaces, so the hooks do not run there unless
the plugin is synced to the account. Branch protection needs a public repository or a paid GitHub
plan. The hooks reduce a class of mistakes; they are not a security boundary.

**Contributing.** `python -m unittest discover -s tests -v` and
`python -m unittest discover -s plugins/shipyard/templates/scripts/selftest -v`, then
`claude plugin validate plugins/shipyard`. Read [docs/contrat-plugin.md](docs/contrat-plugin.md) first
(in French): it wins over everything else. Licensed under [MIT](LICENSE).

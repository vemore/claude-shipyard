# Annexe 8 — CI et réglages GitHub

> Lue par **WP-F** (tout `.github/**` sauf `CODEOWNERS`) et par l'orchestrateur pour le §7
> (réglages du dépôt, `CODEOWNERS` en équipe, protection de la branche par défaut), qu'il
> applique lui-même. Les identifiants et noms de jobs viennent de l'annexe 00 §6 ; les commandes
> qu'un job de composant exécute viennent de `scripts/check.sh` (annexe 05) — un job n'en
> contient pas d'autre. **La CI n'a pas le plugin** : elle n'exécute que ce qui est dans le dépôt
> (les copies vendorisées, `check.sh`), jamais un fichier du plugin. Ce que le wiki dit de la CI
> et de la protection : annexe 04 §3 et §4.

## 1. Ce que contient `.github/`

| Fichier | Quand | Écrit par | Rôle |
|---|---|---|---|
| `.github/workflows/ci.yml` | toujours | WP-F | le **seul** workflow qui porte des checks requis |
| `.github/dependabot.yml` | toujours | WP-F | mises à jour hebdomadaires groupées |
| `.github/osv-scanner.toml` | seulement si `Project.md` § Components nomme osv-scanner comme audit d'un composant | WP-F | ignores de vulnérabilités, chacun avec expiration et entrée `wip/` |
| `.github/workflows/deps.yml` | niveau Complet (pas en shipyard 0.1 : une entrée `wip/todo_nr/` à la place) | WP-F | rafraîchissement mensuel des verrous et artefacts générés |
| `.github/workflows/deploy-<cible>.yml` | optionnel | WP-F | publication d'un site statique (§8) |
| `.github/CODEOWNERS` | `TEAM_MODE=team` | orchestrateur | qui possède quel chemin (§7.3) |

Toutes les actions tierces sont **épinglées par SHA de commit complet**, version en
commentaire (`uses: actions/checkout@<sha40> # v4.2.2`) ; Dependabot (écosystème
`github-actions`) les met à jour. Pourquoi : un tag se déplace, un SHA non ; une action
compromise ne doit pas entrer par un tag réécrit. **Chaque SHA se résout, jamais de mémoire** :
`gh api repos/<owner>/<action>/commits/<tag> --jq .sha` (lecture seule), puis vérifier dans
l'`action.yml` de ce SHA que les entrées utilisées (`with:`) existent — un SHA inventé fait
échouer la CI du bootstrap sur « unable to resolve action ».

## 2. `.github/workflows/ci.yml` — gabarit

Remplacer `<…>` ; un bloc de job par identifiant de `COMPONENTS`, dans l'ordre.

```yaml
# .github/workflows/ci.yml — the only workflow carrying required checks.
# Required checks = the `name:` of `tooling` and of every component job. `scope` is NOT required.
# Never add a workflow-level path filter (the push/pull_request path-filter keys) here: a filtered
# workflow reports no status at all, and a required check that never reports leaves the pull
# request waiting forever. (The ci_scope selftest refuses the literal key anywhere in this file.)
# Scoping is done per job, by `scope` + a job-level `if:` (a job skipped by `if:` reports success).
# A new verification is a STEP in an existing required job (or in scripts/check.sh), never a new
# job: a new job is not required until the protection is edited, and a renamed one blocks every
# open pull request.
# CI has no Claude Code plugin: everything here runs from the repository (vendored copies, check.sh).
name: CI

on:
  push:
    branches: [<default-branch>]
  pull_request:
  schedule:
    - cron: '<m> <h> * * <weekday>'   # weekly: every job and every audit, whatever the scope
  workflow_dispatch:

concurrency:
  group: ${{ github.workflow }}-${{ github.ref }}
  # Cancel a superseded pull-request run; never a run of the default branch, which must keep a
  # complete green/red record.
  cancel-in-progress: ${{ github.event_name == 'pull_request' }}

permissions:
  contents: read            # a job-level `permissions:` block REPLACES this one, not extends it

jobs:
  scope:
    name: Scope
    runs-on: ubuntu-latest
    timeout-minutes: 5
    permissions:
      contents: read
      pull-requests: read
    outputs:
      <component-1>: ${{ steps.flags.outputs.<component-1> }}
      <component-2>: ${{ steps.flags.outputs.<component-2> }}
    steps:
      - uses: actions/checkout@<sha40> # <version>
      - id: flags
        env:
          GH_TOKEN: ${{ github.token }}
          EVENT: ${{ github.event_name }}
          REPO: ${{ github.repository }}
          PR: ${{ github.event.pull_request.number }}
        # No `|| true` anywhere: if this step fails, every component job runs (see the `if:`).
        run: |
          set -euo pipefail
          . scripts/lib/tooling.conf
          all_true() { for c in $COMPONENTS; do echo "$c=true"; done | tee -a "$GITHUB_OUTPUT"; }
          if [ "$EVENT" != pull_request ]; then all_true; exit 0; fi
          # The files endpoint stops at 3000 files without saying so: past that, run everything.
          if [ "$(gh api "repos/$REPO/pulls/$PR" --jq .changed_files)" -ge 3000 ]; then all_true; exit 0; fi
          gh api "repos/$REPO/pulls/$PR/files?per_page=100" --paginate \
             --jq '.[] | .filename, (.previous_filename // empty)' \
            | python3 scripts/ci_scope.py | tee -a "$GITHUB_OUTPUT"

  tooling:
    name: Tooling — selftests, wiki, wip
    runs-on: ubuntu-24.04                      # pinned: python 3.9 builds may leave newer images
    timeout-minutes: 10
    steps:
      - uses: actions/checkout@<sha40> # <version>
        with:
          fetch-depth: 0                       # wip.py and some selftests read history
      - uses: actions/setup-python@<sha40> # <version>
        with:
          python-version: '3.9'                # the oldest supported: catches 3.10+ syntax
      - name: Vendored tooling matches scripts/lib/VENDORED.json
        # The plugin's `vendor.py --check` cannot run here (no plugin on a runner); the recorded
        # hashes can. A copy edited in this repository is drift: change the template in the
        # plugin, then run /shipyard:sync-tooling.
        shell: python3 {0}
        run: |
          import hashlib, json, sys
          with open("scripts/lib/VENDORED.json", encoding="utf-8") as fh:
              record = json.load(fh)
          files = record.get("files") or {}
          problems = []
          for path, expected in sorted(files.items()):
              try:
                  with open(path, "rb") as fh:
                      actual = hashlib.sha256(fh.read()).hexdigest()
              except OSError:
                  problems.append("missing  " + path)
                  continue
              if actual != expected.split(":")[-1].strip().lower():
                  problems.append("modified " + path)
          if not files:
              problems.append("scripts/lib/VENDORED.json lists no file")
          print("\n".join(problems) or "ok: %d vendored files match shipyard %s"
                % (len(files), record.get("shipyard", "?")))
          sys.exit(1 if problems else 0)
      - name: Selftests (vendored scripts, check.sh, skill-local scripts; fails on zero tests)
        run: scripts/selftest.sh
      - name: Wiki lint                       # exit 1 on findings only; `note:` lines do not fail
        run: python3 scripts/wiki_lint.py
      - name: wip entries
        run: python3 scripts/wip.py check

  <component-1>:
    name: <Component 1> — <lint, types, tests, build, audit>
    needs: scope
    if: ${{ !cancelled() && needs.scope.outputs.<component-1> != 'false' }}
    runs-on: ubuntu-latest
    timeout-minutes: <20>
    # services: { postgres: … }               # if the component's tests need one
    steps:
      - uses: actions/checkout@<sha40> # <version>
      - uses: <toolchain setup action>@<sha40> # <version>   e.g. astral-sh/setup-uv, actions/setup-node
        with:
          <cache keyed on the component's lockfile>
      # Only if Project.md names osv-scanner as this component's audit: install it here, pinned
      # by version and verified by SHA-256 (§5). The ecosystem's own audit needs no step.
      - name: Gates, tests, build, audit       # check.sh ci also sets every <NAME>_REQUIRED=true
        run: scripts/check.sh ci <component-1>
```

**Le step d'empreintes**, et pourquoi en premier. Les copies vendorisées sont identiques à leur
gabarit (annexe 01, 7.3) ; une copie modifiée dans le dépôt ne recevrait plus aucun correctif.
Le plugin vérifie cela avec `bin/vendor.py --check`, mais un runner n'a pas le plugin : le step
relit donc `scripts/lib/VENDORED.json` (`{"shipyard": "<version>", "files": {"<chemin>":
"<sha256>"}}`) et compare chaque fichier à son empreinte, en Python 3.9 stdlib, sans rien
installer. Il passe avant les selftests : un selftest vendorisé qui a été modifié ne prouve plus
rien. Ce qu'il ne fait pas : dire si une version plus récente du plugin existe (le hook
`SessionStart` le dit), ni vérifier les fichiers que `VENDORED.json` ne liste pas (`check.sh`,
`tooling.conf`, le code). Un échec se répare par `/shipyard:sync-tooling` (qui refuse d'écraser
une copie modifiée sans le dire) ou en annulant la modification — jamais en éditant
`VENDORED.json` à la main.

## 3. Les trois détails porteurs de la condition `if:`

`if: ${{ !cancelled() && needs.scope.outputs.<c> != 'false' }}` — chacun des trois morceaux
protège contre un merge non testé :

1. **`!cancelled()`.** `needs:` ajoute un `success()` implicite. Sans `!cancelled()`, un `scope`
   en échec ferait *sauter* tous les jobs de composant — et un job sauté rapporte **Success** au
   check requis : la PR deviendrait mergeable sans qu'aucun test n'ait tourné. `always()`
   éviterait le saut mais tournerait aussi quand le run est annulé, ce qui ruinerait
   `cancel-in-progress`.
2. **`!= 'false'` et non `== 'true'`.** Une sortie absente (scope en échec, sortie mal nommée)
   vaut `''` : le job tourne, sauf si `scope` a dit explicitement non.
3. **L'enveloppe `${{ … }}`.** Un `if: !cancelled() && …` nu commence par `!`, indicateur de tag
   YAML : le fichier ne se parse plus, le workflow ne rapporte rien, et chaque check requis
   attend pour toujours.

`scope` n'est **pas** requis : un `scope` en échec fait déjà tourner tous les jobs requis, donc
l'exiger n'ajoute rien ; le vrai risque — un `scope` vert et faux — est invisible pour la
protection de branche et se combat par le selftest vendorisé de `ci_scope.py` et sa règle
fourre-tout (un chemin qu'aucun `COMPONENT_<ID>_RE` ni la règle de documentation ne reconnaît
lance tout). Un job de composant ne contient qu'un appel à `scripts/check.sh ci <c>` (plus
l'installation de la toolchain) : la CI, le hook et l'humain exécutent la même commande.

## 4. Règles de la CI

- **Jamais de `paths:` / `paths-ignore:` au niveau d'un workflow qui porte un check requis.**
  Un workflow filtré ne rapporte *aucun* statut ; une PR de documentation seule attendrait pour
  toujours un check requis qui ne viendra pas. Un job sauté par `if:` rapporte Success. Le
  selftest vendorisé de `ci_scope.py` lit `ci.yml` et refuse un filtre de chemins, une condition
  `if:` d'une autre forme, et une étape `scope` qui ne lit pas `previous_filename`.
- **Une vérification nouvelle = un step d'un job requis existant**, ou mieux une ligne de
  `scripts/check.sh`. Jamais un nouveau job : il ne serait pas requis tant que personne n'édite
  la protection, et renommer un job requis bloque toutes les PR ouvertes. Renommer un job reste
  possible, mais dans le même changement que la mise à jour de la protection (§7) et du wiki.
- **Le moins cher d'abord** : le job `tooling` tourne en parallèle et échoue en quelques
  secondes ; dans un job de composant, lint et audit passent avant les builds longs.
- **`timeout-minutes` sur chaque job** : un job bloqué consomme un runner et retarde toute la
  vague de PR parallèles.
- **Caches clés sur les verrous** (`hashFiles('<lockfile>')`) : un cache qui survit à un
  changement de verrou masque une installation cassée.
- **`concurrency`** : un orchestrateur qui pousse 4–5 branches en même temps dépasse vite la
  limite de jobs simultanés d'un compte ; annuler les runs de PR remplacés libère les runners,
  ne jamais annuler ceux de la branche par défaut garde un historique complet.
- **Réessai unique, sur un seul message connu** : une commande instable n'est relancée qu'une
  fois, et seulement si sa sortie contient la chaîne précise d'un incident connu ; le second
  statut est définitif. Un réessai général cache l'instabilité — et un artefact altéré échouerait
  quand même deux fois.
- **`*_REQUIRED=true`** pour tout test qui se saute quand son service ou sa variable manque : en
  CI il échoue au lieu de passer vert sans avoir rien exécuté.
- **Le run hebdomadaire force tous les drapeaux** (événement ≠ `pull_request`) : il attrape ce
  que le scope des PR a laissé passer et exécute les audits de dépendances même sans PR.
- **Pas de secret de déploiement en CI** par défaut : la CI prouve, le déploiement est l'affaire
  de l'orchestrateur (skill `deploy`). Un secret ajouté plus tard est documenté dans le wiki.
- **Rien du plugin** : un step qui appellerait un fichier du plugin (`bin/vendor.py`, un hook)
  échouerait sur un runner. Ce que la CI doit vérifier de l'outillage passe par les copies
  vendorisées et par `VENDORED.json`.
- Une PR créée par le `GITHUB_TOKEN` d'un workflow **ne déclenche aucun workflow** : ses checks
  requis ne rapporteraient jamais. D'où le §6 (pousser une branche, pas ouvrir de PR).

## 5. Hygiène des dépendances

`.github/dependabot.yml` (un bloc par écosystème et répertoire de composant) :

```yaml
version: 2
updates:
  - package-ecosystem: "<uv|pip|npm|gomod|cargo|gradle|maven>"
    directory: "/<component dir>"
    schedule: { interval: "weekly", day: "monday" }
    open-pull-requests-limit: 5
    commit-message: { prefix: "chore" }
    groups:
      <ecosystem>-minor-patch:
        update-types: ["minor", "patch"]
  - package-ecosystem: "github-actions"
    directory: "/"
    schedule: { interval: "weekly", day: "monday" }
    commit-message: { prefix: "chore" }
    groups:
      actions:
        patterns: ["*"]
```

- Une PR Dependabot passe toute la CI et se merge **comme les autres** (squash, par
  l'orchestrateur, après lecture) — jamais en auto-merge. Une montée de version majeure est
  traitée comme un changement normal (entrée `wip/`, lane selon ce qu'elle touche).
- **Scan de vulnérabilités** : il vit **dans `scripts/check.sh ci <c>`** (WP-A), jamais dans un
  step séparé de `ci.yml`, pour que la CI et l'humain lancent la même chose. L'outil de chaque
  composant est écrit par l'orchestrateur dans `Project.md` § Components ; par défaut, l'audit
  de l'écosystème, sans installation supplémentaire (`uv audit`/`pip-audit --strict`,
  `npm audit --omit=dev --audit-level=high`, `cargo audit`, `govulncheck ./...`). Si
  `Project.md` nomme `osv-scanner`, WP-F ajoute avant `check.sh ci` un step qui l'installe
  **épinglé par version et vérifié par SHA-256** (un scanner téléchargé sans somme de contrôle
  est lui-même un risque de chaîne d'approvisionnement), et `.github/osv-scanner.toml`. Les
  variables `<NAME>_REQUIRED` sont posées par `check.sh ci` seul. Les alertes Dependabot restent
  actives, mais seul le scan en CI fait échouer un build.
- **Politique d'ignore** — `.github/osv-scanner.toml` (passé par `--config`) ou l'option
  équivalente de l'audit :

  ```toml
  # Only an advisory with no fixed release yet may be ignored here. Every entry expires and names
  # the wip/ entry that tracks it. Remove it in the pull request that bumps past the fix.
  # [[IgnoredVulns]]
  # id = "GHSA-xxxx-xxxx-xxxx"
  # ignoreUntil = 2027-01-31
  # reason = "no fixed release yet — wip/todo_nr/YYYY-MM-DD-<package>-<id>.md"
  ```
  Pourquoi l'expiration : un ignore éternel devient invisible ; `ignoreUntil` remet le job au
  rouge à la date dite, et l'entrée `wip/` dit qui doit regarder. Un scan n'est **jamais laissé
  rouge** : on corrige, ou on ignore selon cette règle.

## 6. Niveau Complet — `.github/workflows/deps.yml`

Workflow mensuel qui rafraîchit ce que Dependabot ne voit pas : dépendances transitives des
verrous, artefacts générés ou vendus à partir des dépendances (licences tierces, binaires
copiés, code généré). En shipyard 0.1, `TOOLING_LEVEL` vaut toujours `essentiel` : WP-F ne
l'écrit pas, et l'entrée `wip/todo_nr/` qui l'attend (WP-D) reprend cette section comme
spécification autonome.

```yaml
name: Dependency refresh
on:
  schedule:
    - cron: '<m> <h> <day-of-month> * *'   # offset from Dependabot's weekly run: never race on a lock
  workflow_dispatch:
permissions:
  contents: read
jobs:
  refresh:
    name: Refresh locks and generated artefacts
    runs-on: ubuntu-latest
    timeout-minutes: 30
    permissions:
      contents: write                       # push a branch; never opens the pull request
    steps:
      - uses: actions/checkout@<sha40> # <version>
      - <toolchain setup, pinned>
      - name: Refresh
        run: <uv lock --upgrade | npm update | cargo update | …>; <regenerate generated artefacts>
      - name: Verify
        run: scripts/check.sh all
      - name: Push a branch if anything changed
        run: |
          set -euo pipefail
          git add -A                           # new generated files too, not only tracked ones
          git diff --cached --quiet && { echo "Nothing to refresh." >> "$GITHUB_STEP_SUMMARY"; exit 0; }
          b="chore/deps-$(date -u +%F)"
          git ls-remote --exit-code --heads origin "$b" >/dev/null 2>&1 && b="$b-${{ github.run_number }}"
          git switch -c "$b"
          git -c user.name='github-actions[bot]' -c user.email='41898282+github-actions[bot]@users.noreply.github.com' \
              commit -m "chore: refresh dependencies ($(date -u +%F))"
          git push origin "$b"                # never --force
          printf 'Open the pull request:\n\n    gh pr create --base <default-branch> --head %s --title "chore: refresh dependencies" --body "Monthly refresh."\n' "$b" >> "$GITHUB_STEP_SUMMARY"
```

- **Il pousse une branche, il n'ouvre pas la PR** : une PR créée avec `GITHUB_TOKEN` ne
  déclenche aucun workflow, ses checks requis ne rapporteraient jamais ; un jeton personnel ou
  une GitHub App serait un secret de plus à faire tourner. L'orchestrateur (ou l'humain) ouvre
  la PR avec la commande imprimée.
- **Jamais de force-push** : une branche du même jour reçoit un suffixe.
- **Il ne peut pas être essayé avant d'être sur la branche par défaut** : `workflow_dispatch`
  répond 404 depuis une branche. Le premier run réel est le mois suivant le merge, ou un
  déclenchement manuel après le merge.
- Un cron que GitHub a désactivé (60 jours sans activité du dépôt) ne rougit rien : c'est au
  contrôle des workflows planifiés de le dire, comme pour le run hebdomadaire de `ci.yml`.

## 7. Réglages du dépôt, `CODEOWNERS` et protection de la branche par défaut (orchestrateur)

### 7.1 Réglages du dépôt — juste après `gh repo create`

```bash
gh api -X PATCH "repos/{owner}/{repo}" \
  -F allow_squash_merge=true -F allow_merge_commit=false -F allow_rebase_merge=false \
  -F delete_branch_on_merge=true -F allow_auto_merge=false \
  -f squash_merge_commit_title=PR_TITLE -f squash_merge_commit_message=PR_BODY
```
(`-F` pour les booléens typés, `-f` pour les chaînes.) Pourquoi :
- **Squash seul** : un commit par PR sur la branche par défaut — annulable en une étape, et
  c'est sur lui que le déploiement après chaque merge est indexé. Le titre du commit est le
  titre conventionnel de la PR.
- **Suppression de la branche au merge** : la branche locale devient `[gone]`, et le hook de
  commit refuse alors d'y committer (une branche dont la PR est mergée ne doit plus rien
  recevoir ; un correctif est une nouvelle PR).
- **Pas d'auto-merge** : les merges sont sériels et faits par l'orchestrateur après lecture du
  diff et application de la lane ; un auto-merge sauterait ces deux étapes.

### 7.2 Protection — après le merge de la PR de bootstrap

La protection s'applique **une fois la PR de bootstrap mergée** : le bootstrap n'est jamais
bloqué par ses propres règles, et les noms de checks existent alors réellement. Les contextes
sont recopiés des noms que les checks de cette PR ont **effectivement** rapportés
(`gh pr checks <n> --json name --jq '.[].name'`), jamais retapés : un contexte mal orthographié
est un check requis qui ne rapportera jamais, donc toutes les PR bloquées.

```bash
gh api -X PUT "repos/{owner}/{repo}/branches/<default-branch>/protection" --input - <<'JSON'
{
  "required_status_checks": {
    "strict": true,
    "contexts": ["Tooling — selftests, wiki, wip", "<Component 1 job name>", "<Component 2 job name>"]
  },
  "enforce_admins": true,
  "required_pull_request_reviews": null,
  "restrictions": null,
  "required_linear_history": true,
  "allow_force_pushes": false,
  "allow_deletions": false
}
JSON
```
(Si l'API refuse `contexts`, utiliser `"checks": [{"context": "<nom>"}, …]`.)

| Réglage | Valeur | Conséquence et pourquoi |
|---|---|---|
| `strict` | `true` | une branche doit contenir la pointe de la branche par défaut pour merger : les merges sont **sériels**, et chaque merge rend les autres PR périmées — on les met à jour par `gh api -X PUT repos/{owner}/{repo}/pulls/<n>/update-branch` (merge de la branche par défaut dans la branche, jamais de rebase) |
| `contexts` | `tooling` + jobs de composant, **pas `scope`** | §3 |
| `enforce_admins` | `true` | sans lui, le jeton du propriétaire — celui qu'utilise l'agent — peut merger une PR rouge (`--admin`) et pousser sur la branche par défaut ; les hooks du plugin refusent aussi ces deux gestes : deux lignes de défense, l'une côté agent, l'autre côté serveur. Un correctif urgent passe donc aussi par une PR — c'est le but |
| `required_pull_request_reviews` | `null` (défaut, solo comme équipe) | en solo, une approbation requise bloquerait tout : GitHub ne laisse pas l'auteur approuver sa PR ; la revue indépendante des lanes B et C est faite par un agent qui n'a pas écrit le changement. En équipe, l'approbation des owners est un **process** tenu par `ship-parallel` (§7.3) ; la règle de branche n'est qu'une option |
| `required_linear_history` | `true` | pas de commit de merge sur la branche par défaut : squash |
| `allow_force_pushes` / `allow_deletions` | `false` | l'historique partagé ne se réécrit pas ; côté branches de travail, c'est le hook qui refuse le force-push |

Relecture, comparée aux valeurs **attendues** que WP-D a déjà écrites dans
`ParallelDelivery.md` (le tableau ci-dessus) ; si elles diffèrent, SKILL.md §8 dit comment le
consigner (petite PR `docs/`) :
```bash
gh api "repos/{owner}/{repo}/branches/<default-branch>/protection" --jq \
  '{strict: .required_status_checks.strict, contexts: .required_status_checks.contexts,
    admins: .enforce_admins.enabled, linear: .required_linear_history.enabled,
    force: .allow_force_pushes.enabled,
    codeowners: (.required_pull_request_reviews.require_code_owner_reviews // false)}'
```

**Dépôt privé en offre gratuite** : le PUT répond 403 (« Upgrade to GitHub Pro or make this
repository public to enable this feature » ; les rulesets ont la même limite). On le sait
d'avance : la sonde en lecture seule de SKILL.md §3 (`GET …/protection` sur le dépôt réel, qui
tient compte du plan d'une organisation) le dit avant le contrat, et `Project.md` le porte. Ne
pas contourner : `ParallelDelivery.md` dit que la protection est indisponible et que **les hooks
sont la seule garde** (y compris contre `--admin` et le push direct), et une entrée
`wip/todo_nr/` « protect the default branch » (rendre le dépôt public, passer à une offre
payante, ou accepter le risque — décision de l'utilisateur) est écrite par WP-D. Le bootstrap
continue.

### 7.3 Équipe — `.github/CODEOWNERS` et l'option `require_code_owner_reviews`

En `TEAM_MODE=team`, l'orchestrateur écrit `.github/CODEOWNERS` avant le fan-out, avec la zone
que la personne qui bootstrappe a déclarée au questionnaire, plus les chemins d'outillage
qu'elle possède tant que l'équipe n'en décide pas autrement :

```text
# .github/CODEOWNERS — who owns which path of this repository.
# Kept by /shipyard:join (one pull request per new member, approved by the current owners) and
# read by scripts/owners.py and by GitHub (review requests). Last matching pattern wins.
# The human-readable copy, with the reasons, is .llmwiki/Team.md: change both in one pull request.
/<component dir>/   @<login>
/.claude/           @<login>
/scripts/           @<login>
/.github/           @<login>
/CLAUDE.md          @<login>
```

`wip/` et `.llmwiki/` n'ont **pas** d'owner : presque chaque PR les touche (clôture de son
entrée, page qu'elle rend fausse), et leur owner devrait approuver chaque PR de chaque
coéquipier — exactement la file d'attente que le process veut éviter.

- Un motif par ligne, ancré par `/`, owners en `@login`. Pas de motif `*` global, sauf si la
  zone déclarée est « tout le dépôt pour l'instant » : alors une ligne `*  @<login>` en tête,
  que les zones déclarées plus tard par `/shipyard:join` précisent (le dernier motif qui
  correspond gagne). Sans `*`, un chemin qu'aucun motif ne couvre n'a pas d'owner, et n'attend
  l'approbation de personne.
- GitHub cherche le fichier dans `.github/`, puis à la racine, puis dans `docs/` ;
  `scripts/owners.py` suit le même ordre, avec la même règle « le dernier motif qui correspond
  gagne ». Un seul fichier, dans `.github/`.
- **Ce qu'il change** : GitHub demande automatiquement la revue des owners de chaque zone
  touchée ; `ship-parallel` ne merge une PR qui touche une zone dont l'utilisateur de la session
  n'est pas owner qu'après l'approbation d'un owner de chaque zone étrangère
  (`gh pr view <n> --json latestReviews`) ; le hook `SessionStart` dit à chacun ce qu'il possède,
  ou de lancer `/shipyard:join`.
- **L'option `require_code_owner_reviews`** fait de cette approbation une règle de branche.
  Elle n'est **jamais appliquée au bootstrap** et le questionnaire ne la propose pas : elle n'a
  de sens que lorsque **chaque zone a plusieurs owners** : GitHub ne laisse pas
  l'auteur d'une PR l'approuver, donc un owner seul de sa zone ne peut plus merger ses propres
  PR, et avec `enforce_admins` personne ne peut passer outre. Au bootstrap, la personne qui
  bootstrappe est seule owner de tout : avec l'option, chacune de ses PR attendrait
  l'approbation d'un second owner qui n'existe pas encore. C'est une décision d'équipe, plus
  tard, par une PR qui met à jour la protection et `ParallelDelivery.md` ; ce jour-là, le bloc
  `required_pull_request_reviews` du PUT de §7.2 devient :

  ```json
  "required_pull_request_reviews": {
    "required_approving_review_count": 1,
    "require_code_owner_reviews": true,
    "dismiss_stale_reviews": false
  }
  ```
  `dismiss_stale_reviews: false` : `ship-parallel` met chaque branche à jour par `update-branch`
  avant son merge ; avec `true`, chaque mise à jour effacerait l'approbation et la redemanderait
  à chaque merge de la vague. La relecture de §7.2 doit alors lire `codeowners: true`.

## 8. Optionnel — workflow de publication d'un site statique

Pour une cible de type pages statiques (`deploy-<cible>.yml`) :
- Déclencheur `push` sur la branche par défaut **avec** un filtre `paths:` : acceptable ici
  parce que ce n'est **pas** un check requis — rien n'attend son statut.
- `concurrency: { group: deploy-<cible>, cancel-in-progress: false }` : on n'annule jamais un
  déploiement à mi-chemin ; le suivant attend.
- Permissions minimales au niveau du job de déploiement (ex. `pages: write`, `id-token: write`),
  et seulement sur `refs/heads/<default-branch>`.
- Le build réutilise `scripts/check.sh` (mêmes gates que la CI) avant de publier.
- **Test fumée après déploiement** : quelques chemins clés interrogés avec réessais
  (`curl --fail --retry 5 --retry-delay 10 --retry-all-errors`), en vérifiant un **contenu**
  attendu, pas seulement un code 200 — une page d'erreur servie avec 200 passe un test de statut.

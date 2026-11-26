# Couche core Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Passer de raw → customer à raw → core → customer, lisible en démo.

**Architecture:** Cinq contrats core portent les règles partagées ; les customer ne lisent que core. La validation est d'abord élargie, les contrats migrent, puis la règle est durcie : `make check` passe à la fin de chaque tâche.

**Tech Stack:** Python 3.12, ODCS v3.2.0 YAML, pytest.

**Spec:** `docs/superpowers/specs/2026-11-26-core-layer-design.md` (colonnes et règles des 5 modèles : les lire là).

## Global Constraints

- Contrats core : `contracts/core/core__<nom>.odcs.yaml`, dataset `core`, domaine `core`, équipe `team-core`, version `1.0.0`.
- Customer : version `2.0.0`, noms et types de colonnes inchangés.
- Aucun e-mail dans core ; `customer_key` : C2, tag `pseudonymized`, expression canonique (L012).
- `description.*` : 350 caractères maximum (L017). Contrats en français, interface en anglais.
- Le SQL repris vient des `transformInputs` actuels : aucune règle nouvelle, aucune règle modifiée.
- Pas de graphe maison dans la page Doc : la démo utilise l'onglet Lineage natif.
- Pas de modification de `.github/`. Commits montrés et validés avant exécution (CLAUDE.md) ; aucun push sans demande.

## Review Focus

- Un remboursement d'une commande web non valide doit rester exclu (jointure sur les commandes valides).
- Un ticket magasin lié à une commande web remboursée sur Shopify ne doit pas être compté deux fois.
- La cohorte 90 jours d'acquisition ne lit que `source_system = 'shopify'`, pas les retours en caisse.
- `kpis` utilise la date locale du magasin (`event_date`), `audiences` l'instant UTC (`event_at`) : ne pas les intervertir.
- Un client sans signal de consentement reste NULL, donc exclu des audiences.

Ces cinq points portent sur du SQL non exécuté dans ce dépôt : chacun est une vérification de relecture à la tâche 2 ou 3, pas un test automatique.

---

### Task 1: La validation connaît la couche core

**Files:** Modify `tools/validate_lineage.py`, `docs/conventions.md` ; Test `tests/test_validators.py`, `tests/fixtures/broken/`.

**Interfaces:** Produces `Contract.layer == "core"`, `CORE_COUNT = 5`.

- [ ] Ajouter les fixtures cassées `l002_core_bad_name` (`core_sales` sans `__`), `l004_core_references_customer`, `l008_core_missing_logic`, `l019_core_without_primary_key` ; chacune avec `expect.txt` (code puis extrait du message). Porter la borne de `test_each_rule_has_a_broken_fixture` à `range(1, 20)`.
- [ ] `.venv/bin/python -m pytest -q` : les 4 nouveaux cas échouent.
- [ ] Reconnaître la couche core : L002 (`^core__[a-z0-9_]+$`, domaine et dataset `core`), L004 (core lit raw ou core ; customer lit encore raw ou core à ce stade), L005, L008, L012, L016 appliqués à core, L019 « un objet core a au moins une property `primaryKey` ». L001 inchangé à ce stade.
- [ ] `make check` : OK. Commit `feat: couche core dans la validation`.

### Task 2: Les cinq contrats core

**Files:** Create `contracts/core/core__{sales_events,customers,ad_spend,campaigns,web_events}.odcs.yaml` ; Modify `tools/validate_lineage.py` (L001), `CODEOWNERS` (`/contracts/core/ @org/team-core`).

**Interfaces:** Produces les colonnes exactes de la spec, objet de schéma = nom sans `core__` (ex. `core__sales_events#sales_events.event_id`).

- [ ] Écrire les 5 contrats : grain, `primaryKey`, `quality` (unicité et non-nullité de la clé, valeurs autorisées, signe des montants), SLA, `loadStrategy`, lineage par colonne, `transformInputs` repris du SQL actuel.
- [ ] L001 : exiger `CORE_COUNT = 5` ; adapter la fixture `l001_count`.
- [ ] Relire les points « Review Focus » 1, 2 et 5 contre le SQL d'origine.
- [ ] `make check` : OK, 22 contrats. Commit `feat: cinq contrats core`.

### Task 3: Les customer lisent uniquement core

**Files:** Modify les 3 `contracts/customer/**`, `tools/validate_lineage.py`, `tests/fixtures/**`, `docs/conventions.md`, `docs/use-cases/*.md`.

**Interfaces:** Consumes les colonnes de la tâche 2.

- [ ] Ajouter la fixture `l004_customer_references_raw`, attendue en échec ; lancer pytest : elle échoue.
- [ ] Rebrancher `transformSourceObjects`, `transformExpression` et `transformInputs` sur core ; version `2.0.0`.
- [ ] Durcir L004 : customer → core uniquement. Migrer les fixtures valides et cassées qui référencent un raw depuis un customer (ajouter un core minimal par mini-dépôt) en gardant la règle visée par chacune.
- [ ] Relire les points « Review Focus » 3 et 4 ; comparer colonne par colonne les noms et types avec `origin/main`.
- [ ] `make check` : OK. Commit `feat!: les customer lisent uniquement core`.

### Task 4: Catalogue et démo en trois couches

**Files:** Modify `tools/build_catalog.py`, `tools/catalog_assets/{lineage.html,lineage.fr.html}`, `tests/test_catalog.py`, `README.md`, `CHANGELOG.md`.

**Interfaces:** Consumes `Contract.layer` (tâche 1). Un nœud core a `nodeType == "model"` et apparaît sous `core` dans l'arborescence.

- [ ] Test : les 5 nœuds core existent avec `nodeType == "model"` et aucune arête ne va d'un raw vers un customer ; le lancer.
- [ ] Adapter `build_manifest` si le test échoue.
- [ ] Pages Doc : premier écran = la règle et les trois couches (raw, core, customer) ; sections détaillées dans des `<details>` ; mettre à jour l'exemple `spend_amount`, qui passe désormais par `core__ad_spend`. Pas de graphe maison.
- [ ] `make check && make catalog` ; capture de l'onglet Lineage sur `acquisition_monthly` : trois couches visibles de gauche à droite.
- [ ] Commit `feat: démo en trois couches`.

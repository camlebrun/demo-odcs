# Onglet Trace en arbre : plan d'implémentation

> Plan initial (arbre seul). L'écran a ensuite changé en cours de route : la spec fait foi.

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans (ou subagent-driven-development), tâche par tâche.

**Goal:** Pour la colonne choisie, un arbre « qui alimente quoi » jusqu'au système source, avec un panneau de détail.

**Architecture:** `build_catalog.py` expose les sources externes des raw. `column_info.js` remplace la chaîne par couche par un parcours en profondeur depuis la colonne choisie. Choisir une ligne ne redessine que le détail et le surlignage, pour garder les branches repliées.

**Tech Stack:** Python, JS sans dépendance (injecté dans dbt-colibri), pytest + node.

**Spec:** `docs/superpowers/specs/2026-11-27-trace-tree-design.md`

## Global Constraints
- Aucune dépendance nouvelle, aucun appel réseau, pas de CI ni de contenu de contrat modifié.
- Textes d'interface en anglais, comme l'existant (« voir plus haut » devient `shown above`).
- Vérifier qu'une classe Tailwind existe avant de l'utiliser ; styles nouveaux en `.cp-*`.
- Les fonctions de rendu ne lèvent jamais d'exception ; toute donnée passe par `esc()`.
- Branche `feat/trace-chain`, PR #5. **Aucun commit sans accord** : montrer le plan de commits à la fin.

## Review Focus
- Contrat à plusieurs objets (colonnes `objet.champ`, noms longs) : lignes lisibles et cliquables, sans débordement horizontal.
- Changement de colonne : le détail revient sur la racine, pas sur le nœud choisi auparavant.
- Re-rendu React après un clic : le nœud choisi reste affiché (les branches repliées peuvent se rouvrir).
- Nom contenant `"` ou `<` : échappé dans le texte et les attributs.
- Clic sur le triangle d'une branche : replie sans changer la sélection ; clic sur la ligne : sélectionne sans replier.

---

### Task 1 : sources externes des raw

**Files:** Modify `tools/build_catalog.py` (dict `meta`, l. 109-122) ; Test `tests/test_catalog.py`

**Interfaces:** Produces `nodes[cid].columns[col].meta.externalSources: list[str]`, couche raw seulement, absent si vide.

- [ ] Test :
```python
def test_manifest_exposes_external_sources_of_raw_columns_only():
    nodes = build_catalog.build_manifest(FIXTURE)["nodes"]
    cols = nodes["raw__pages_views__ga4"]["columns"]
    assert cols["event_name"]["meta"]["externalSources"] == ["ga4_bigquery_export#events.event_name"]
    assert "externalSources" not in cols["meta_loaded_at"]["meta"]
    assert "externalSources" not in nodes["core__orders"]["columns"]["customer_key"]["meta"]
```
- [ ] `.venv/bin/python -m pytest -q tests/test_catalog.py -k external_sources` : FAIL (`KeyError`).
- [ ] Ajouter la clé à `meta` avec `sources_of(node) or None` quand `c.layer == "raw"`.
- [ ] Même commande : PASS.

### Task 2 : arbre et détail

**Files:** Modify `tools/catalog_assets/column_info.js` (l. 106-301), `tools/catalog_assets/column_info.css` (l. 29-48) ; Test `tests/test_catalog.py`

**Interfaces:**
- Consumes `meta.externalSources` (Task 1).
- Conserve `window.cpTraceTabHtml(model)` et `window.cpTraceColumnSet(model, col)` (appelés par `catalog_template.py`).
- Produces `window.cpTraceNodeSet(nodeModel, nodeCol)` : mémorise le nœud pour le contrat et la colonne affichés, met à jour `.cp-detail` et `.cp-on` sans réécrire l'arbre.

**Rendu attendu** (dans `.cp-chain`) :
- `.cp-tree` : `<ul>/<li>` imbriqués, racine = colonne choisie, enfants dans l'ordre des arêtes.
- Ligne : `<button class="cp-node" data-cp-node-model data-cp-node-col>` avec contrat, colonne, badge `transformLogic` ; `cp-copy` (grisée) si `map` ; `not documented` sans `transformDescription`.
- Branche avec enfants : `<details open><summary>` contenant le bouton.
- Feuille raw : un `<div class="cp-ext">` par source externe.
- Colonne déjà rendue (diamant, cycle) : même bouton, classe `cp-ref`, texte `shown above`, sans enfants.
- Au-delà de `TRACE_MAX = 400` lignes : `<div class="cp-note cp-truncated">Trace truncated at 400 lines.</div>`.
- `.cp-detail` : nœud choisi (racine par défaut) : titre, badge, description ou `Transformation not documented`, SQL ouvert, toutes les entrées en boutons (mêmes attributs `data-cp-node-*`), sources externes.
- Sans amont : racine seule, avec les phrases actuelles (`Created in this contract…` / `No upstream lineage declared…`).
- Contrat raw : même arbre ; la phrase `Raw contract: no upstream…` disparaît.
- Liste de gauche : `T` devient `has sources`. Pour un raw, il s'applique si `externalSources` existe.
- En-tête : `N transformations · M contracts` conservé au-dessus de l'arbre.
- CSS : arbre et détail côte à côte ; `@media (max-width:900px)` détail sous l'arbre. Supprimer `.cp-result`, `.cp-contract`, `.cp-from` et les fonctions par couche devenues mortes (`LAYER_RANK`, `layerOf`, `heights`, `traceSteps`, `traceContractHtml`, `traceChainHtml`).

- [ ] Tests. Étendre `HARNESS`/`_trace` avec `node: tuple[str, str] | None` (appelle `cpTraceNodeSet` après la colonne). Remplacer les tests des l. 111-147 et 162-189 ; garder 150-159 en déplaçant l'assertion `TO_HEX` sur `node=("core__orders", "customer_key")`.
```python
def test_trace_tree_goes_from_result_to_external_source(tmp_path):
    m = build_catalog.build_manifest(FIXTURE)
    t = _trace(tmp_path, m, "kpis_monthly", "customer_key")
    assert t.index('data-cp-node-model="kpis_monthly"') < t.index('data-cp-node-model="core__orders"') < t.index('data-cp-node-model="raw__orders__shopify"')
    assert "shopify_admin_api#orders.email" in t
    assert "<details open" in t and 'class="cp-detail"' in t
    assert "TO_HEX" not in t  # SQL amont : seulement quand le noeud est choisi
    assert "TO_HEX" in _trace(tmp_path, m, "kpis_monthly", "customer_key", node=("core__orders", "customer_key"))

def test_trace_tree_on_a_raw_contract_shows_the_external_system(tmp_path):
    m = build_catalog.build_manifest(FIXTURE)
    t = _trace(tmp_path, m, "raw__pages_views__ga4", "event_name")
    assert "ga4_bigquery_export#events.event_name" in t
    assert "Raw contract: no upstream" not in t
```
Avec des nœuds construits à la main (helpers `col`/`node` de l'ancien test l. 127-131) :
  - `test_trace_tree_shows_a_shared_column_once_and_survives_cycles` : diamant `mart.k <- a.k, b.k <- raw.x` plus arête `mart.k -> a.k` ; assert `t.count("shown above") == 2`, `t.count('class="cp-ext"') == 1`, `"not documented" in t`.
  - `test_trace_tree_says_when_truncated` : `mart.k` alimenté par 450 colonnes ; assert `"Trace truncated at 400 lines." in t`.
  - `test_trace_tree_escapes_names` : colonne amont `a"<b>` ; assert `'a"<b>' not in t` et `"a&quot;&lt;b&gt;" in t`.
  - `test_trace_tree_resets_detail_on_column_change` : choisir un nœud, puis une autre colonne (harnais dédié) ; le détail porte le titre de la nouvelle racine.
- Le test « tous les contrats du repo » (l. 192) reste ; y appeler aussi `cpTraceNodeSet(id, col)`.
- [ ] `.venv/bin/python -m pytest -q tests/test_catalog.py` : les nouveaux tests FAIL.
- [ ] Implémenter. Parcours en profondeur préfixe avec un ensemble `seen` (première occurrence dépliée). État : `TRACE_NODE[model + "\u001f" + col]`, effacé par `cpTraceColumnSet`. Délégation de clic sur `[data-cp-node-col]`.
- [ ] Même commande : PASS. Puis `make check` : tout PASS.

### Task 3 : documentation et vérification réelle

**Files:** Modify `README.md:59`, `CHANGELOG.md:13`

- [ ] Réécrire les deux entrées « Trace » : arbre depuis le résultat, système source, détail au clic.
- [ ] `make catalog`, puis Playwright (`uv run --no-project --with playwright`, `channel="chrome"`, script dans le scratchpad) avec de vrais clics : `acquisition_monthly.new_customer_roas`, une ligne de l'arbre, un triangle, une colonne raw, thèmes clair et sombre, largeur 800 px. Regarder les captures et contrôler le Review Focus.
- [ ] `make check` : PASS. `git status` : pas de `uv.lock`.
- [ ] Montrer le plan de commits (builder ; arbre ; docs, spec et plan) et attendre l'accord.

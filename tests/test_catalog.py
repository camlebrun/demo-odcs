"""Tests du generateur de catalogue (JSON consomme par dbt-colibri)."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

import build_catalog

FIXTURE = Path(__file__).parent / "fixtures" / "valid" / "mini_repo"
ASSETS = Path(build_catalog.__file__).parent / "catalog_assets"

# Execute catalog_assets/column_info.js hors navigateur : window/document factices, manifeste
# injecte comme dans l'index.html (metadata, nodes, lineage.edges, tree).
HARNESS = """
const fs = require("fs");
const [asset, manifestPath, model, column, clickModel, nodeModel, nodeCol, nextColumn] = process.argv.slice(2);
global.window = {};
global.document = { documentElement: { classList: { toggle() {} } }, addEventListener() {} };
global.navigator = {};
eval(fs.readFileSync(asset, "utf8"));
const src = JSON.parse(fs.readFileSync(manifestPath, "utf8"));
window.colibriData = { metadata: src.metadata, nodes: src.nodes, lineage: { edges: src.lineage.edges }, tree: src.tree };
const shown = model === "" ? null : model;
if (column) window.cpTraceColumnSet(clickModel || model, column);
if (nodeModel) { window.cpTraceTabHtml(shown); window.cpTraceNodeSet(nodeModel, nodeCol); }
if (nextColumn) { window.cpTraceTabHtml(shown); window.cpTraceColumnSet(model, nextColumn); }
process.stdout.write(window.cpTraceTabHtml(shown));
"""


def _trace(
    tmp_path, manifest: dict, model: str, column: str | None = None, click_model: str | None = None,
    node: tuple[str, str] | None = None, next_column: str | None = None,
) -> str:
    """Rend l'onglet Trace d'un contrat avec node (le JS du catalogue n'est pas reimplemente en Python).
    `model=""` simule un rendu React dont l'etat contrat est absent (vue lineage) ; `column` simule
    la colonne cliquee dans la liste des colonnes du panneau du contrat, `click_model` le contrat
    de ce clic quand il differe de l'etat React ; `node` simule le clic sur une ligne de l'arbre,
    `next_column` un changement de colonne ensuite."""
    node_bin = shutil.which("node")
    if not node_bin:
        pytest.skip("node est necessaire pour executer le JS du catalogue")
    harness = tmp_path / "trace.js"
    harness.write_text(HARNESS, encoding="utf-8")
    data = tmp_path / "manifest.json"
    data.write_text(json.dumps(manifest), encoding="utf-8")
    args = [node_bin, str(harness), str(ASSETS / "column_info.js"), str(data), model,
            column or "", click_model or model, *(node or ("", "")), next_column or ""]
    out = subprocess.run(args, capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    return out.stdout


def test_manifest_has_one_node_per_contract():
    m = build_catalog.build_manifest(FIXTURE)
    assert set(m["nodes"]) == {
        "raw__orders__shopify",
        "raw__pages_views__ga4",
        "core__orders",
        "core__events",
        "kpis_monthly",
    }
    assert m["metadata"]["total_model_count"] == 5


def test_column_edges_follow_transform_source_objects():
    m = build_catalog.build_manifest(FIXTURE)
    col_edges = [e for e in m["lineage"]["edges"] if e["targetColumn"]]
    assert col_edges, "le customer du fixture declare du lineage"
    for e in col_edges:
        assert e["target"] in {"kpis_monthly", "core__orders", "core__events"}
        assert e["sourceColumn"] in m["nodes"][e["source"]]["columns"]
        assert e["targetColumn"] in m["nodes"][e["target"]]["columns"]
        assert m["nodes"][e["target"]]["columns"][e["targetColumn"]]["hasLineage"] is True
    # une arete de contrat a contrat (sans colonne) par source referencee
    contract_edges = {(e["source"], e["target"]) for e in m["lineage"]["edges"] if not e["targetColumn"]}
    assert {s for s, t in contract_edges if t == "kpis_monthly"} <= {"core__orders", "core__events"}


def test_repository_lineage_goes_raw_core_customer():
    m = build_catalog.build_manifest(Path(build_catalog.REPO_ROOT))
    nodes = m["nodes"]
    cores = [n for n in nodes if n.startswith("core__")]
    assert len(cores) == 5
    assert all(nodes[n]["nodeType"] == "model" for n in cores)
    customers = {"acquisition_monthly", "audiences", "kpis_monthly"}
    parents = {e["source"] for e in m["lineage"]["edges"] if e["target"] in customers}
    assert parents and all(p.startswith("core__") for p in parents), sorted(parents)


def test_parents_and_children_are_symmetric():
    m = build_catalog.build_manifest(FIXTURE)
    for tgt, cols in m["lineage"]["parents"].items():
        for tcol, srcs in cols.items():
            for s in srcs:
                back = m["lineage"]["children"][s["dbt_node"]][s["column"]]
                assert {"dbt_node": tgt, "column": tcol, "lineage_type": s["lineage_type"]} in back


def test_template_patches_apply_and_remove_dbt_and_cloud_upsells():
    gen = pytest.importorskip("dbt_colibri.report.generator")
    from catalog_template import patch_template

    html = patch_template((Path(gen.__file__).parent / "index.html").read_text(encoding="utf-8"))
    forbidden = ("Colibri Cloud", "Copy dbt", "dbt build", "dbt compile", "getdbt.com", "Saved Views", "Column lineage unavailable", 'children:"Code"', 'children:"Model Information"', 'children:"Contract Enforced"')
    for text in forbidden:
        assert text not in html, text
    assert all(f in html for f in ("cpColumnHtml", "cpColumnTabHtml", "cpNodeHtml", "cpToggleExpert", "cpModelTestsHtml", "cpLoadStrategy", "cpObjectType", "cpTraceTabHtml", "cpTraceColumnSet", "window.cpFilterMatch(", 'id:"trace",label:"Trace",icon:cpTraceIcon', 'cpTraceIcon=pi("route"', 'id:"cp-trace-panel"', "data-cp-col", "cp-trace-wrap bg-background", ".cp-trace-wrap{pointer-events:auto}"))
    assert "f=window.cpFold(i),p=window.cpFold(s)" in html, "recherche sans accents"
    assert "window.cpTagMatch(Me.tags,x)" in html and "window.cpColumnTags(Xe.tags,x)" in html, "filtres par tag jusqu'aux colonnes"
    assert "cue(i.description,s,100)" in html, "la recherche globale lit la description du contrat"
    assert "gqt(Xe.columnName,Me,Xe.description)" in html, "et la description de colonne"
    assert 'placeholder:"Search contracts, columns, descriptions..."' in html
    assert "data-sidebar-column]{" not in html, "plus de contournement CSS sur le panneau natif"
    assert 'children:"Source trace"' not in html and "cp-trace-toggle" not in html, "l'ancien bouton Source trace est retire"


def test_column_link_is_offered_and_read_back(tmp_path):
    node_bin = shutil.which("node")
    if not node_bin:
        pytest.skip("node est necessaire pour executer le JS du catalogue")
    harness = tmp_path / "link.js"
    harness.write_text("""
const fs = require("fs");
global.window = { location: { href: "https://x.test/index.html?model=old#h", search: "" } };
global.document = { documentElement: { classList: { toggle() {} } }, addEventListener() {} };
global.navigator = {};
eval(fs.readFileSync(process.argv[2], "utf8"));
if (window.cpColumnLink("m") !== "https://x.test/index.html?model=m&view=trace") throw new Error("lien de contrat");
const link = window.cpColumnLink("a b", "c&d");
console.log(JSON.stringify([link, window.cpDeepLink(new URL(link).search),
  window.cpDeepLink("?model=m&column=c"), window.cpDeepLink("?view=trace&model=m")]));
""", encoding="utf-8")
    out = subprocess.run([node_bin, str(harness), str(ASSETS / "column_info.js")], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    link, back, native, partial = json.loads(out.stdout)
    assert link == "https://x.test/index.html?model=a%20b&column=c%26d&view=trace"
    assert back == {"model": "a b", "column": "c&d"}
    assert partial == {"model": "m", "column": None}, "un lien peut viser un contrat sans colonne"
    assert native is None, "un lien sans view=trace garde le comportement de colibri"
    html = _trace(tmp_path, _graph({"core__a": ["x"]}, []), "core__a", "x")
    assert 'data-cp-link' in html and "Copy link" in html


def test_search_folds_accents_and_combines_tag_groups(tmp_path):
    node_bin = shutil.which("node")
    if not node_bin:
        pytest.skip("node est necessaire pour executer le JS du catalogue")
    harness = tmp_path / "f.js"
    harness.write_text("""
const fs = require("fs");
global.window = {}; global.document = { documentElement: { classList: { toggle() {} } }, addEventListener() {} }; global.navigator = {};
eval(fs.readFileSync(process.argv[2], "utf8"));
const sel = new Set(["owner:a", "owner:b", "pii"]);
console.log(JSON.stringify([window.cpFold("P\u00e9rim\u00e8tre"),
  window.cpTagMatch(["owner:b", "pii"], sel), window.cpTagMatch(["owner:b"], sel), window.cpTagMatch([], new Set()),
  window.cpColumnTags(["pii"], sel), window.cpColumnTags([], sel), window.cpColumnTags([], new Set(["owner:a"])),
  window.cpColumnFiltered(sel), window.cpColumnFiltered(new Set(["owner:a"])),
  window.cpColumnTags(["pseudonymized"], new Set(["pii", "pseudonymized"])), window.cpColumnTags(["pseudonymized"], new Set(["pii"]))]));
""", encoding="utf-8")
    out = subprocess.run([node_bin, str(harness), str(ASSETS / "column_info.js")], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    assert json.loads(out.stdout) == ["perimetre", True, False, True, True, False, True, True, False, True, False]


def test_contract_tags_expose_owner_classification_and_pii():
    m = build_catalog.build_manifest(ASSETS.parents[1])
    tags = m["nodes"]["audiences"]["tags"]
    assert "owner:team-customer" in tags and "classification:C2" in tags
    levels = {t for c in m["nodes"]["audiences"]["columns"].values() for t in c.get("tags", []) if t.startswith("classification:") or t in ("pii", "pseudonymized")}
    assert levels <= set(tags)
    assert "pseudonymized" in tags


def test_nested_field_inherits_the_documentation_of_its_parent(tmp_path):
    parent = {"meta": {"transformLogic": "map", "transformDescription": "Recopie du tableau.", "externalSources": ["api#R.t"]}}
    nodes = {"core__a": {"id": "core__a", "columns": {"x": _col("transform", "Somme.")}},
             "raw__r__s": {"id": "raw__r__s", "nodeType": "source", "columns": {"t": parent, "t.amount": {"meta": {}}}}}
    edge = {"source": "raw__r__s", "sourceColumn": "t.amount", "target": "core__a", "targetColumn": "x"}
    html = _trace(tmp_path, {"nodes": nodes, "lineage": {"edges": [edge]}}, "core__a", "x")
    assert "t.amount" in html and "not documented" not in html and "api#R.t" in html


def _col(logic=None, desc=None):
    return {"meta": {k: v for k, v in (("transformLogic", logic), ("transformDescription", desc)) if v}}


def _graph(columns: dict[str, list[str]], pairs: list[tuple[str, str, str, str]]) -> dict:
    """Manifeste minimal : contrat -> colonnes ; aretes (source, colonne, cible, colonne)."""
    nodes = {c: {"id": c, "nodeType": "model", "columns": {n: _col("transform", f"Calcul {n}.") for n in cols}}
             for c, cols in columns.items()}
    keys = ("source", "sourceColumn", "target", "targetColumn")
    return {"nodes": nodes, "lineage": {"edges": [dict(zip(keys, p)) for p in pairs]}}


def test_trace_tab_lists_columns_and_follows_the_selected_one(tmp_path):
    manifest = build_catalog.build_manifest(FIXTURE)
    hint = _trace(tmp_path, manifest, "kpis_monthly")
    assert "Source trace · kpis_monthly" in hint
    assert 'data-cp-col="customer_key"' in hint and "Select a column" in hint
    assert "cp-tree" not in hint
    trace = _trace(tmp_path, manifest, "kpis_monthly", "customer_key")
    assert 'class="cp-colbtn cp-on" data-cp-model="kpis_monthly" data-cp-col="customer_key"' in trace
    assert "transformations ·" not in trace


def test_trace_tree_goes_from_result_to_external_source(tmp_path):
    m = build_catalog.build_manifest(FIXTURE)
    t = _trace(tmp_path, m, "kpis_monthly", "customer_key")
    order = [t.index(f'data-cp-node-model="{c}"') for c in ("kpis_monthly", "core__orders", "raw__orders__shopify")]
    assert order == sorted(order)
    assert '<div class="cp-ext">shopify_admin_api#Order.email</div>' in t, "systeme source toujours affiche"
    assert "<details open" in t and 'class="cp-detail"' in t
    assert "TO_HEX" in _trace(tmp_path, m, "kpis_monthly", "customer_key", node=("core__orders", "customer_key"))


def test_trace_tree_on_a_raw_contract_has_no_missing_upstream_note(tmp_path):
    t = _trace(tmp_path, build_catalog.build_manifest(FIXTURE), "raw__pages_views__ga4", "event_name")
    assert "Raw contract: no upstream" not in t and "ga4_bigquery_export#events.event_name" in t


def test_trace_tree_shows_a_shared_column_once_and_survives_cycles(tmp_path):
    g = _graph(
        {"raw__x": ["k"], "a": ["k"], "b": ["k"], "mart": ["k"]},
        [("a", "k", "mart", "k"), ("b", "k", "mart", "k"), ("raw__x", "k", "a", "k"),
         ("raw__x", "k", "b", "k"), ("mart", "k", "a", "k")],
    )
    g["nodes"]["raw__x"]["columns"]["k"] = {"meta": {"externalSources": ["sys#o.k"]}}
    t = _trace(tmp_path, g, "mart", "k")
    assert t.count("shown above") == 2  # raw__x sous b, et le retour sur mart
    assert "not documented" in t


def test_trace_tree_says_when_truncated(tmp_path):
    wide = [f"c{i}" for i in range(450)]
    g = _graph({"src": wide, "mart": ["k"]}, [("src", c, "mart", "k") for c in wide])
    t = _trace(tmp_path, g, "mart", "k")
    assert "Trace truncated at 400 lines." in t
    assert t.count('class="cp-node') == 400


def test_trace_tree_escapes_names(tmp_path):
    name = 'a"<b>'
    g = _graph({"src": [name], "mart": ["k"]}, [("src", name, "mart", "k")])
    t = _trace(tmp_path, g, "mart", "k")
    assert name not in t and "a&quot;&lt;b&gt;" in t


def test_trace_tree_resets_detail_on_column_change(tmp_path):
    g = _graph({"src": ["x"], "mart": ["k", "j"]}, [("src", "x", "mart", "k")])
    picked = _trace(tmp_path, g, "mart", "k", node=("src", "x"))
    assert '<div class="cp-dtitle">src.x</div>' in picked
    assert '<div class="cp-dtitle">mart.j</div>' in _trace(tmp_path, g, "mart", "k", node=("src", "x"), next_column="j")


def test_trace_tree_without_upstream_says_why(tmp_path):
    g = _graph({"mart": ["k"]}, [])
    assert "No upstream lineage declared" in _trace(tmp_path, g, "mart", "k")
    g["nodes"]["mart"]["columns"]["k"] = _col("create", "Constante.")
    assert "Created in this contract" in _trace(tmp_path, g, "mart", "k")


def test_trace_tab_survives_a_stale_react_model_state(tmp_path):
    """Reproduit le bug vu en ligne : la carte de colonnes de la vue lineage garde son etat interne,
    le rendu React du panneau Trace ne connait pas le contrat (l = null). Le panneau retombe sur le
    dernier contrat clique, et le clic met a jour le panneau sans re-rendu React."""
    manifest = build_catalog.build_manifest(FIXTURE)
    empty = _trace(tmp_path, manifest, "")
    assert "Select a contract to see its source trace." in empty
    stale = _trace(tmp_path, manifest, "", "customer_key", click_model="kpis_monthly")
    assert "Source trace · kpis_monthly" in stale
    assert "Alimente customer_key" in stale
    picked = _trace(tmp_path, manifest, "", "customer_key", click_model="kpis_monthly", node=("core__orders", "customer_key"))
    assert "TO_HEX" in picked


def test_trace_tab_and_column_panels_render_for_every_contract_of_the_repo(tmp_path):
    """Aucune fiche du repo ne fait planter le rendu React (page blanche)."""
    node = shutil.which("node")
    if not node:
        pytest.skip("node est necessaire pour executer le JS du catalogue")
    harness = tmp_path / "all.js"
    harness.write_text(
        """
const fs = require("fs");
const [asset, manifestPath] = process.argv.slice(2);
global.window = {};
global.document = { documentElement: { classList: { toggle() {} } }, addEventListener() {} };
global.navigator = {};
eval(fs.readFileSync(asset, "utf8"));
const src = JSON.parse(fs.readFileSync(manifestPath, "utf8"));
window.colibriData = { metadata: src.metadata, nodes: src.nodes, lineage: { edges: src.lineage.edges }, tree: src.tree };
const errors = [];
for (const id of Object.keys(window.colibriData.nodes)) {
  try { window.cpTraceTabHtml(id); } catch (e) { errors.push("cpTraceTabHtml " + id + " -> " + e.message); }
  const n = window.colibriData.nodes[id];
  const cols = Object.keys(n.columns || {});
  for (const col of cols) {
    for (const fn of ["cpColumnHtml", "cpColumnTabHtml", "cpNodeHtml"]) {
      try { window[fn](id, col); } catch (e) { errors.push(fn + " " + id + "." + col + " -> " + e.message); }
    }
    try { window.cpTraceColumnSet(id, col); window.cpTraceTabHtml(id); window.cpTraceNodeSet(id, col); window.cpTraceTabHtml(null); } catch (e) { errors.push("cpTraceTabHtml " + id + "." + col + " -> " + e.message); }
  }
}
process.stdout.write(JSON.stringify(errors));
""",
        encoding="utf-8",
    )
    data = tmp_path / "manifest.json"
    data.write_text(json.dumps(build_catalog.build_manifest(Path(build_catalog.REPO_ROOT))), encoding="utf-8")
    out = subprocess.run([node, str(harness), str(ASSETS / "column_info.js"), str(data)], capture_output=True, text=True, timeout=120)
    assert out.returncode == 0, out.stderr
    assert json.loads(out.stdout) == []


def test_render_writes_lineage_page_linked_from_dashboard(tmp_path):
    pytest.importorskip("dbt_colibri")
    html = build_catalog.render_html(build_catalog.build_manifest(Path(build_catalog.REPO_ROOT)), tmp_path)
    assert (tmp_path / "lineage.html").is_file()
    assert (tmp_path / "lineage.fr.html").is_file()
    assert 'href:"lineage.fr.html"' in html.read_text(encoding="utf-8")



def test_manifest_exposes_external_sources_of_raw_columns_only():
    nodes = build_catalog.build_manifest(FIXTURE)["nodes"]
    cols = nodes["raw__pages_views__ga4"]["columns"]
    assert cols["event_name"]["meta"]["externalSources"] == ["ga4_bigquery_export#events.event_name"]
    assert "externalSources" not in cols["meta_loaded_at"]["meta"]
    assert "externalSources" not in nodes["core__orders"]["columns"]["customer_key"]["meta"]


def test_trace_header_shows_declared_and_highest_upstream_classification(tmp_path):
    g = _graph(
        {"raw__x": ["cost", "cur", "nested"], "core__a": ["spend"], "core__copy": ["spend_copy"], "mart": ["total"]},
        [("raw__x", "cost", "core__a", "spend"), ("raw__x", "cur", "core__a", "spend"),
         ("raw__x", "nested", "core__a", "spend"), ("core__a", "spend", "core__copy", "spend_copy"),
         ("core__copy", "spend_copy", "mart", "total")],
    )
    cols = {c: n["columns"] for c, n in g["nodes"].items()}
    g["nodes"]["raw__x"]["nodeType"] = "source"
    for name in ("cost", "cur"):
        cols["raw__x"][name] = {"meta": {"transformLogic": "map", "externalSources": [f"ads_api#campaign.{name}"]}}
    cols["raw__x"]["cost"]["meta"]["classification"] = "C1"
    cols["raw__x"]["cur"]["meta"]["classification"] = "C3"
    cols["raw__x"]["cur"]["tags"] = ["pii"]
    cols["raw__x"]["nested"] = {}  # champ imbrique : aucune source externe, aucune classification
    cols["core__a"]["spend"] = {"meta": {"transformLogic": "transform", "transformDescription": "Conversion en euros.",
                                         "transformExpression": "core_sql_here", "classification": "C2"}}
    cols["core__copy"]["spend_copy"] = _col("map", "Copie.")
    cols["mart"]["total"] = {"meta": {"transformLogic": "transform", "transformDescription": "Somme.",
                                      "transformExpression": "mart_sql_here", "classification": "C1"}}
    t = _trace(tmp_path, g, "mart", "total")
    head = t[t.index('class="cp-head"'):t.index('<div class="cp-deep"')]
    assert head.index("Declared: ") < head.index("Highest upstream: ")
    assert 'Highest upstream: <span class="cp-badge hi">C3' in head
    assert 'class="cp-summary"' not in t, "plus de bloc sous l'arbre"
    assert '<span class="cp-t"><span class="cp-badge ">C1' in t, "la liste affiche la classification"


def test_trace_column_without_upstream_says_it_once(tmp_path):
    g = _graph({"raw__x": ["nested"]}, [])
    g["nodes"]["raw__x"]["nodeType"] = "source"
    g["nodes"]["raw__x"]["columns"]["nested"] = {}
    t = _trace(tmp_path, g, "raw__x", "nested")
    assert "No upstream lineage declared" in t


def test_trace_always_shows_the_source_system(tmp_path):
    g = _graph({"raw__x": ["a"], "mart": ["k"]}, [("raw__x", "a", "mart", "k")])
    g["nodes"]["raw__x"]["columns"]["a"] = {"meta": {"externalSources": ["sys_api#o.a"]}}
    t = _trace(tmp_path, g, "mart", "k")
    assert "data-cp-expert" in t and "Data engineer mode" in t
    assert '<div class="cp-ext">sys_api#o.a</div>' in t and 'cp-expert-only"><div class="cp-ext' not in t


def test_sidebar_filter_matches_columns_and_folders(tmp_path):
    node_bin = shutil.which("node")
    if not node_bin:
        pytest.skip("node est necessaire pour executer le JS du catalogue")
    script = tmp_path / "filter.js"
    script.write_text("""
global.window = {}; global.document = { addEventListener() {} }; global.navigator = {};
eval(require("fs").readFileSync(process.argv[2], "utf8"));
window.colibriData = { nodes: { kpis: { path: "contracts/customer/sales/kpis.odcs.yaml", columns: { Email_Hash: {} } } } };
process.stdout.write(JSON.stringify(["email", "sales", "contracts", "odcs", "zzz"].map(function (q) { return window.cpFilterMatch("kpis", q); })));
""", encoding="utf-8")
    out = subprocess.run([node_bin, str(script), str(ASSETS / "column_info.js")], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    assert json.loads(out.stdout) == [True, True, False, False, False]


def test_trace_shows_no_sql_outside_data_engineer_mode(tmp_path):
    g = _graph({"core__a": ["k"], "mart": ["k"]}, [("core__a", "k", "mart", "k")])
    for c in ("core__a", "mart"):
        g["nodes"][c]["columns"]["k"]["meta"]["transformExpression"] = f"sql_{c}"
    t = _trace(tmp_path, g, "mart", "k")
    blocks = t.count('<div class="cp-sql">')
    assert blocks == 1, "detail de l'arbre"
    assert t.count('<div class="cp-expert-only"><div class="cp-sql">') == blocks


def test_trace_shows_owner_and_tree_size(tmp_path):
    g = _graph({"raw__x": ["a"], "core__a": ["k"], "mart": ["k"]},
               [("raw__x", "a", "core__a", "k"), ("core__a", "k", "mart", "k")])
    g["nodes"]["raw__x"]["nodeType"] = "source"
    g["nodes"]["core__a"]["meta"] = {"team": "team-core", "support": [{"url": "mailto:core@x.example"}]}
    t = _trace(tmp_path, g, "core__a", "k")
    assert "Owner: <b>team-core</b> core@x.example" in t
    assert "Lineage tree · 1 upstream column, 1 raw" in t


def test_trace_tree_names_the_table_of_every_column(tmp_path):
    g = _graph({"raw__x": ["a"], "mart": ["k"]}, [("raw__x", "a", "mart", "k")])
    g["nodes"]["raw__x"]["relationName"] = "proj.raw.x"
    g["nodes"]["mart"]["relationName"] = "proj.customer.mart_table"
    t = _trace(tmp_path, g, "mart", "k")
    deep = t[t.index('<div class="cp-deep"'):]
    assert '<span class="cp-tname">raw.x</span>' in deep, "table de l'entree"
    assert '<span class="cp-tname">customer.mart_table</span>' in deep, "table de la colonne choisie"
    assert '<div class="cp-dtitle">mart.k</div><div class="cp-from">proj.customer.mart_table</div>' in deep


def test_quality_check_sql_is_visible_outside_data_engineer_mode(tmp_path):
    node_bin = shutil.which("node")
    if not node_bin:
        pytest.skip("node est necessaire pour executer le JS du catalogue")
    script = tmp_path / "checks.js"
    script.write_text("""
global.window = {}; global.document = { addEventListener() {} }; global.navigator = {};
eval(require("fs").readFileSync(process.argv[2], "utf8"));
process.stdout.write(window.cpModelTestsHtml([{ name: "sql", kwargs: { query: "SELECT 1" } }]));
""", encoding="utf-8")
    out = subprocess.run([node_bin, str(script), str(ASSETS / "column_info.js")], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    assert 'class="cp-sql"' in out.stdout and "cp-expert-only" not in out.stdout

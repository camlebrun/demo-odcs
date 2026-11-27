"""Tests du generateur de catalogue (JSON consomme par dbt-colibri)."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

import build_catalog

FIXTURE = Path(__file__).parent / "fixtures" / "valid" / "mini_repo"
ASSETS = Path(build_catalog.__file__).parent / "catalog_assets"

# Execute catalog_assets/column_info.js hors navigateur : window/document factices, manifeste
# injecte comme dans l'index.html (metadata, nodes, lineage.edges, tree).
HARNESS = """
const fs = require("fs");
const [asset, manifestPath, model, column, clickModel] = process.argv.slice(2);
global.window = {};
global.document = { documentElement: { classList: { toggle() {} } }, addEventListener() {} };
global.navigator = {};
eval(fs.readFileSync(asset, "utf8"));
const src = JSON.parse(fs.readFileSync(manifestPath, "utf8"));
window.colibriData = { metadata: src.metadata, nodes: src.nodes, lineage: { edges: src.lineage.edges }, tree: src.tree };
if (column) window.cpTraceColumnSet(clickModel || model, column);
process.stdout.write(window.cpTraceTabHtml(model === "" ? null : model));
"""


def _trace(
    tmp_path, manifest: dict, model: str, column: str | None = None, click_model: str | None = None
) -> str:
    """Rend l'onglet Trace d'un contrat avec node (le JS du catalogue n'est pas reimplemente en Python).
    `model=""` simule un rendu React dont l'etat contrat est absent (vue lineage) ; `column` simule
    la colonne cliquee dans la liste des colonnes du panneau du contrat, `click_model` le contrat
    de ce clic quand il differe de l'etat React."""
    node = shutil.which("node")
    if not node:
        pytest.skip("node est necessaire pour executer le JS du catalogue")
    harness = tmp_path / "trace.js"
    harness.write_text(HARNESS, encoding="utf-8")
    data = tmp_path / "manifest.json"
    data.write_text(json.dumps(manifest), encoding="utf-8")
    args = [node, str(harness), str(ASSETS / "column_info.js"), str(data), model]
    if column:
        args += [column, click_model or model]
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
    assert all(f in html for f in ("cpColumnHtml", "cpColumnTabHtml", "cpNodeHtml", "cpToggleExpert", "cpModelTestsHtml", "cpLoadStrategy", "cpObjectType", "cpTraceTabHtml", "cpTraceColumnSet", 'id:"trace",label:"Trace",icon:cpTraceIcon', 'cpTraceIcon=pi("route"', 'id:"cp-trace-panel"', "data-cp-col", "cp-trace-wrap bg-background", ".cp-trace-wrap{pointer-events:auto}"))
    assert "data-sidebar-column]{" not in html, "plus de contournement CSS sur le panneau natif"
    assert 'children:"Source trace"' not in html and "cp-trace-toggle" not in html, "l'ancien bouton Source trace est retire"


def test_trace_tab_lists_columns_and_follows_the_selected_one(tmp_path):
    """L'onglet Trace rend sa propre liste de colonnes et la chaine de la colonne choisie."""
    manifest = build_catalog.build_manifest(FIXTURE)
    hint = _trace(tmp_path, manifest, "kpis_monthly")
    assert "Source trace · kpis_monthly" in hint
    assert 'data-cp-col="customer_key"' in hint and "Select a column" in hint
    assert "cp-result" not in hint
    trace = _trace(tmp_path, manifest, "kpis_monthly", "customer_key")
    assert 'class="cp-colbtn cp-on" data-cp-model="kpis_monthly" data-cp-col="customer_key"' in trace
    # resultat en tete, puis la chaine remontee jusqu'aux raw, en dernier
    assert trace.index("cp-result") < trace.index('data-cp-layer="core"') < trace.index('data-cp-layer="raw"')
    for text in ("Recopie du champ email", "Alimente customer_key", "from core__orders#customer_key", "TO_HEX"):
        assert text in trace, text


def test_trace_tab_collapses_copies_and_orders_contracts_by_dependency(tmp_path):
    def col(logic=None, desc=None):
        return {"meta": {k: v for k, v in (("transformLogic", logic), ("transformDescription", desc)) if v}}

    def node(i, kind, **cols):
        return {"id": i, "nodeType": kind, "columns": cols}

    nodes = {
        "raw__a": node("raw__a", "source", x=col("map", "Copie x."), y=col("map", "Copie y."), z=col()),
        "core__first": node("core__first", "model", k=col("transform", "Premier calcul.")),
        "core__second": node("core__second", "model", k=col("transform", "Second calcul.")),
        "mart": node("mart", "model", k=col("transform", "Resultat.")),
    }
    pairs = [("raw__a", "x", "core__first"), ("raw__a", "y", "core__first"), ("raw__a", "z", "core__first"),
             ("core__first", "k", "core__second"), ("core__second", "k", "mart"), ("core__first", "k", "mart")]
    edges = [{"source": s, "sourceColumn": c, "target": t, "targetColumn": "k"} for s, c, t in pairs]
    trace = _trace(tmp_path, {"nodes": nodes, "lineage": {"edges": edges}}, "mart", "k")
    assert "<summary><b>raw__a</b> · 2 copied columns · 1 undocumented</summary>" in trace
    assert "<details" in trace and "<details open" not in trace
    assert trace.index("<b>core__second</b>") < trace.index("<b>core__first</b>") < trace.index("<b>raw__a</b>")
    assert "from raw__a#x, raw__a#y, raw__a#z" in trace, "les etapes amont affichent leurs entrees"
    assert "3 transformations · 4 contracts" in trace


def test_trace_tab_survives_a_stale_react_model_state(tmp_path):
    """Reproduit le bug vu en ligne : la carte de colonnes de la vue lineage garde son etat interne,
    le rendu React du panneau Trace ne connait pas le contrat (l = null). Le panneau retombe sur le
    dernier contrat clique, et le clic met a jour le panneau sans re-rendu React."""
    manifest = build_catalog.build_manifest(FIXTURE)
    empty = _trace(tmp_path, manifest, "")
    assert "Select a contract to see its source trace." in empty
    stale = _trace(tmp_path, manifest, "", "customer_key", click_model="kpis_monthly")
    assert "Source trace · kpis_monthly" in stale
    assert "Alimente customer_key" in stale and "TO_HEX" in stale


def test_trace_tab_on_a_raw_contract_says_its_sources_are_external(tmp_path):
    trace = _trace(tmp_path, build_catalog.build_manifest(FIXTURE), "raw__orders__shopify")
    assert "Raw contract: no upstream in the catalog" in trace


def test_trace_tab_reports_undocumented_step_and_ignores_cycles(tmp_path):
    """Qualite variable : une colonne amont sans transformation est signalee, un cycle ne boucle pas."""
    nodes = {
        "raw__orders__shopify": {"id": "raw__orders__shopify", "nodeType": "source", "columns": {"id": {}}},
        "core__orders": {"id": "core__orders", "nodeType": "model", "columns": {"order_id": {"meta": {"transformLogic": "map"}}}},
        "kpis_monthly": {
            "id": "kpis_monthly",
            "nodeType": "model",
            "columns": {"order_id": {"meta": {"transformLogic": "map", "transformDescription": "Copie de order_id."}}},
        },
    }
    edges = [
        {"id": 1, "source": "core__orders", "target": "kpis_monthly", "sourceColumn": "order_id", "targetColumn": "order_id"},
        {"id": 2, "source": "raw__orders__shopify", "target": "core__orders", "sourceColumn": "id", "targetColumn": "order_id"},
        {"id": 3, "source": "raw__orders__shopify", "target": "core__orders", "sourceColumn": "id", "targetColumn": "order_id"},
        # arete de retour : un contrat amont qui depend de lui-meme (cycle)
        {"id": 4, "source": "kpis_monthly", "target": "core__orders", "sourceColumn": "order_id", "targetColumn": "order_id"},
    ]
    trace = _trace(tmp_path, {"nodes": nodes, "lineage": {"edges": edges}}, "kpis_monthly", "order_id")
    assert trace.count("<b>raw__orders__shopify</b>") == 1, "une colonne amont n'est listee qu'une fois"
    assert trace.count("<b>core__orders</b>") == 1
    assert "Transformation not documented" in trace
    assert "Copie de order_id." in trace


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
    try { window.cpTraceColumnSet(id, col); window.cpTraceTabHtml(id); window.cpTraceTabHtml(null); } catch (e) { errors.push("cpTraceTabHtml " + id + "." + col + " -> " + e.message); }
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

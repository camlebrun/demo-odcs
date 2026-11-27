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
    assert all(f in html for f in ("cpColumnHtml", "cpColumnTabHtml", "cpNodeHtml", "cpToggleExpert", "cpModelTestsHtml", "cpLoadStrategy", "cpObjectType", "cpTraceTabHtml", "cpTraceColumnSet", 'id:"trace",label:"Trace",icon:cpTraceIcon', 'cpTraceIcon=pi("route"', 'id:"cp-trace-panel"', "data-cp-col", "cp-trace-wrap bg-background", ".cp-trace-wrap{pointer-events:auto}"))
    assert "data-sidebar-column]{" not in html, "plus de contournement CSS sur le panneau natif"
    assert 'children:"Source trace"' not in html and "cp-trace-toggle" not in html, "l'ancien bouton Source trace est retire"


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
    assert "shopify_admin_api#Order.email" in t
    assert "<details open" in t and 'class="cp-detail"' in t
    assert "TO_HEX" in t.split('<details class="cp-deep">')[0], "le SQL d'une etape amont est affiche"
    assert "TO_HEX" in _trace(tmp_path, m, "kpis_monthly", "customer_key", node=("core__orders", "customer_key"))


def test_trace_tree_on_a_raw_contract_shows_the_external_system(tmp_path):
    t = _trace(tmp_path, build_catalog.build_manifest(FIXTURE), "raw__pages_views__ga4", "event_name")
    assert "ga4_bigquery_export#events.event_name" in t
    assert "Raw contract: no upstream" not in t


def test_trace_tree_shows_a_shared_column_once_and_survives_cycles(tmp_path):
    g = _graph(
        {"raw__x": ["k"], "a": ["k"], "b": ["k"], "mart": ["k"]},
        [("a", "k", "mart", "k"), ("b", "k", "mart", "k"), ("raw__x", "k", "a", "k"),
         ("raw__x", "k", "b", "k"), ("mart", "k", "a", "k")],
    )
    g["nodes"]["raw__x"]["columns"]["k"] = {"meta": {"externalSources": ["sys#o.k"]}}
    t = _trace(tmp_path, g, "mart", "k")
    assert t.count("shown above") == 2  # raw__x sous b, et le retour sur mart
    assert t.count('class="cp-ext"') == 1
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


def test_trace_summary_lists_changes_from_sources_to_result_with_tree_closed(tmp_path):
    g = _graph(
        {"raw__x": ["k"], "core__a": ["k"], "core__b": ["k"], "mart": ["k"]},
        [("core__a", "k", "mart", "k"), ("core__b", "k", "mart", "k"), ("raw__x", "k", "core__a", "k"),
         ("core__a", "k", "core__b", "k")],
    )
    cols = {c: n["columns"] for c, n in g["nodes"].items()}
    cols["raw__x"]["k"] = {"meta": {"transformLogic": "map", "transformDescription": "Recopie brute.",
                                    "externalSources": ["sys_api#o.k", "sys_api#o.j"]}}
    cols["core__a"]["k"] = _col("transform", "Etape A.")
    cols["core__b"]["k"] = _col("transform", "Etape B.")
    cols["mart"]["k"] = _col("transform", "Resultat final.")
    t = _trace(tmp_path, g, "mart", "k")
    summary = t[t.index('class="cp-summary"'):t.index('<details class="cp-deep">')]
    assert summary.index("Resultat final.") < summary.index("Etape B.") < summary.index("Etape A."), \
        "resultat en haut, puis du plus proche au plus lointain"
    assert summary.count("Etape A.") == 1, "une colonne partagee n'est resumee qu'une fois"
    assert "Recopie brute." not in summary, "les recopies sont omises du resume"
    assert '<details class="cp-deep" open' not in t and 'class="cp-tree"' in t
    assert '<details class="cp-deep" open>' in _trace(tmp_path, g, "mart", "k", node=("core__a", "k")), \
        "un re-rendu apres un clic dans l'arbre ne referme pas la vue detaillee"


def test_trace_summary_reports_undocumented_steps_and_plain_copies(tmp_path):
    g = _graph({"src": ["x"], "mart": ["k"]}, [("src", "x", "mart", "k")])
    g["nodes"]["src"]["columns"]["x"] = {}
    g["nodes"]["mart"]["columns"]["k"] = _col("map", "Copie de x.")
    t = _trace(tmp_path, g, "mart", "k")
    assert "No transformation declared: plain copies only." in t
    assert "1 step not documented" in t


def test_trace_summary_shows_classification_and_sources_by_sensitivity(tmp_path):
    """Classification declaree et la plus haute en amont ; champs sources les plus sensibles d'abord, C1 replies."""
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
    s = t[t.index('class="cp-summary"'):t.index('<details class="cp-deep">')]
    order = [s.index(x) for x in ("Declared: ", "Highest upstream: ", "Somme.", "mart_sql_here", ">Sources<", ">Transformations<", "Conversion en euros.")]
    assert order == sorted(order)
    assert 'Highest upstream: <span class="cp-badge hi">C3' in s
    sources = s.split(">Sources<")[1].split(">Transformations<")[0]
    visible, folded = sources.split("<summary>C1 and lower · 1 field</summary>")
    assert "C3 · pii" in visible and "<b>ads_api</b> campaign.cur" in visible
    assert "<b>raw__x</b> nested" in visible and "unclassified" in visible, "sans classification : jamais replie"
    assert "campaign.cost" in folded and "campaign.cost" not in visible
    assert ">core__copy<" not in s and "<div>core__copy: spend_copy</div>" in s, "entree declaree, pas une etape"
    assert "core_sql_here" in s and "Step inputs" not in s
    assert '<span class="cp-t"><span class="cp-badge ">C1' in t, "la liste affiche la classification"


def test_trace_steps_show_the_table_id(tmp_path):
    g = _graph({"core__a": ["k"], "core__multi": ["obj.k"], "mart": ["k"]},
               [("core__a", "k", "mart", "k"), ("core__multi", "obj.k", "mart", "k")])
    g["nodes"]["core__a"]["relationName"] = "proj.core.a"
    g["nodes"]["core__multi"]["relationName"] = "proj.core.{obj,other}"
    t = _trace(tmp_path, g, "mart", "k")
    steps = t.split(">Transformations<")[1].split('<details class="cp-deep">')[0]
    assert ">proj.core.a</div>" in steps
    assert ">proj.core.obj</div>" in steps and '<span class="cp-hopcol">k</span>' in steps, "contrat a plusieurs tables"
    assert "core__a" not in steps


def test_trace_shows_table_queries_with_column_lines_highlighted(tmp_path):
    g = _graph({"core__a": ["flag"], "mart": ["is_ok"]}, [("core__a", "flag", "mart", "is_ok")])
    g["nodes"]["mart"]["columns"]["is_ok"]["meta"]["transformExpression"] = "IFNULL(latest.opted, FALSE)"
    g["nodes"]["mart"]["meta"] = {"customProperties": {"transformInputs": "SELECT a\nFROM t\nWHERE latest.opted"}}
    g["nodes"]["core__a"]["meta"] = {"customProperties": {"transformInputs": "-- regle <b>\nSELECT x AS opted\nFROM raw"}}
    t = _trace(tmp_path, g, "mart", "is_ok")
    block = t[t.index('class="cp-summary"'):t.index('<details class="cp-deep">')]
    assert block.count('<details class="cp-acc cp-query"><summary>Full table SQL</summary>') == 1, "un seul bloc, replie"
    assert block.index(">Transformations<") < block.index("Full table SQL") < block.index(">mart</span>", block.index("Full table SQL")) < block.index(">core__a</span>", block.index("Full table SQL"))
    block = block[block.index("Full table SQL"):]
    hits = block.split('class="cp-line cp-hit"')[1:]
    assert len(hits) == 2, "latest/opted ; ni IFNULL ni FALSE"
    assert block.count('class="cp-line') == 6, "une ligne rendue par ligne de requete"
    assert "regle &lt;b&gt;" in block and "<b>\n" not in block
    assert "Full table SQL" not in _trace(tmp_path, build_catalog.build_manifest(FIXTURE), "kpis_monthly", "customer_key")


def test_trace_shows_column_description_first_and_hides_trivial_sql(tmp_path):
    g = _graph({"core__a": ["flag"], "mart": ["is_ok"]}, [("core__a", "flag", "mart", "is_ok")])
    top = g["nodes"]["mart"]["columns"]["is_ok"]
    top["description"] = "Regle metier. Toujours vrai ici."
    top["meta"]["transformExpression"] = "latest.opted"
    step = g["nodes"]["core__a"]["columns"]["flag"]
    step["description"] = "Description de l'etape."
    step["meta"]["transformExpression"] = "flag"
    t = _trace(tmp_path, g, "mart", "is_ok")
    summary = t[t.index('class="cp-summary"'):t.index('<details class="cp-deep">')]
    header = summary.split(">Transformations<")[0]
    assert header.index("Toujours vrai ici.") < header.index(">transformDescription<") < header.index("Calcul is_ok.") < header.index(">transformExpression<") < header.index("latest")
    assert "Calcul flag." in summary and "Description de l" not in summary, "une etape dit comment la colonne est calculee"
    assert summary.count("Transformation SQL") == 2, "affiche meme quand il reprend le nom de la colonne"
    del top["description"]
    assert "Calcul is_ok." in _trace(tmp_path, g, "mart", "is_ok"), "repli sur transformDescription"


def test_trace_steps_list_their_source_objects(tmp_path):
    g = _graph({"raw__x": ["a", "b"], "core__a": ["k"], "mart": ["k"]},
               [("raw__x", "a", "core__a", "k"), ("raw__x", "b", "core__a", "k"), ("core__a", "k", "mart", "k")])
    g["nodes"]["raw__x"]["columns"] = {"a": _col("map"), "b": _col("map")}
    g["nodes"]["raw__x"]["relationName"] = "proj.raw.x"
    g["nodes"]["core__a"]["relationName"] = "proj.core.a"
    t = _trace(tmp_path, g, "mart", "k")
    summary = t[t.index('class="cp-summary"'):t.index('<details class="cp-deep">')]
    header, steps = summary.split(">Transformations<")
    assert '<div class="cp-fname">transformSourceObjects</div><div class="cp-from"><div>proj.core.a: k</div></div>' in header
    assert '<div class="cp-from"><div>proj.raw.x: a, b</div></div>' in steps


def test_trace_shows_sources_unfolded_when_none_is_sensitive(tmp_path):
    g = _graph({"raw__x": ["a"], "mart": ["k"]}, [("raw__x", "a", "mart", "k")])
    g["nodes"]["raw__x"]["columns"]["a"] = {"meta": {"classification": "C1", "externalSources": ["sys#o.a"]}}
    t = _trace(tmp_path, g, "mart", "k")
    sources = t.split(">Sources<")[1].split(">Transformations<")[0].split('<details class="cp-acc cp-query">')[0]
    assert "o.a" in sources and "C1 and lower" not in sources


def test_trace_column_without_upstream_says_it_once(tmp_path):
    g = _graph({"raw__x": ["nested"]}, [])
    g["nodes"]["raw__x"]["nodeType"] = "source"
    g["nodes"]["raw__x"]["columns"]["nested"] = {}
    t = _trace(tmp_path, g, "raw__x", "nested").split('<details class="cp-deep">')[0]
    assert "No upstream lineage declared" in t
    assert "plain copies only" not in t and "step not documented" not in t and ">Sources<" not in t


def test_trace_shows_the_same_three_fields_for_every_column_and_step(tmp_path):
    g = _graph({"core__a": ["k"], "mart": ["k", "cur"]}, [("core__a", "k", "mart", "k")])
    g["nodes"]["mart"]["columns"]["cur"] = {"meta": {"transformLogic": "create", "transformDescription": "Constante."}}
    for col, blocks in (("k", 2), ("cur", 1)):
        summary = _trace(tmp_path, g, "mart", col).split('<details class="cp-deep">')[0]
        for name in ("transformDescription", "transformExpression", "transformSourceObjects"):
            assert summary.count(f'>{name}<') == blocks, (col, name)
    assert summary.count("not declared") == 1 and ">none<" in summary and ">create<" in summary

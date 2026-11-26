"""Tests du generateur de catalogue (JSON consomme par dbt-colibri)."""
from pathlib import Path

import pytest

import build_catalog

FIXTURE = Path(__file__).parent / "fixtures" / "valid" / "mini_repo"


def test_manifest_has_one_node_per_contract():
    m = build_catalog.build_manifest(FIXTURE)
    assert set(m["nodes"]) == {
        "raw__orders__shopify",
        "raw__pages_views__ga4",
        "kpis_monthly",
    }
    assert m["metadata"]["total_model_count"] == 3


def test_column_edges_follow_transform_source_objects():
    m = build_catalog.build_manifest(FIXTURE)
    col_edges = [e for e in m["lineage"]["edges"] if e["targetColumn"]]
    assert col_edges, "le customer du fixture declare du lineage"
    for e in col_edges:
        assert e["target"] == "kpis_monthly"
        assert e["sourceColumn"] in m["nodes"][e["source"]]["columns"]
        assert e["targetColumn"] in m["nodes"][e["target"]]["columns"]
        assert m["nodes"][e["target"]]["columns"][e["targetColumn"]]["hasLineage"] is True
    # une arete de contrat a contrat (sans colonne) par source referencee
    contract_edges = {(e["source"], e["target"]) for e in m["lineage"]["edges"] if not e["targetColumn"]}
    assert {s for s, _ in contract_edges} <= {"raw__orders__shopify", "raw__pages_views__ga4"}


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
    assert all(f in html for f in ("cpColumnHtml", "cpColumnTabHtml", "cpNodeHtml", "cpToggleExpert", "cpModelTestsHtml", "cpLoadStrategy", "cpObjectType"))


def test_render_writes_lineage_page_linked_from_dashboard(tmp_path):
    pytest.importorskip("dbt_colibri")
    html = build_catalog.render_html(build_catalog.build_manifest(Path(build_catalog.REPO_ROOT)), tmp_path)
    assert (tmp_path / "lineage.html").is_file()
    assert (tmp_path / "lineage.fr.html").is_file()
    assert 'href="lineage.html"' in html.read_text(encoding="utf-8")

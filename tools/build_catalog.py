"""Genere le catalogue de donnees a partir des data contracts ODCS.

Le catalogue est un dashboard statique dbt-colibri (MIT, https://github.com/b-ned/dbt-colibri).
Colibri lit normalement un manifest dbt et parse le SQL. Ici il n'y a pas de dbt : le lineage
est deja declare par property dans les contrats (transformSourceObjects). On produit donc
directement le JSON consomme par l'interface (`colibri-manifest.json`), puis on l'injecte
dans le `index.html` de colibri avec sa fonction publique `inject_data_into_html`.

Sorties (par defaut dist/catalog/) :
  colibri-manifest.json   lineage complet (noeuds, aretes colonne a colonne, parents, enfants)
  index.html              dashboard autonome (telemetrie colibri desactivee)

Usage : python tools/build_catalog.py [--root .] [--out dist/catalog] [--json-only]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from catalog_template import TemplateMismatch, patch_template
from common import REPO_ROOT
from validate_lineage import all_props, custom_prop, load_contracts, schema_objects, sources_of

DEFAULT_OUT = REPO_ROOT / "dist" / "catalog"
SCHEMA_VERSION = "odcs-v3.2.0"
LINEAGE_TYPE = {"map": "pass-through", "transform": "transformation"}


def _text(value) -> str | None:
    if isinstance(value, dict):
        parts = [f"**{k}** : {v}" for k, v in value.items() if v]
        return "\n\n".join(parts) or None
    return str(value) if value else None


def _server(data: dict) -> dict:
    servers = data.get("servers")
    return servers[0] if isinstance(servers, list) and servers and isinstance(servers[0], dict) else {}


def _tests(quality, prefix: str) -> list[dict]:
    """Traduit les regles `quality` ODCS vers le format `tests` de l'interface colibri."""
    out = []
    for i, rule in enumerate(quality if isinstance(quality, list) else []):
        if not isinstance(rule, dict):
            continue
        name = rule.get("metric") or rule.get("name") or rule.get("type") or "quality"
        out.append(
            {
                "unique_id": f"{prefix}.{name}.{i}",
                "name": str(name),
                "namespace": "odcs",
                "config": {"severity": rule.get("severity"), "warn_if": None, "error_if": None},
                "kwargs": {k: v for k, v in rule.items() if k not in ("severity",)},
                "compiled_code": None,  # jamais de code compile dans le catalogue ; la requete reste dans kwargs.query
            }
        )
    return out


def _parse_ref(ref: str) -> tuple[str, str, str] | None:
    """`<contract_id>#<objet>.<chemin>` -> (contract_id, objet, chemin)."""
    if not isinstance(ref, str) or "#" not in ref:
        return None
    cid, rest = ref.split("#", 1)
    obj, _, path = rest.partition(".")
    return cid, obj, path


def build_manifest(root: Path) -> dict:
    contracts, errors = load_contracts(root)
    if errors:
        raise SystemExit("Contrats illisibles :\n" + "\n".join(str(e) for e in errors))
    multi = {c.cid: len(schema_objects(c)) > 1 for c in contracts}

    def col(cid: str, obj: str, path: str) -> str:
        return f"{obj}.{path}" if multi.get(cid) else path

    nodes: dict[str, dict] = {}
    parents: dict[str, dict[str, list]] = {}
    children: dict[str, dict[str, list]] = {}
    edges: list[dict] = []

    for c in sorted(contracts, key=lambda x: x.cid or ""):
        d = c.data
        srv = _server(d)
        desc = d.get("description")
        columns: dict[str, dict] = {}
        model_tests: list[dict] = []
        for obj in schema_objects(c):
            oname = str(obj.get("name"))
            model_tests += _tests(obj.get("quality"), f"{c.cid}.{oname}")
        for prop in all_props(c):
            oname, _, path = prop.path.partition(".")
            node = prop.node
            name = col(c.cid, oname, path)
            tags = list(node.get("tags") or [])
            if node.get("classification"):
                tags.append(f"classification:{node['classification']}")
            meta = {
                k: v
                for k, v in {
                    "classification": node.get("classification"),
                    "required": node.get("required"),
                    "unique": node.get("unique"),
                    "primaryKey": node.get("primaryKey"),
                    "primaryKeyPosition": node.get("primaryKeyPosition"),
                    "transformLogic": node.get("transformLogic"),
                    "transformDescription": node.get("transformDescription"),
                    "transformExpression": custom_prop(node, "transformExpression"),
                }.items()
                if v is not None
            }
            entry = {
                "columnName": name,
                "hasLineage": False,
                "dataType": node.get("physicalType"),
                "contractType": node.get("logicalType"),
                "description": node.get("description"),
            }
            if tags:
                entry["tags"] = tags
            if meta:
                entry["meta"] = meta
            tests = _tests(node.get("quality"), f"{c.cid}.{path}")
            if tests:
                entry["tests"] = tests
            columns[name] = {k: v for k, v in entry.items() if v is not None}

        objs = schema_objects(c) or [{}]
        tables = [o.get("physicalName") or o.get("name") for o in objs]
        table = tables[0] if len(tables) == 1 else "{" + ",".join(str(t) for t in tables) + "}"
        node_meta = {
            "contractId": c.cid,
            "contractVersion": d.get("version"),
            "contractStatus": d.get("status"),
            "domain": d.get("domain"),
            "dataProduct": d.get("dataProduct"),
            "team": (d.get("team") or {}).get("name") if isinstance(d.get("team"), dict) else None,
            "support": d.get("support"),
            "slaProperties": d.get("slaProperties"),
            "apiVersion": d.get("apiVersion"),
            "descriptionParts": desc if isinstance(desc, dict) else None,
            "customProperties": {
                cp["property"]: cp.get("value")
                for cp in d.get("customProperties") or []
                if isinstance(cp, dict) and "property" in cp
            }
            or None,
        }
        nodes[c.cid] = {
            "id": c.cid,
            "name": c.cid,
            "fullName": c.cid,
            "nodeType": "source" if c.layer == "raw" else "model",
            "materialized": "table",
            "modelType": "unknown",
            "database": srv.get("project"),
            "schema": srv.get("dataset"),
            "path": c.rel,
            "description": _text(desc),
            "contractEnforced": True,
            "rawCode": c.path.read_text(encoding="utf-8"),
            "compiledCode": None,
            "refs": [],
            "tags": sorted({*(d.get("tags") or []), f"domain:{d.get('domain')}", f"status:{d.get('status')}"}),
            "columns": columns,
            "relationName": ".".join(x for x in (srv.get("project"), srv.get("dataset"), table) if x) or None,
            "meta": {k: v for k, v in node_meta.items() if v is not None},
        }
        if model_tests:
            nodes[c.cid]["tests"] = model_tests

    # Aretes colonne a colonne (declarees) + aretes de contrat a contrat.
    edge_id = 1
    contract_links: set[tuple[str, str]] = set()
    for c in sorted(contracts, key=lambda x: x.cid or ""):
        for prop in all_props(c):
            node = prop.node
            logic = node.get("transformLogic")
            srcs = sources_of(node)
            if not logic or not srcs:
                continue
            oname, _, path = prop.path.partition(".")
            tgt_col = col(c.cid, oname, path)
            ltype = LINEAGE_TYPE.get(logic, "unknown")
            if logic == "map":
                s = _parse_ref(srcs[0])
                if s and s[2].rsplit(".", 1)[-1] != path.rsplit(".", 1)[-1]:
                    ltype = "rename"
            nodes[c.cid]["columns"][tgt_col]["lineageType"] = ltype if len(srcs) < 2 else "transformation"
            nodes[c.cid]["columns"][tgt_col]["hasLineage"] = True
            for ref in srcs:
                s = _parse_ref(ref)
                if not s or s[0] not in nodes:
                    continue
                scid, sobj, spath = s
                scol = col(scid, sobj, spath)
                if scol in nodes[scid]["columns"]:
                    nodes[scid]["columns"][scol]["hasLineage"] = True
                edges.append(
                    {"id": edge_id, "source": scid, "target": c.cid, "sourceColumn": scol, "targetColumn": tgt_col}
                )
                edge_id += 1
                contract_links.add((scid, c.cid))
                parents.setdefault(c.cid, {}).setdefault(tgt_col, []).append(
                    {"dbt_node": scid, "column": scol, "lineage_type": ltype}
                )
                children.setdefault(scid, {}).setdefault(scol, []).append(
                    {"dbt_node": c.cid, "column": tgt_col, "lineage_type": ltype}
                )
    for scid, tcid in sorted(contract_links):
        edges.append({"id": edge_id, "source": scid, "target": tcid, "sourceColumn": "", "targetColumn": ""})
        edge_id += 1

    # Arbres de navigation : projet BigQuery > dataset > contrats ; et arborescence du repo.
    db_tree: dict[str, dict[str, list[str]]] = {}
    path_tree: dict = {}
    for n in nodes.values():
        db_tree.setdefault(str(n["database"] or "unknown"), {}).setdefault(str(n["schema"] or "unknown"), []).append(n["id"])
        cursor = path_tree
        if n["nodeType"] == "source":
            cursor = path_tree.setdefault("sources", {})
        for seg in Path(n["path"]).parts[1:-1]:  # sans "contracts/" ni le nom de fichier
            cursor = cursor.setdefault(seg, {})
        cursor.setdefault("__items__", []).append(n["id"])
    db_tree = {db: {s: sorted(ids) for s, ids in sorted(schemas.items())} for db, schemas in sorted(db_tree.items())}

    def sort_items(folder: dict) -> dict:
        out = {k: sort_items(v) for k, v in sorted(folder.items()) if k != "__items__"}
        if "__items__" in folder:
            out["__items__"] = sorted(folder["__items__"])
        return out

    fingerprint = hashlib.sha256("|".join(sorted(nodes)).encode()).hexdigest()[:16]
    return {
        "metadata": {
            "colibri_version": _colibri_version(),
            "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
            "adapter_type": "bigquery",
            "dbt_version": None,
            "dbt_schema_version": SCHEMA_VERSION,
            "dbt_invocation_id": None,
            "dbt_project_name": "data-contracts",
            "dbt_project_id": fingerprint,
            "total_model_count": len(contracts),
            "unmaterialized_model_count": 0,
        },
        "nodes": nodes,
        "lineage": {"edges": edges, "parents": parents, "children": children},
        "tree": {"byDatabase": db_tree, "byPath": {"data-contracts": sort_items(path_tree)}},
    }


def _colibri_version() -> str | None:
    try:
        from importlib.metadata import version

        return version("dbt-colibri")
    except Exception:  # noqa: BLE001
        return None


def render_html(manifest: dict, out_dir: Path) -> Path:
    try:
        import dbt_colibri.report.generator as gen
    except ImportError:
        raise SystemExit(
            "dbt-colibri n'est pas installe. Lancer `make install-catalog` "
            "(ou utiliser --json-only pour ne produire que le JSON)."
        )
    stripped = {
        "metadata": manifest["metadata"],
        "nodes": manifest["nodes"],
        "lineage": {"edges": manifest["lineage"]["edges"]},
        "tree": manifest["tree"],
    }
    template = Path(gen.__file__).parent / "index.html"
    html = out_dir / "index.html"
    patched = out_dir / ".template.html"
    try:
        patched.write_text(patch_template(template.read_text(encoding="utf-8")), encoding="utf-8")
    except TemplateMismatch as exc:
        raise SystemExit(f"Template colibri incompatible (version epinglee dans pyproject.toml) : {exc}")
    # La telemetrie (PostHog) de l'interface colibri est toujours desactivee.
    gen.inject_data_into_html(stripped, str(patched), str(html), disable_telemetry=True)
    patched.unlink()
    return html


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", type=Path, default=REPO_ROOT)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--open", action="store_true", help="ouvre le catalogue dans le navigateur")
    ap.add_argument("--json-only", action="store_true", help="ne produit que colibri-manifest.json")
    args = ap.parse_args(argv)

    manifest = build_manifest(args.root)
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "colibri-manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    n_cols = sum(len(n["columns"]) for n in manifest["nodes"].values())
    print(f"OK {manifest['metadata']['total_model_count']} contrats, {n_cols} colonnes, {len(manifest['lineage']['edges'])} aretes -> {args.out}/colibri-manifest.json")
    if not args.json_only:
        page = render_html(manifest, args.out)
        print(f"OK catalogue -> {page}")
        if args.open:
            import webbrowser

            webbrowser.open(page.resolve().as_uri())
    return 0


if __name__ == "__main__":
    sys.exit(main())

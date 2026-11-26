#!/usr/bin/env python3
"""Valide le lineage et les conventions des data contracts (voir docs/conventions.md).

Regles (code dans la sortie) :
  L001 decompte (14 raw dont 4/4/2/2/2 par source, 5 core, 3 customer) ; desactivable avec --no-count
  L002 nommage raw / core / customer, id == name == nom de fichier, dossier source == domaine (raw)
  L003 references transformSourceObjects (contrat, objet, property, chemins imbriques)
  L004 couches : un core lit des raw ou des core ; un customer ne lit que des core
  L005 cycle dans le graphe de references
  L006 lineage raw : chaque champ de premier niveau est `map` depuis 1 champ de la source externe
       (<systeme>#<objet>.<champ>), sauf meta_loaded_at / meta_source_file en `create` sans source
  L007 coherence de transformLogic (map / transform / create) et des sources
  L008 transformLogic et transformDescription presents sur tout champ core et customer
  L009 un contrat customer vit dans contracts/customer/<flux>/ avec <flux> parmi acquisition, audiences, sales
  L010 PII : tag `pii` ET classification `C3`
  L011 map : renommage ou cast trivial uniquement
  L012 customer_key conforme a la regle canonique (un customer reprend la cle d'un core sans la recalculer)
  L013 metadonnees (apiVersion, status, version, domain, servers, team, support)
  L014 documentation et classification des properties
  L015 nommage des properties (snake_case, suffixes _at/_date/_amount/_eur/is_/has_ vs type physique)
  L016 customer_key : classification C2 et tag pseudonymized
  L017 description du contrat (purpose, usage, limitations) et des objets : 350 caracteres maximum (5 lignes)
  L018 objet de schema : physicalType table|view ; customProperties loadStrategy (full_refresh|incremental|append) facultatif,
       incrementalKey (property existante) obligatoire si incremental
  L019 chaque objet d'un contrat core declare au moins une property primaryKey

Code retour 1 s'il y a au moins une erreur.
"""
from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

from common import REPO_ROOT, find_contracts, load_yaml

RAW_COUNTS = {"shopify": 4, "pos": 4, "ga4": 2, "googleads": 2, "metaads": 2}
CORE_COUNT = 5
CUSTOMER_COUNT = 3
SOURCES = tuple(RAW_COUNTS)
FLOWS = ("acquisition", "audiences", "sales")  # flux metier : un sous-dossier de contracts/customer/ par flux
STATUSES = ("proposed", "draft", "active", "deprecated", "retired")
CLASSIFICATIONS = ("C0", "C1", "C2", "C3")  # confidentialite : public, interne, confidentiel, restreint
PII_TAG = "pii"
PII_CLASSIFICATION = "C3"
TECH_FIELDS = ("meta_loaded_at", "meta_source_file")
# Systeme source externe cite dans transformSourceObjects d'un raw : <systeme>#<objet>.<champ>.
RAW_SYSTEMS = {"shopify": "shopify_admin_api", "pos": "pos_export", "ga4": "ga4_bigquery_export", "googleads": "googleads_api", "metaads": "metaads_api"}
DERIVED_LAYERS = ("core", "customer")  # couches calculees : lineage par colonne vers le depot
READS = {"core": ("raw", "core"), "customer": ("core",)}  # L004 : couches lisibles par couche
READS_LABEL = {"core": "des raw ou des core", "customer": "des core"}
LOGICS = ("map", "transform", "create")
OBJECT_TYPES = ("table", "view")
LOAD_STRATEGIES = ("full_refresh", "incremental", "append")
API_VERSION = "v3.2.0"
DESCRIPTION_MAX = 350  # caracteres : 5 lignes dans le catalogue

SNAKE = r"[a-z][a-z0-9]*(?:_[a-z0-9]+)*"
RAW_RE = re.compile(rf"^raw__(?P<table>{SNAKE})__(?P<source>[a-z0-9]+)$")
CUSTOMER_RE = re.compile(rf"^{SNAKE}$")
CORE_RE = re.compile(r"^core__[a-z0-9_]+$")
SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+$")
REF_RE = re.compile(r"^(?P<contract>[^#\s]+)#(?P<obj>[^.\s#]+)\.(?P<path>[^\s#]+)$")

# Regle customer_key (docs/conventions.md, section "customer_key"). {c} = colonne email.
CUSTOMER_KEY_CANONICAL = "IF(NULLIF(TRIM({c}), '') IS NULL, NULL, TO_HEX(SHA256(LOWER(TRIM({c})))))"
_ck_parts = re.sub(r"\s+", "", CUSTOMER_KEY_CANONICAL).split("{c}")
CUSTOMER_KEY_RE = re.compile(
    re.escape(_ck_parts[0])
    + r"(?P<c>[A-Za-z_][\w.]*)"
    + re.escape(_ck_parts[1])
    + r"(?P=c)"
    + re.escape(_ck_parts[2])
    + "$"
)

# map : identifiant (renommage) ou [SAFE_]CAST(identifiant AS type), rien d'autre.
TRIVIAL_MAP_RE = re.compile(
    r"^\s*(?:(?:SAFE_)?CAST\(\s*[A-Za-z_][\w.]*\s+AS\s+[A-Za-z0-9_]+\s*\)|[A-Za-z_][\w.]*)\s*$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Err:
    code: str
    where: str
    message: str

    def __str__(self) -> str:
        return f"[{self.code}] {self.where}: {self.message}"


@dataclass
class Contract:
    path: Path
    rel: str
    data: dict
    layer: str  # raw | core | customer | other
    folder: str  # source pour raw, flux metier pour customer, vide pour core

    @property
    def cid(self):
        return self.data.get("id")


@dataclass
class Prop:
    path: str  # ex. orders.event_params.key
    node: dict
    top: bool  # property de premier niveau d'un objet


def load_contracts(root: Path) -> tuple[list[Contract], list[Err]]:
    contracts, errors = [], []
    for p in find_contracts(root):
        rel = p.relative_to(root).as_posix()
        parts = p.relative_to(root / "contracts").parts
        if len(parts) == 3 and parts[0] == "raw":
            layer, folder = "raw", parts[1]
        elif len(parts) == 3 and parts[0] == "customer":
            layer, folder = "customer", parts[1]
        elif len(parts) == 2 and parts[0] == "core":
            layer, folder = "core", ""
        else:
            layer, folder = "other", ""
        try:
            data = load_yaml(p)
        except Exception as exc:  # noqa: BLE001
            errors.append(Err("L002", rel, f"YAML illisible: {exc}"))
            continue
        if not isinstance(data, dict):
            errors.append(Err("L002", rel, "le contrat doit etre un objet YAML"))
            continue
        contracts.append(Contract(p, rel, data, layer, folder))
    return contracts, errors


def children(node: dict) -> list[dict]:
    """Sous-properties d'une property : object.properties, array.items.properties, map.value.properties."""
    kids = node.get("properties")
    if not isinstance(kids, list):
        items = node.get("items")
        kids = items.get("properties") if isinstance(items, dict) else None
    if not isinstance(kids, list):
        mp = node.get("map")
        value = mp.get("value") if isinstance(mp, dict) else None
        kids = value.get("properties") if isinstance(value, dict) else None
    return [k for k in kids if isinstance(k, dict)] if isinstance(kids, list) else []


def schema_objects(c: Contract) -> list[dict]:
    objs = c.data.get("schema")
    return [o for o in objs if isinstance(o, dict)] if isinstance(objs, list) else []


def walk(props: list, prefix: str, top: bool = True) -> Iterator[Prop]:
    for p in props:
        if not isinstance(p, dict):
            continue
        path = f"{prefix}.{p.get('name', '?')}"
        yield Prop(path, p, top)
        yield from walk(children(p), path, top=False)


def all_props(c: Contract) -> Iterator[Prop]:
    for obj in schema_objects(c):
        yield from walk(obj.get("properties") or [], str(obj.get("name", "?")))


def resolve_path(obj: dict, path: str) -> bool:
    """Vrai si `a.b.c` existe sous l'objet (traverse properties, items.properties, map.value)."""
    level = obj.get("properties") if isinstance(obj.get("properties"), list) else []
    node = obj
    for part in path.split("."):
        match = next((p for p in level if isinstance(p, dict) and p.get("name") == part), None)
        if match is None:
            return False
        node = match
        level = children(node)
    return True


def custom_prop(node: dict, name: str):
    for cp in node.get("customProperties") or []:
        if isinstance(cp, dict) and cp.get("property") == name:
            return cp.get("value")
    return None


def sources_of(node: dict) -> list:
    src = node.get("transformSourceObjects")
    return src if isinstance(src, list) else ([] if src is None else [src])


# ---------------------------------------------------------------- regles


def check_count(contracts: list[Contract]) -> list[Err]:
    errs = []
    raw = [c for c in contracts if c.layer == "raw"]
    cust = [c for c in contracts if c.layer == "customer"]
    if len(raw) != sum(RAW_COUNTS.values()):
        errs.append(Err("L001", "contracts/raw", f"{len(raw)} contrat(s) raw trouve(s), {sum(RAW_COUNTS.values())} attendus"))
    for src, expected in RAW_COUNTS.items():
        n = sum(1 for c in raw if c.folder == src)
        if n != expected:
            errs.append(Err("L001", f"contracts/raw/{src}", f"{n} contrat(s) trouve(s), {expected} attendus"))
    core = [c for c in contracts if c.layer == "core"]
    if len(core) != CORE_COUNT:
        errs.append(Err("L001", "contracts/core", f"{len(core)} contrat(s) core trouve(s), {CORE_COUNT} attendus"))
    if len(cust) != CUSTOMER_COUNT:
        errs.append(Err("L001", "contracts/customer", f"{len(cust)} contrat(s) customer trouve(s), {CUSTOMER_COUNT} attendus"))
    return errs


def check_naming(c: Contract) -> list[Err]:
    errs = []
    stem = c.path.name[: -len(".odcs.yaml")]
    cid, name = c.cid, c.data.get("name")
    if c.layer == "other":
        return [Err("L002", c.rel, "emplacement invalide: attendu contracts/raw/<source>/, contracts/core/ ou contracts/customer/<flux>/")]
    if cid != stem:
        errs.append(Err("L002", c.rel, f"id '{cid}' different du nom de fichier '{stem}'"))
    if name != cid:
        errs.append(Err("L002", c.rel, f"name '{name}' different de id '{cid}'"))
    if not isinstance(cid, str):
        return errs + [Err("L002", c.rel, "id manquant ou non texte")]
    if c.layer == "raw":
        if c.folder not in SOURCES:
            errs.append(Err("L002", c.rel, f"dossier source '{c.folder}' inconnu (attendu: {', '.join(SOURCES)})"))
        m = RAW_RE.match(cid)
        if not m:
            errs.append(Err("L002", c.rel, f"id '{cid}' ne respecte pas raw__<table>__<source>"))
        elif m["source"] != c.folder:
            errs.append(Err("L002", c.rel, f"source '{m['source']}' du nom differente du dossier '{c.folder}'"))
    elif c.layer == "core":
        if not CORE_RE.match(cid):
            errs.append(Err("L002", c.rel, f"id '{cid}' ne respecte pas core__<nom>"))
    else:
        if cid.startswith("raw__"):
            errs.append(Err("L002", c.rel, "un contrat customer ne peut pas porter le prefixe raw__"))
        if not CUSTOMER_RE.match(cid) or "__" in cid:
            errs.append(Err("L002", c.rel, f"id '{cid}' ne respecte pas <objet> en snake_case, sans '__'"))
    return errs


def check_metadata(c: Contract) -> list[Err]:
    errs, d = [], c.data
    if c.layer == "other":
        return errs
    if d.get("apiVersion") != API_VERSION:
        errs.append(Err("L013", c.rel, f"apiVersion '{d.get('apiVersion')}' (attendu {API_VERSION})"))
    if d.get("kind") != "DataContract":
        errs.append(Err("L013", c.rel, f"kind '{d.get('kind')}' (attendu DataContract)"))
    if d.get("status") not in STATUSES:
        errs.append(Err("L013", c.rel, f"status '{d.get('status')}' hors de {', '.join(STATUSES)}"))
    if not isinstance(d.get("version"), str) or not SEMVER_RE.match(d["version"]):
        errs.append(Err("L013", c.rel, f"version '{d.get('version')}' n'est pas du semver MAJOR.MINOR.PATCH"))
    expected_domain = c.folder if c.layer == "raw" else c.layer
    if d.get("domain") != expected_domain:
        errs.append(Err("L013", c.rel, f"domain '{d.get('domain')}' (attendu '{expected_domain}')"))
    expected_dataset = f"raw_{c.folder}" if c.layer == "raw" else c.layer
    servers = d.get("servers") if isinstance(d.get("servers"), list) else []
    bq = [s for s in servers if isinstance(s, dict) and s.get("type") == "bigquery"]
    if not bq or not any(s.get("dataset") == expected_dataset for s in bq):
        errs.append(Err("L013", c.rel, f"servers: serveur bigquery avec dataset '{expected_dataset}' attendu"))
    team = d.get("team")
    if not isinstance(team, dict) or team.get("name") != f"team-{expected_domain}":
        errs.append(Err("L013", c.rel, f"team.name doit valoir 'team-{expected_domain}' (objet Team ODCS)"))
    elif not any(isinstance(m, dict) and m.get("role") == "owner" for m in team.get("members") or []):
        errs.append(Err("L013", c.rel, "team.members doit contenir un membre avec role 'owner'"))
    if not isinstance(d.get("support"), list) or not d.get("support"):
        errs.append(Err("L013", c.rel, "support: liste non vide attendue"))
    return errs


def check_load_strategy(c: Contract) -> list[Err]:
    """L018 : type de l'objet et strategie de chargement (affiches dans le catalogue)."""
    errs = []
    for obj in schema_objects(c):
        where = f"{c.rel} {obj.get('name', '?')}"
        if obj.get("physicalType") not in OBJECT_TYPES:
            errs.append(Err("L018", where, f"physicalType '{obj.get('physicalType')}' hors de {', '.join(OBJECT_TYPES)}"))
        strategy = custom_prop(obj, "loadStrategy")
        if strategy is None:
            continue
        if strategy not in LOAD_STRATEGIES:
            errs.append(Err("L018", where, f"loadStrategy '{strategy}' hors de {', '.join(LOAD_STRATEGIES)}"))
            continue
        key = custom_prop(obj, "incrementalKey")
        names = {p.get("name") for p in obj.get("properties") or [] if isinstance(p, dict)}
        if strategy == "incremental" and key not in names:
            errs.append(Err("L018", where, f"incremental exige customProperties.incrementalKey, une property de l'objet (trouve '{key}')"))
        if strategy != "incremental" and key is not None:
            errs.append(Err("L018", where, "incrementalKey n'a de sens qu'avec loadStrategy incremental"))
    return errs


def check_docs(c: Contract) -> list[Err]:
    errs, d = [], c.data
    if c.layer == "other":
        return errs
    desc = d.get("description")
    if not isinstance(desc, dict) or not str(desc.get("purpose", "")).strip():
        errs.append(Err("L014", c.rel, "description.purpose manquant"))
    for part in ("purpose", "usage", "limitations"):
        text = str(desc.get(part, "")) if isinstance(desc, dict) else ""
        if len(text) > DESCRIPTION_MAX:
            errs.append(Err("L017", c.rel, f"description.{part} : {len(text)} caracteres (maximum {DESCRIPTION_MAX}, soit 5 lignes)"))
    for obj in schema_objects(c):
        if not str(obj.get("description", "")).strip():
            errs.append(Err("L014", f"{c.rel} {obj.get('name')}", "description de l'objet manquante"))
        elif len(str(obj.get("description"))) > DESCRIPTION_MAX:
            errs.append(Err("L017", f"{c.rel} {obj.get('name')}", f"description de l'objet : {len(str(obj.get('description')))} caracteres (maximum {DESCRIPTION_MAX})"))
    for p in all_props(c):
        where = f"{c.rel} {p.path}"
        if not str(p.node.get("description", "")).strip():
            errs.append(Err("L014", where, "description manquante"))
        cls = p.node.get("classification")
        if cls is None:
            if p.top:
                errs.append(Err("L014", where, "classification manquante"))
        elif cls not in CLASSIFICATIONS:
            errs.append(Err("L014", where, f"classification '{cls}' hors de {', '.join(CLASSIFICATIONS)}"))
    return errs


PROP_NAME_RE = re.compile(r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)*$")
# Suffixes ou prefixes de nom customer imposant un type physique BigQuery (docs/conventions.md, section 3).
CUSTOMER_TYPE_RULES = (
    ("suffix", "_at", ("TIMESTAMP",)),
    ("suffix", "_date", ("DATE",)),
    ("suffix", "_amount", ("NUMERIC",)),
    ("suffix", "_eur", ("NUMERIC",)),
    ("prefix", "is_", ("BOOL",)),
    ("prefix", "has_", ("BOOL",)),
)


def check_property_names(c: Contract) -> list[Err]:
    errs: list[Err] = []
    if c.layer == "other":
        return errs
    for p in all_props(c):
        name = str(p.node.get("name", ""))
        where = f"{c.rel} {p.path}"
        if not PROP_NAME_RE.match(name):
            errs.append(Err("L015", where, f"nom '{name}' : snake_case minuscule ASCII, commence par une lettre"))
            continue
        if c.layer not in DERIVED_LAYERS or not p.top:
            continue
        ptype = str(p.node.get("physicalType", "")).upper()
        for kind, token, types in CUSTOMER_TYPE_RULES:
            hit = name.endswith(token) if kind == "suffix" else name.startswith(token)
            if hit and ptype not in types:
                errs.append(Err("L015", where, f"'{name}' impose physicalType {'/'.join(types)} (trouve '{ptype}')"))
        if name.startswith("meta_") and p.node.get("transformLogic") != "create":
            errs.append(Err("L015", where, f"'{name}' : un champ meta_ est un champ technique en transformLogic create"))
    return errs


def check_customer_key_class(c: Contract) -> list[Err]:
    errs: list[Err] = []
    if c.layer not in DERIVED_LAYERS:
        return errs
    for p in all_props(c):
        if p.node.get("name") != "customer_key":
            continue
        where = f"{c.rel} {p.path}"
        if p.node.get("classification") != "C2" or "pseudonymized" not in (p.node.get("tags") or []):
            errs.append(Err("L016", where, "customer_key doit etre C2 avec le tag pseudonymized"))
    return errs


def check_pii(c: Contract) -> list[Err]:
    errs = []
    for p in all_props(c):
        tags = p.node.get("tags") if isinstance(p.node.get("tags"), list) else []
        has_tag = PII_TAG in tags
        has_cls = p.node.get("classification") == PII_CLASSIFICATION
        if has_tag and not has_cls:
            errs.append(Err("L010", f"{c.rel} {p.path}", f"tag '{PII_TAG}' sans classification '{PII_CLASSIFICATION}'"))
        if has_cls and not has_tag:
            errs.append(Err("L010", f"{c.rel} {p.path}", f"classification '{PII_CLASSIFICATION}' sans tag '{PII_TAG}'"))
    return errs


def check_raw_transform(c: Contract) -> list[Err]:
    """L006 : chaque champ de premier niveau d'un raw porte son lineage vers la source externe."""
    errs = []
    system = RAW_SYSTEMS.get(c.folder)
    for p in all_props(c):
        if not p.top:
            continue
        n = p.node
        where = f"{c.rel} {p.path}"
        logic = n.get("transformLogic")
        srcs = sources_of(n)
        if not logic:
            errs.append(Err("L006", where, "transformLogic manquant sur un champ raw"))
            continue
        if not str(n.get("transformDescription", "")).strip():
            errs.append(Err("L006", where, "transformDescription manquante sur un champ raw"))
        if n.get("name") in TECH_FIELDS:
            if logic != "create" or srcs:
                errs.append(Err("L006", where, "un champ technique raw doit etre transformLogic: create, sans transformSourceObjects"))
            continue
        if logic != "map":
            errs.append(Err("L006", where, f"un champ raw est transformLogic: map (aucun calcul), pas '{logic}'"))
            continue
        if len(srcs) != 1:
            errs.append(Err("L006", where, f"map exige exactement 1 source externe ({len(srcs)} trouvee(s))"))
            continue
        m = REF_RE.match(str(srcs[0]))
        if not m or m["contract"] != system:
            errs.append(Err("L006", where, f"source '{srcs[0]}' invalide (attendu {system}#<objet>.<champ>)"))
    return errs


def check_primary_key(c: Contract) -> list[Err]:
    """L019 : le grain d'un core est declare par une cle primaire."""
    return [
        Err("L019", f"{c.rel} {obj.get('name', '?')}", "un objet core a au moins une property primaryKey")
        for obj in schema_objects(c)
        if not any(isinstance(p, dict) and p.get("primaryKey") for p in obj.get("properties") or [])
    ]


def reuses_core_key(c: Contract, expr: str, srcs: list, by_id: dict[str, Contract]) -> bool:
    """L012 : un customer reprend le customer_key d'un core tel quel, le hachage n'est ecrit qu'en core."""
    if c.layer != "customer" or not re.fullmatch(r"(?:\w+\.)?customer_key", expr):
        return False
    matches = [REF_RE.match(str(s)) for s in srcs]
    return any(m and m["path"] == "customer_key" and by_id.get(m["contract"]) and by_id[m["contract"]].layer == "core" for m in matches)


def check_derived_fields(c: Contract, by_id: dict[str, Contract]) -> tuple[list[Err], set[str]]:
    """L003, L004, L007, L008, L011, L012 pour un core ou un customer. Retourne aussi les ids references."""
    errs, referenced = [], set()
    for p in all_props(c):
        n, where = p.node, f"{c.rel} {p.path}"
        logic = n.get("transformLogic")
        if logic is None:
            if p.top:
                errs.append(Err("L008", where, "transformLogic manquant"))
            continue
        if p.top and not str(n.get("transformDescription", "")).strip():
            errs.append(Err("L008", where, "transformDescription manquante"))
        if logic not in LOGICS:
            errs.append(Err("L007", where, f"transformLogic '{logic}' hors de {', '.join(LOGICS)}"))
            continue
        srcs = sources_of(n)
        expr = custom_prop(n, "transformExpression")
        expr_ok = isinstance(expr, str) and expr.strip() != ""
        if logic == "map" and len(srcs) != 1:
            errs.append(Err("L007", where, f"map exige exactement 1 source ({len(srcs)} trouvee(s))"))
        if logic == "transform":
            if len(srcs) < 1:
                errs.append(Err("L007", where, "transform exige au moins 1 source"))
            if not expr_ok:
                errs.append(Err("L007", where, "transform exige customProperties.transformExpression non vide"))
        if logic == "create" and srcs:
            errs.append(Err("L007", where, f"create n'accepte aucune source ({len(srcs)} trouvee(s))"))
        if logic == "map" and expr_ok and not TRIVIAL_MAP_RE.match(expr):
            errs.append(Err("L011", where, f"map limite a un renommage ou un cast trivial, pas '{expr}' (utiliser transform)"))
        if n.get("name") == "customer_key" and p.top:
            norm = re.sub(r"\s+", "", expr) if expr_ok else ""
            if not (CUSTOMER_KEY_RE.match(norm) or reuses_core_key(c, norm, srcs, by_id)):
                errs.append(Err("L012", where, f"customer_key doit suivre la regle canonique: {CUSTOMER_KEY_CANONICAL}"))
        for ref in srcs:
            m = REF_RE.match(ref) if isinstance(ref, str) else None
            if not m:
                errs.append(Err("L003", where, f"reference '{ref}' invalide (attendu <contract_id>#<objet>.<property>)"))
                continue
            target = by_id.get(m["contract"])
            if target is None:
                errs.append(Err("L003", where, f"contrat '{m['contract']}' introuvable (reference '{ref}')"))
                continue
            referenced.add(target.cid)
            if target.layer not in READS[c.layer]:
                errs.append(Err("L004", where, f"un {c.layer} ne reference que {READS_LABEL[c.layer]}, pas '{target.cid}'"))
            obj = next((o for o in schema_objects(target) if o.get("name") == m["obj"]), None)
            if obj is None:
                errs.append(Err("L003", where, f"objet de schema '{m['obj']}' introuvable dans '{target.cid}'"))
            elif not resolve_path(obj, m["path"]):
                errs.append(Err("L003", where, f"property '{m['path']}' introuvable dans '{target.cid}#{m['obj']}'"))
    return errs, referenced


def check_flow_folder(c: Contract) -> list[Err]:
    if c.folder in FLOWS:
        return []
    return [Err("L009", c.rel, f"flux '{c.folder}' inconnu : dossier attendu parmi {', '.join(FLOWS)}")]


def find_cycles(graph: dict[str, set[str]]) -> list[list[str]]:
    cycles, state, stack = [], {}, []

    def dfs(node: str) -> None:
        state[node] = 1
        stack.append(node)
        for nxt in sorted(graph.get(node, ())):
            if state.get(nxt) == 1:
                cycles.append(stack[stack.index(nxt):] + [nxt])
            elif nxt not in state:
                dfs(nxt)
        stack.pop()
        state[node] = 2

    for n in sorted(graph):
        if n not in state:
            dfs(n)
    return cycles


# ---------------------------------------------------------------- orchestration


def run(root: Path, count: bool = True) -> list[Err]:
    contracts, errors = load_contracts(root)
    by_id = {c.cid: c for c in contracts if isinstance(c.cid, str)}
    if count:
        errors += check_count(contracts)
    graph: dict[str, set[str]] = {}
    for c in contracts:
        errors += check_naming(c)
        errors += check_metadata(c)
        errors += check_docs(c)
        errors += check_load_strategy(c)
        errors += check_pii(c)
        errors += check_property_names(c)
        errors += check_customer_key_class(c)
        if c.layer == "raw":
            errors += check_raw_transform(c)
        elif c.layer in DERIVED_LAYERS:
            errs, referenced = check_derived_fields(c, by_id)
            errors += errs
            errors += check_flow_folder(c) if c.layer == "customer" else check_primary_key(c)
            if isinstance(c.cid, str):
                graph[c.cid] = referenced
    for cycle in find_cycles(graph):
        errors.append(Err("L005", "contracts", f"cycle de references: {' -> '.join(cycle)}"))
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", type=Path, default=REPO_ROOT, help="racine contenant contracts/")
    parser.add_argument("--no-count", action="store_true", help="desactive le decompte strict L001 (repo en construction)")
    args = parser.parse_args(argv)

    if not find_contracts(args.root):
        print(f"ERREUR: aucun contrat *.odcs.yaml sous {args.root / 'contracts'}", file=sys.stderr)
        return 1
    errors = run(args.root, count=not args.no_count)
    for e in sorted(errors, key=lambda e: (e.code, e.where, e.message)):
        print(e)
    if errors:
        print(f"\n{len(errors)} erreur(s) de lineage/convention.", file=sys.stderr)
        return 1
    print("OK lineage et conventions" + (" (decompte non verifie)." if args.no_count else " (decompte inclus)."))
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Adapte le template HTML de dbt-colibri (v0.3.6, interface compilee) a un catalogue de data contracts.

Colibri ne livre que son bundle minifie : on ne peut pas le recompiler, on le patche par
remplacement de chaines. Chaque remplacement est obligatoire : si une version future de colibri
change le bundle, la generation echoue explicitement au lieu de produire une page silencieusement
incorrecte (la version est epinglee dans pyproject.toml).

Retraits :
- les 3 encarts publicitaires "Colibri Cloud" (ERD, Saved Views, Recent Commits) ;
- le vocabulaire dbt (commandes `dbt build`, aides `dbt compile`, titre) ;
- l'onglet "Compiled" (pas de code compile dans un contrat).
Ajouts dans le panneau natif "Model info" (catalog_assets/column_info.js et .css) : infos du
contrat, types logique et physique en accordeon, SQL de transformation, mode expert.
"""
from __future__ import annotations

import re
from pathlib import Path

ASSETS = Path(__file__).parent / "catalog_assets"
UPSELL_START = "R.jsx($c,{delayDuration:200,"
UPSELL_END = 'Try this feature on Colibri Cloud"})]})})'


class TemplateMismatch(RuntimeError):
    pass


def _cut(html: str, key: str, start_marker: str, end_marker: str, tail: str = "") -> str:
    """Remplace par `null` le bloc JSX qui contient `key`, de `start_marker` (le plus proche avant) a `end_marker` (+ tail)."""
    k = html.find(key)
    a = html.rfind(start_marker, 0, k) if k >= 0 else -1
    b = html.find(end_marker, k) if k >= 0 else -1
    if k < 0 or a < 0 or b < 0:
        raise TemplateMismatch(f"bloc introuvable : {key}")
    b += len(end_marker)
    if tail:
        if html[b : b + len(tail)] != tail:
            raise TemplateMismatch(f"fin de bloc inattendue pour {key}")
        b += len(tail)
    return html[:a] + "null" + html[b:]


def _sub(html: str, old: str, new: str, count: int | None = None) -> str:
    n = html.count(old)
    if n == 0 or (count is not None and n != count):
        raise TemplateMismatch(f"chaine attendue {count or '>=1'} fois, trouvee {n} fois : {old[:70]}")
    return html.replace(old, new)


def _resub(html: str, pattern: str, repl: str) -> str:
    new, n = re.subn(pattern, repl, html)
    if n < 1:
        raise TemplateMismatch(f"motif introuvable : {pattern[:70]}")
    return new


def _between(html: str, start: str, end: str, new: str) -> str:
    a = html.find(start)
    b = html.find(end, a) if a >= 0 else -1
    if a < 0 or b < 0:
        raise TemplateMismatch(f"zone introuvable : {start[:60]}")
    return html[:a] + new + html[b + len(end) :]


def _patch_model_info(html: str) -> str:
    """Branche column_info.js dans la liste des colonnes et l'apercu du panneau Model info."""
    # a) Ligne de colonne : bloc ajoute apres la description.
    m = re.search(
        r'(\w+)\.description&&R\.jsx\("div",\{className:"text-xs text-muted-foreground leading-relaxed prose prose-xs",'
        r"children:R\.jsx\(\w+,\{remarkPlugins:\[\w+\],children:\1\.description\}\)\}\)(\]\},\1\.columnName\)\))",
        html,
    )
    if not m:
        raise TemplateMismatch("ligne de colonne du panneau Model info introuvable")
    col = m.group(1)
    back = html[max(0, m.start() - 1500) : m.start()]
    found = re.findall(r"(\w+)&&(\w+)\(\1,%s\.columnName\)" % re.escape(col), back)
    if not found:
        raise TemplateMismatch("variable de l'id du noeud introuvable")
    model = found[-1][0]
    extra = (
        f',R.jsx("div",{{onClick:e=>e.stopPropagation(),'
        f"dangerouslySetInnerHTML:{{__html:window.cpColumnHtml({model},{col}.columnName)}}}})"
    )
    at = m.start(2)
    html = html[:at] + extra + html[at:]

    # b) Bouton "Mode expert" dans l'en-tete de la liste des colonnes.
    k = html.find('placeholder:"Find...",value:')
    box = 'R.jsxs("div",{className:"relative w-32",children:['
    j = html.rfind(box, 0, k) if k >= 0 else -1
    if k < 0 or j < 0 or k - j > 600:
        raise TemplateMismatch("en-tete de la liste des colonnes introuvable")
    button = (
        'R.jsx("button",{className:"cp-expert-toggle",title:"Afficher les propri\\u00e9t\\u00e9s techniques",'
        'onClick:()=>window.cpToggleExpert(),children:"Mode expert"}),'
    )
    html = html[:j] + button + html[j:]

    # c) Infos du contrat avant la liste des colonnes (apercu du noeud).
    head = 'R.jsxs("div",{children:[R.jsxs("div",{className:"flex items-center justify-between mb-2",children:[R.jsxs(pk,{children:["Columns ("'
    n = html.find(head)
    if n < 0:
        raise TemplateMismatch("entete Columns de l'apercu introuvable")
    card = f'R.jsx("div",{{dangerouslySetInnerHTML:{{__html:window.cpNodeHtml({model})}}}}),'
    return html[:n] + card + html[n:]


def _patch_columns_tab(html: str) -> str:
    """Onglet Columns : transformation et types dans la ligne depliee, bouton Mode expert."""
    m = re.search(
        r'R\.jsxs\("div",\{children:\[R\.jsx\("div",\{className:"text-xs font-semibold text-muted-foreground uppercase mb-1",children:"Description"\}\),'
        r'R\.jsx\("div",\{className:"text-sm prose prose-sm dark:prose-invert max-w-none break-words",children:([\w$]+)\.description\?'
        r'R\.jsx\([\w$]+,\{remarkPlugins:\[[\w$]+\],children:\1\.description\}\):R\.jsx\("span",\{className:"text-muted-foreground italic",'
        r'children:"No description available"\}\)\}\)\]\}\)',
        html,
    )
    if not m:
        raise TemplateMismatch("ligne depliee de l'onglet Columns introuvable")
    col = m.group(1)
    head = re.findall(r"function [\w$]+\(\{selectedModelId:([\w$]+),", html[: m.start()])
    if not head:
        raise TemplateMismatch("composant de l'onglet Columns introuvable")
    model = head[-1]
    extra = f',R.jsx("div",{{dangerouslySetInnerHTML:{{__html:window.cpColumnTabHtml({model},{col}.columnName)}}}})'
    html = html[: m.end()] + extra + html[m.end() :]

    anchor = 'R.jsx("div",{className:"mb-4",children:R.jsxs("div",{className:"relative max-w-sm",children:[R.jsx(v6,'
    if html.count(anchor) != 1:
        raise TemplateMismatch("barre de recherche de l'onglet Columns introuvable")
    toggle = (
        'R.jsx("div",{className:"flex justify-end mb-2",children:R.jsx("button",{className:"cp-expert-toggle",'
        'title:"Afficher les propriétés techniques",onClick:()=>window.cpToggleExpert(),children:"Mode expert"})}),'
    )
    return html.replace(anchor, toggle + anchor)


def _remove_code_views(html: str) -> str:
    """Pas de vue code : ni onglet "Code", ni bascule modele / code du panneau lateral."""
    html = _resub(html, r'[\w$]+&&R\.jsx\([\w$]+,\{value:"code",className:"text-xs",children:"Code"\}\)', "null")
    return _resub(
        html,
        r'[\w$]+&&[\w$]+&&R\.jsx\("div",\{className:"absolute top-0 left-0 w-full flex justify-center pt-2 z-40 bg-card rounded-t-lg",'
        r'children:R\.jsx\([\w$]+,\{value:[\w$]+,onValueChange:[\w$]+=>[\w$]+\([\w$]+\),options:\[\{value:"info",icon:[\w$]+\},\{value:"code",icon:[\w$]+\}\]\}\)\}\)',
        "null",
    )


def _drop_lineage_warning(html: str) -> str:
    """Retire la bulle "Column lineage unavailable" des noeuds : fausse pour un contrat raw (pas de source amont)."""
    key = "Column lineage unavailable"
    k = html.find(key)
    start_marker = 'R.jsx($c,{children:R.jsxs(Kc,{children:[R.jsx(Jc,{asChild:!0,children:R.jsx("div",{className:"absolute -top-3 -left-3'
    a = html.rfind(start_marker, 0, k) if k >= 0 else -1
    end_marker = 'to fix this."]})})]})]})})'
    b = html.find(end_marker, k) if k >= 0 else -1
    if a < 0 or b < 0 or html.count(key) != 1:
        raise TemplateMismatch("bulle de lineage indisponible introuvable")
    guard = re.search(r"\w+&&$", html[max(0, a - 12) : a])
    if not guard:
        raise TemplateMismatch("condition de la bulle de lineage introuvable")
    a -= len(guard.group(0))
    return html[:a] + "null" + html[b + len(end_marker) :]


def patch_template(html: str) -> str:
    # 0. Bulle d'avertissement "Column lineage unavailable" (fausse pour un raw).
    html = _drop_lineage_warning(html)

    # 1. Encarts "Try this feature on Colibri Cloud" : Recent Commits, Saved Views, ERD.
    html = _cut(
        html,
        '("git_blame"',
        'R.jsxs("div",{className:"border-t pt-5",children:[R.jsx(pk,{children:"Recent Commits"}),',
        UPSELL_END,
        tail="]})",
    )
    html = _cut(
        html,
        '("saved_views"',
        'R.jsx("div",{className:"px-3 pb-2 flex-shrink-0",children:',
        UPSELL_END,
        tail="})",
    )
    html = _cut(html, '("erd"', UPSELL_START, UPSELL_END)
    if "Colibri Cloud" in html:
        raise TemplateMismatch("un encart Colibri Cloud subsiste")

    # 2. Commandes dbt -> identifiants de contrats.
    html = _resub(html, r"`dbt build \\\\\n  --select \\\\\n  \$\{(\w+)\.join\(`[^`]*`\)\}`", r'`${\1.join("\\n")}`')
    html = _resub(html, r"`dbt build --select \$\{(\w+)\.name\}`", r"`${\1.name}`")
    html = _sub(html, "Copy dbt command for dependent models", "Copy dependent contract ids")
    html = _sub(html, "Copy dbt command for selection", "Copy selected contract ids")
    html = _sub(html, "Copy a dbt command for the current selection.", "Copy the ids of the selected contracts.")
    html = _sub(html, "Copy dbt command", "Copy contract id")
    html = _sub(html, "Copied dbt command for ", "Copied contract id for ")
    html = _resub(
        html,
        r'Copied command for \$\{(\w+)\.length\} dependent model\$\{\1\.length>1\?"s":""\}',
        r'Copied ${\1.length} contract id${\1.length>1?"s":""}',
    )
    html = _sub(html, "No dependent models found for this column.", "No dependent contracts found for this column.")
    html = _sub(html, "Error generating dbt command:", "Error copying contract id:")
    html = _sub(html, "https://schemas.getdbt.com/dbt/manifest/v12.json", "odcs-v3.2.0")
    html = _sub(html, "<title>Colibri Data</title>", "<title>Catalogue de données</title>", 1)

    # 3. Pas de code compile : onglet masque, "Raw" devient le YAML du contrat.
    html = _sub(html, 'children:"Compiled"})', 'children:"Compiled",style:{display:"none"}})', 2)
    html = _sub(html, 'rounded-[4px]",children:"Raw"}', 'rounded-[4px]",children:"Contrat YAML"}', 1)
    html = _sub(html, 'disabled:!ie,children:"Raw"}', 'disabled:!ie,children:"Contrat YAML"}', 1)
    html = _sub(html, "Compiled SQL", "Requête de contrôle", 2)

    # 4. Panneau natif "Model info" : infos du contrat, types, SQL de transformation, mode expert.
    html = _patch_model_info(html)
    html = _patch_columns_tab(html)
    html = _remove_code_views(html)
    css = (ASSETS / "column_info.css").read_text(encoding="utf-8")
    js = (ASSETS / "column_info.js").read_text(encoding="utf-8")
    return _sub(html, "</head>", f"<style>{css}</style><script>{js}</script></head>", 1)

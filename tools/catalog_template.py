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
contrat, types logique et physique en accordeon, SQL de transformation, mode expert, onglet
"Trace" (pour une colonne : classification, sources, transformations et arbre de lignage).
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


def _resub(html: str, pattern: str, repl) -> str:
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
        'R.jsx("button",{className:"cp-expert-toggle",title:"Show technical properties",'
        'onClick:()=>window.cpToggleExpert(),children:"Data engineer mode"}),'
    )
    html = html[:j] + button + html[j:]

    # c) Infos du contrat avant la liste des colonnes (apercu du noeud).
    head = 'R.jsxs("div",{children:[R.jsxs("div",{className:"flex items-center justify-between mb-2",children:[R.jsxs(pk,{children:["Columns ("'
    n = html.find(head)
    if n < 0:
        raise TemplateMismatch("entete Columns de l'apercu introuvable")
    card = f'R.jsx("div",{{dangerouslySetInnerHTML:{{__html:window.cpNodeHtml({model})}}}}),'
    return html[:n] + card + html[n:]


def _patch_model_tests(html: str) -> str:
    """Bloc natif "Model Tests" : ne montre que la severite (champs absents des contrats). Remplace par un bloc lisible."""
    return _resub(
        html,
        r'children:\["Model Tests \(",([\w$]+)\.length,"\)"\]\}\),R\.jsx\("div",\{className:"space-y-3",children:\1\.map\(',
        r'children:["Quality checks (",\1.length,")"]}),'
        r'R.jsx("div",{dangerouslySetInnerHTML:{__html:window.cpModelTestsHtml(\1)}}),'
        r'R.jsx("div",{hidden:!0,className:"space-y-3",children:\1.map(',
    )


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

    # Bloc natif "Tests" de la ligne depliee (puce "odcs" sans contenu utile) : retire.
    html = _resub(
        html,
        r'([\w$]+)\.hasTests&&\1\.tests&&R\.jsxs\("div",\{className:"mt-4 border-t pt-4"',
        'false&&R.jsxs("div",{className:"mt-4 border-t pt-4"',
    )

    anchor = 'R.jsx("div",{className:"mb-4",children:R.jsxs("div",{className:"relative max-w-sm",children:[R.jsx(v6,'
    if html.count(anchor) != 1:
        raise TemplateMismatch("barre de recherche de l'onglet Columns introuvable")
    toggle = (
        'R.jsx("div",{className:"flex justify-end mb-2",children:R.jsx("button",{className:"cp-expert-toggle",'
        'title:"Show technical properties",onClick:()=>window.cpToggleExpert(),children:"Data engineer mode"})}),'
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


def _bigquery_info(html: str) -> str:
    """Overview : le bloc "Model Information" (database, materialization, type de modele...) devient le schema BigQuery."""
    html = _sub(html, 'children:"Model Information"})', 'children:"BigQuery schema"})', 1)
    # Colonne de gauche : projet puis table. Colonne de droite : dataset.
    # Database = project_id.dataset.table (relationName) : l'interface ne recoit pas le champ `database`.
    html = _sub(html, 'mb-1",children:"Database"}),R.jsx("div",{className:"text-sm font-medium",children:be?.split(".")[0]||"N/A"})',
                'mb-1",children:"Database"}),R.jsx("div",{className:"text-sm font-medium break-all",children:s?.relationName||"N/A"})', 1)
    html = _sub(html, 'mb-1",children:"Materialization"}),R.jsx("div",{className:"text-sm font-medium capitalize",children:Oe})',
                'mb-1",children:"Table"}),R.jsx("div",{className:"text-sm font-medium",children:(s?.relationName||"").split(".").pop()||"N/A"})', 1)
    html = _sub(html, 'mb-1",children:"Schema"}),', 'mb-1",children:"Dataset"}),', 1)
    # Grille sans retour a la ligne : les colonnes s'adaptent au contenu.
    html = _sub(html, 'className:"grid grid-cols-2 gap-y-6 max-w-2xl",children:[R.jsxs("div",{className:"space-y-6",children:[R.jsxs("div",{children:[R.jsx("div",{className:"text-sm text-muted-foreground mb-1",children:"Database"})',
                'className:"grid gap-y-6",style:{gridTemplateColumns:"max-content max-content",columnGap:"4rem"},children:[R.jsxs("div",{className:"space-y-6",children:[R.jsxs("div",{children:[R.jsx("div",{className:"text-sm text-muted-foreground mb-1",children:"Database"})', 1)
    html = _sub(html, 'className:"text-sm font-medium break-all",children:s?.relationName', 'className:"text-sm font-medium whitespace-nowrap",children:s?.relationName', 1)

    def cell(label: str, call: str) -> str:
        return (
            'R.jsxs("div",{children:[R.jsx("div",{className:"text-sm text-muted-foreground mb-1",children:"' + label + '"}),'
            'R.jsx("div",{className:"text-sm font-medium capitalize whitespace-nowrap",children:window.' + call + '(s?.fullName)})]})'
        )

    # "Contract Enforced" (sans objet) devient le type de l'objet (table, view) ; "Model Type" devient la strategie de chargement.
    html = _resub(
        html,
        r'[\w$]+!==void 0&&R\.jsxs\("div",\{children:\[R\.jsx\("div",\{className:"text-sm text-muted-foreground mb-1",children:"Contract Enforced"\}\),'
        r'R\.jsx\("div",\{className:"text-sm font-medium",children:[\w$]+\?"Yes":"No"\}\)\]\}\)',
        lambda _m: cell("Type", "cpObjectType"),
    )
    return _resub(
        html,
        r'R\.jsxs\("div",\{children:\[R\.jsx\("div",\{className:"text-sm text-muted-foreground mb-1",children:"Model Type"\}\),'
        r'R\.jsx\("div",\{className:"text-sm font-medium capitalize",children:[\w$]+\}\)\]\}\)',
        lambda _m: cell("Load strategy", "cpLoadStrategy"),
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


def _trace_tab(html: str) -> str:
    """Onglet "Trace" a cote de "Model Info" et "Lineage" : le contenu, pour le contrat selectionne,
    est rendu par window.cpTraceTabHtml(selectedModelId)."""
    # a) Entree de la barre d'onglets (le rendu du bouton est natif : f.map(...)), avec sa propre
    #    icone (lucide "route"), creee par la meme fabrique que les icones du bundle.
    icon = '_De=pi("file-text",KSt)'
    route = (
        'cpTraceIcon=pi("route",[["circle",{cx:"6",cy:"19",r:"3",key:"a"}],'
        '["path",{d:"M9 19h8.5a3.5 3.5 0 0 0 0-7h-11a3.5 3.5 0 0 1 0-7H15",key:"b"}],'
        '["circle",{cx:"18",cy:"5",r:"3",key:"c"}]])'
    )
    html = _sub(html, icon + ";", icon + "," + route + ";", 1)
    tabs = 'const f=[{id:"docs",label:"Model Info",icon:_De},{id:"lineage",label:"Lineage",icon:xqt}];'
    trace_entry = ',{id:"trace",label:"Trace",icon:cpTraceIcon}];'
    html = _sub(html, tabs, tabs[:-2] + trace_entry, 1)
    # b) L'onglet actif suit l'etat de la vue : "trace" est un etat comme "docs" et "lineage".
    html = _sub(
        html,
        'activeContext:i==="lineage"?"lineage":"docs"',
        'activeContext:i==="trace"?"trace":i==="lineage"?"lineage":"docs"',
        1,
    )
    # c) Panneau de contenu de l'onglet, frere du panneau docs (selectedModelId = l dans cette portee).
    #    Fond opaque : la vue lineage reste montee dessous et ses noeuds React Flow forcent
    #    visibility:visible en inline, ils transparaitraient sinon a travers le panneau.
    trace_panel = (
        'R.jsx("div",{className:`absolute inset-0 flex flex-col isolate pointer-events-none ${i!=="trace"?"invisible":""}`,'
        'children:R.jsxs("div",{className:"flex-1 flex flex-col overflow-hidden cp-trace-wrap bg-background",children:['
        "Ee,"
        'R.jsx("div",{id:"cp-trace-panel",className:"flex-1 min-h-0 overflow-hidden p-4",dangerouslySetInnerHTML:{__html:window.cpTraceTabHtml(l)}})]})})'
    )
    html = _sub(html, "setExpandedSchemas:J})})})]})", "setExpandedSchemas:J})})})," + trace_panel + "]})", 1)
    # d) Clic sur une ligne de colonne du panneau du contrat : l'onglet Trace reprend cette colonne.
    row_click = "onClick:()=>{l&&s&&l(s,Y.columnName)}"
    followed = "onClick:()=>{window.cpTraceColumnSet&&s&&window.cpTraceColumnSet(String(s),Y.columnName);l&&s&&l(s,Y.columnName)}"
    return _sub(html, row_click, followed, 1)


def _doc_tab(html: str) -> str:
    """Onglet "Doc" a cote de "Model Info" et "Lineage" : ouvre catalog_assets/lineage.fr.html (lien vers l'anglais dans la page)."""
    anchor = "p.label]},p.id)}),"
    link = (
        'R.jsx("a",{href:"lineage.fr.html",className:"flex items-center gap-2 px-3 py-1.5 text-xs font-medium '
        'rounded-md text-muted-foreground hover:text-foreground hover:bg-accent/50",children:"Doc"}),'
    )
    return _sub(html, anchor, anchor + link, 1)


def _filter_columns(html: str) -> str:
    """Filtre de gauche : colibri ne compare que le nom du contrat et son dataset. On ajoute les
    colonnes et le dossier (window.cpFilterMatch) a chacun de ses 7 predicats."""
    pattern = (r"return (\w+)\.toLowerCase\(\)\.includes\((\w+)\)\|\|(\w+)\.toLowerCase\(\)\.includes\(\2\)"
               r"\|\|(\w+)\.toLowerCase\(\)\.includes\(\2\)")
    new, n = re.subn(pattern, lambda m: f"{m[0]}||window.cpFilterMatch({m[3]},{m[2]})", html)
    if n != 7:
        raise TemplateMismatch(f"filtre de gauche : 7 predicats attendus, {n} trouves")
    return new


def _search_descriptions(html: str) -> str:
    """Recherche globale : colibri ne compare que les noms. On ajoute la description du contrat et
    celle de chaque colonne, classees apres les correspondances sur le nom (score 100)."""
    html = _sub(html, "cue(i.id,s,40)]):null", "cue(i.id,s,40),cue(i.description,s,100)]):null", 1)
    html = _sub(html, "gqt=(i,s)=>cue(i,s,0)", "gqt=(i,s,d)=>hqt([cue(i,s,0),cue(d,s,100)])", 1)
    html = _sub(html, "gqt(Xe.columnName,Me)", "gqt(Xe.columnName,Me,Xe.description)", 1)
    html = _sub(html, 'placeholder:"Search models, sources..."', 'placeholder:"Search contracts, columns, descriptions..."', 1)
    return _sub(html, 'placeholder:"Search for models and columns..."', 'placeholder:"Search contracts, columns, descriptions..."', 1)


def patch_template(html: str) -> str:
    # 0. Bulle d'avertissement "Column lineage unavailable" (fausse pour un raw).
    html = _drop_lineage_warning(html)
    html = _filter_columns(html)
    html = _search_descriptions(html)

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
    html = _sub(html, "<title>Colibri Data</title>", "<title>Data catalog</title>", 1)

    # 3. Pas de code compile : onglet masque, "Raw" devient le YAML du contrat.
    html = _sub(html, 'children:"Compiled"})', 'children:"Compiled",style:{display:"none"}})', 2)
    html = _sub(html, 'rounded-[4px]",children:"Raw"}', 'rounded-[4px]",children:"Contract YAML"}', 1)
    html = _sub(html, 'disabled:!ie,children:"Raw"}', 'disabled:!ie,children:"Contract YAML"}', 1)
    html = _sub(html, "Compiled SQL", "Check query", 2)

    # 4. Panneau natif "Model info" : infos du contrat, types, SQL de transformation, mode expert.
    html = _patch_model_info(html)
    html = _patch_columns_tab(html)
    html = _patch_model_tests(html)
    html = _remove_code_views(html)
    html = _bigquery_info(html)
    css = (ASSETS / "column_info.css").read_text(encoding="utf-8")
    js = (ASSETS / "column_info.js").read_text(encoding="utf-8")
    html = _trace_tab(html)
    html = _doc_tab(html)
    return _sub(html, "</head>", f"<style>{css}</style><script>{js}</script></head>", 1)

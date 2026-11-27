/* Contenu ajoute au panneau natif "Model info" du catalogue : types, transformation SQL,
   mode expert, onglet Trace. Lit window.colibriData (genere depuis les data contracts).
   Aucun appel reseau. */
(function () {
  "use strict";
  /* Le mode expert repart toujours desactive a l'ouverture de la page (pas de memorisation). */
  window.cpToggleExpert = function () {
    document.documentElement.classList.toggle("cp-expert");
  };

  var copies = [];
  document.addEventListener("click", function (ev) {
    var b = ev.target.closest && ev.target.closest("button[data-cp-copy]");
    if (!b) return;
    ev.stopPropagation();
    var txt = copies[+b.getAttribute("data-cp-copy")];
    if (navigator.clipboard && txt != null) navigator.clipboard.writeText(txt).then(function () { b.textContent = "Copied"; });
  }, true);

  /* Clics de l'onglet Trace : liste des colonnes (traceListHtml), puis lignes de l'arbre et entrees
     du detail. Delegation : le contenu du panneau est remplace apres le rendu React. */
  document.addEventListener("click", function (ev) {
    if (!ev.target.closest) return;
    var btn = ev.target.closest("[data-cp-col]");
    if (btn) return window.cpTraceColumnSet(btn.getAttribute("data-cp-model"), btn.getAttribute("data-cp-col"));
    btn = ev.target.closest("[data-cp-node-col]");
    if (btn) window.cpTraceNodeSet(btn.getAttribute("data-cp-node-model"), btn.getAttribute("data-cp-node-col"));
  });

  function data() { return window.colibriData || { nodes: {}, lineage: { edges: [] } }; }
  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }
  var KW = {};
  ("SELECT FROM WHERE GROUP BY ORDER HAVING JOIN LEFT RIGHT FULL OUTER INNER ON AS AND OR NOT IN IS NULL CASE WHEN THEN ELSE END " +
    "WITH UNION ALL DISTINCT OVER PARTITION LIMIT BETWEEN LIKE EXISTS INTERVAL ASC DESC TRUE FALSE USING UNNEST CROSS").split(" ")
    .forEach(function (k) { KW[k] = 1; });
  function hl(sql) {
    var re = /(--[^\n]*)|('(?:[^'\\]|\\.)*')|(\b\d+(?:\.\d+)?\b)|(\b[A-Za-z_][A-Za-z0-9_]*\b)(\s*\()?|([\s\S])/g;
    return String(sql).replace(re, function (m, com, str, num, word, par, ch) {
      if (com) return '<span class="cp-c">' + esc(com) + "</span>";
      if (str) return '<span class="cp-s">' + esc(str) + "</span>";
      if (num) return '<span class="cp-n">' + esc(num) + "</span>";
      if (word) {
        if (par) return '<span class="cp-f">' + esc(word) + "</span>" + esc(par);
        if (KW[word.toUpperCase()]) return '<span class="cp-k">' + esc(word) + "</span>";
        return esc(word);
      }
      return esc(ch);
    });
  }
  function sql(text, title) {
    copies.push(String(text));
    return '<div class="cp-sql"><div class="cp-sqlbar"><span>' + esc(title) + '</span><button class="cp-btn" data-cp-copy="' +
      (copies.length - 1) + '">Copy</button></div><pre><code>' + hl(text) + "</code></pre></div>";
  }
  function acc(title, body, open) {
    return '<details class="cp-acc"' + (open ? " open" : "") + "><summary>" + esc(title) + '</summary><div class="cp-in">' + body + "</div></details>";
  }
  function badge(t, cls) { return '<span class="cp-badge ' + (cls || "") + '">' + esc(t) + "</span>"; }
  function kv(rows) {
    var h = "";
    rows.forEach(function (r) { if (r[1] != null && r[1] !== "") h += "<b>" + esc(r[0]) + "</b><span>" + r[1] + "</span>"; });
    return h ? '<div class="cp-kv">' + h + "</div>" : "";
  }
  function list(items) {
    return items.length ? '<ul class="cp-list">' + items.map(function (i) { return "<li>" + i + "</li>"; }).join("") + "</ul>" : '<span class="cp-note">None</span>';
  }
  var LEVEL = { C0: "public", C1: "internal", C2: "confidential", C3: "restricted" };
  function sens(c) {
    var m = c.meta || {}, t = c.tags || [], h = "";
    if (m.classification) h += badge(LEVEL[m.classification] ? m.classification + " · " + LEVEL[m.classification] : m.classification, m.classification === "C3" ? "hi" : m.classification === "C2" ? "mid" : "");
    if (t.indexOf("pii") >= 0) h += badge("PII", "hi");
    if (t.indexOf("pseudonymized") >= 0) h += badge("pseudonymized", "mid");
    if (t.indexOf("pii_potential") >= 0) h += badge("potential PII", "mid");
    return h;
  }
  function tests(ts) {
    return (ts || []).map(function (t) {
      var k = t.kwargs || {};
      return "<div><b>" + esc(t.name) + "</b> " + badge(k.dimension || "check") + (t.config && t.config.severity ? badge(t.config.severity) : "") +
        (k.description ? '<div class="cp-note">' + esc(k.description) + "</div>" : "") +
        (k.query ? sql(k.query, "Check query") : "") + "</div>";
    }).join("");
  }

  var OPS = { mustBe: "=", mustNotBe: "≠", mustBeGreaterThan: ">", mustBeGreaterOrEqualTo: "≥", mustBeLessThan: "<", mustBeLessOrEqualTo: "≤" };
  /* Regle lisible d'un controle : `rowCount > 0`, `résultat de la requête = 0`. */
  function ruleOf(k) {
    var subject = k.type === "sql" ? "query result" : (k.metric || "value"), out = [];
    Object.keys(OPS).forEach(function (op) { if (k[op] != null) out.push(subject + " " + OPS[op] + " " + k[op]); });
    if (k.mustBeBetween) out.push(subject + " between " + k.mustBeBetween[0] + " and " + k.mustBeBetween[1]);
    return out.join(" ; ");
  }
  /* Bloc "Contrôles qualité" de l'onglet Model info (remplace le bloc natif, vide). */
  window.cpModelTestsHtml = function (ts) {
    return '<div class="cp-tests">' + (ts || []).map(function (t) {
      var k = t.kwargs || {}, sev = t.config && t.config.severity, r = ruleOf(k);
      return '<div class="cp-test"><div><b>' + esc(t.name) + "</b> " + badge(k.dimension || "check") +
        (sev ? badge(sev, sev === "error" ? "hi" : sev === "warning" ? "mid" : "") : "") + "</div>" +
        (k.description ? "<div>" + esc(k.description) + "</div>" : "") +
        (r ? '<div class="cp-note">Rule: ' + esc(r) + "</div>" : "") +
        (k.query ? sql(k.query, "Check query") : "") + "</div>";
    }).join("") + "</div>";
  };

  /* ---------- Onglet "Trace" : pour la colonne choisie dans la liste, un bloc (classification,
     description et SQL, champs sources, transformations par table), puis en option (replie) l'arbre
     "qui alimente quoi" jusqu'aux systemes sources des raw, et le detail de la ligne choisie.
     Une colonne amont n'est depliee qu'une fois (diamants, cycles). Les contrats ne sont pas tous
     documentes de la meme facon : une etape sans description est signalee. ---------- */
  var PARENTS = null;
  var TRACE_MAX = 400; /* garde-fou : contrat tres large */
  var SEP = "\u001f";

  /* Index des colonnes amont, construit une seule fois depuis les aretes colonne a colonne. */
  function parentsIndex() {
    if (PARENTS) return PARENTS;
    PARENTS = {};
    (((data().lineage || {}).edges) || []).forEach(function (e) {
      if (!e.sourceColumn || !e.targetColumn) return; /* arete de contrat a contrat */
      var k = e.target + SEP + e.targetColumn;
      var list = PARENTS[k] || (PARENTS[k] = []);
      for (var i = 0; i < list.length; i++) if (list[i].c === e.source && list[i].col === e.sourceColumn) return;
      list.push({ c: e.source, col: e.sourceColumn });
    });
    return PARENTS;
  }
  function parentsOf(c, col) { return parentsIndex()[c + SEP + col] || []; }
  function metaOf(c, col) { return (((data().nodes[c] || {}).columns || {})[col] || {}).meta || {}; }
  /* Recopie ("map") ou colonne sans rien de declare : grisee, non comptee comme transformation. */
  function isCopy(m) { return m.transformLogic === "map" || (!m.transformLogic && !m.transformDescription); }
  function plural(n, word) { return n + " " + word + (n > 1 ? "s" : ""); }
  function nodeAttrs(c, col) { return ' data-cp-node-model="' + esc(c) + '" data-cp-node-col="' + esc(col) + '"'; }

  /* Ligne de l'arbre (et du detail) : un bouton qui selectionne la colonne. */
  function nodeButton(c, col, cls, extra) {
    var m = metaOf(c, col);
    return '<button type="button" class="' + cls + (isCopy(m) ? " cp-copy" : "") + '"' + nodeAttrs(c, col) + ">" +
      '<span class="cp-nc">' + esc(c) + '</span> <span class="cp-hopcol">' + esc(col) + "</span> " +
      (m.transformLogic ? badge(m.transformLogic) : "") +
      (m.transformDescription ? "" : '<span class="cp-note">not documented</span>') + (extra || "") + "</button>";
  }
  function external(m, cls) {
    return (m.externalSources || []).map(function (x) { return '<div class="' + cls + '">' + esc(x) + "</div>"; }).join("");
  }
  /* Parcours en profondeur depuis la colonne choisie. `walk` cumule les colonnes deja depliees,
     le nombre de lignes et les compteurs de l'en-tete. */
  function treeNode(c, col, picked, walk) {
    if (walk.lines >= TRACE_MAX) { walk.truncated = true; return ""; }
    walk.lines++;
    var key = c + SEP + col, cls = "cp-node" + (key === picked ? " cp-on" : "");
    if (walk.seen[key]) return "<li>" + nodeButton(c, col, cls + " cp-ref", ' <span class="cp-note">shown above</span>') + "</li>";
    walk.seen[key] = 1;
    if (!walk.root) walk.root = key;
    var m = metaOf(c, col), ps = parentsOf(c, col);
    if (!m.transformDescription) walk.undocumented++;
    if (key !== walk.root && rankOf(m.classification) > rankOf(walk.highest)) walk.highest = m.classification;
    var raw = (data().nodes[c] || {}).nodeType === "source";
    if (m.externalSources) m.externalSources.forEach(function (x) { addSource(walk, c, col, x); });
    else if (raw && !ps.length && m.transformLogic !== "create") addField(walk, c, col, c, col);
    var line = nodeButton(c, col, cls);
    var step = { c: c, col: col, m: m };
    if (!ps.length) {
      if (!isCopy(m)) walk.steps.push(step);
      return "<li>" + line + external(m, "cp-ext") + "</li>";
    }
    var kids = ps.map(function (p) { return treeNode(p.c, p.col, picked, walk); }).join("");
    if (!isCopy(m)) walk.steps.push(step); /* apres ses entrees : ordre sources -> resultat */
    return "<li><details open><summary>" + line + "</summary>" + external(m, "cp-ext") + "<ul>" + kids + "</ul></details></li>";
  }
  /* Detail de la ligne choisie : description, SQL, entrees directes (toutes), sources externes. */
  function detailHtml(c, col) {
    var m = metaOf(c, col), ps = parentsOf(c, col);
    var h = '<div class="cp-dtitle">' + esc(c + "." + col) + "</div>" +
      (m.transformLogic ? "<div>" + badge(m.transformLogic) + "</div>" : "") +
      (m.transformDescription ? "<div>" + esc(m.transformDescription) + "</div>"
        : '<div class="cp-note">Transformation not documented</div>') +
      (m.transformExpression ? sql(m.transformExpression, "Transformation SQL") : "");
    if (ps.length) {
      h += '<div class="cp-h">Inputs · ' + ps.length + "</div>" +
        ps.map(function (p) { return nodeButton(p.c, p.col, "cp-input"); }).join("");
    }
    if (m.externalSources) h += '<div class="cp-h">Source system</div>' + external(m, "cp-ext-detail");
    return h;
  }
  function rankOf(level) { return ["C0", "C1", "C2", "C3"].indexOf(level); }
  function levelBadge(level, pii) {
    if (!level) return '<span class="cp-badge">unclassified</span>';
    return badge(level + (pii ? " · pii" : ""), level === "C3" ? "hi" : level === "C2" ? "mid" : "");
  }
  /* Champ source d'une colonne raw, avec la classification et le marquage PII de cette colonne. */
  function addField(walk, c, col, system, field) {
    var column = ((data().nodes[c] || {}).columns || {})[col] || {};
    walk.sources.push({ level: (column.meta || {}).classification || "", pii: (column.tags || []).indexOf("pii") >= 0,
      system: system, field: field });
  }
  function addSource(walk, c, col, ref) {
    var parts = String(ref).split("#");
    addField(walk, c, col, parts[0], parts[1] || "");
  }
  /* Champs sources par niveau puis systeme, les plus sensibles d'abord. C1 et C0 sont replies quand
     il y a plus sensible a montrer ; un champ sans classification ne l'est jamais. */
  function sourcesHtml(walk) {
    var groups = {}, low = 0;
    walk.sources.forEach(function (f) {
      var rank = f.level ? rankOf(f.level) : 1.5; /* non classe : visible, apres C2 */
      var key = [9 - rank, f.pii ? 0 : 1, f.system].join(SEP);
      var g = groups[key] || (groups[key] = { f: f, fields: [] });
      if (g.fields.indexOf(f.field) < 0) g.fields.push(f.field);
    });
    var shown = "", folded = "";
    Object.keys(groups).sort().forEach(function (key) {
      var g = groups[key], line = "<div>" + levelBadge(g.f.level, g.f.pii) + "<b>" + esc(g.f.system) + "</b> " +
        esc(g.fields.join(", ")) + "</div>";
      if (g.f.level === "C1" || g.f.level === "C0") { folded += line; low += g.fields.length; } else shown += line;
    });
    if (!shown) return folded;
    return shown + (folded ? acc("C1 and lower · " + plural(low, "field"), folded, false) : "");
  }
  function columnOf(c, col) { return ((data().nodes[c] || {}).columns || {})[col] || {}; }
  /* Identifiant de la table (projet.dataset.table) et colonne. Un contrat a plusieurs tables a une
     relation "{a,b}" et des colonnes "<table>.<champ>". Sans relation : l'identifiant du contrat. */
  function tableRef(c, col) {
    var relation = (data().nodes[c] || {}).relationName;
    if (!relation) return { table: c, column: col };
    if (relation.indexOf("{") < 0) return { table: relation, column: col };
    var parts = String(col).split("."), object = parts.shift();
    return { table: relation.replace(/\{.*\}/, function () { return object; }), column: parts.join(".") };
  }
  /* Entrees directes d'une colonne : une ligne par table puis ses colonnes, et les sources externes. */
  function sourceObjectsHtml(c, col) {
    var byTable = {}, tables = [];
    parentsOf(c, col).forEach(function (p) {
      var ref = tableRef(p.c, p.col);
      if (!byTable[ref.table]) { byTable[ref.table] = []; tables.push(ref.table); }
      byTable[ref.table].push(ref.column);
    });
    var lines = tables.map(function (table) { return table + ": " + byTable[table].join(", "); })
      .concat(metaOf(c, col).externalSources || []);
    return lines.length ? '<div class="cp-from">' + lines.map(function (line) { return "<div>" + esc(line) + "</div>"; }).join("") + "</div>"
      : '<div class="cp-note">none</div>';
  }
  /* Les trois champs de transformation du contrat, nommes et toujours presents, pour la colonne
     choisie comme pour chaque etape : rien n'est masque, l'absence est dite. */
  function transformationHtml(c, col) {
    var m = metaOf(c, col), missing = '<div class="cp-note">not declared</div>';
    function field(name, body) { return '<div class="cp-fname">' + name + "</div>" + body; }
    return field("transformDescription", m.transformDescription ? "<div>" + esc(m.transformDescription) + "</div>" : missing) +
      field("transformExpression", m.transformExpression ? sql(m.transformExpression, "Transformation SQL") : missing) +
      field("transformSourceObjects", sourceObjectsHtml(c, col));
  }
  function logicBadge(m) { return m.transformLogic ? badge(m.transformLogic) : ""; }
  /* Une etape amont : colonne, classification, description, entrees (la table est le titre du groupe). */
  function stepHtml(s) {
    return '<div class="cp-step"><div><span class="cp-hopcol">' + esc(tableRef(s.c, s.col).column) + "</span> " +
      levelBadge(s.m.classification) + logicBadge(s.m) + "</div>" + transformationHtml(s.c, s.col) + "</div>";
  }
  /* Mots a surligner : la colonne choisie et les champs cites par son SQL (ni mots-cles ni fonctions). */
  function wordsOf(col, expression) {
    var words = [String(col).split(".").pop()], re = /('(?:[^'\\]|\\.)*')|\b([A-Za-z_][A-Za-z0-9_]*)\b(\s*\()?/g, m;
    while ((m = re.exec(expression || ""))) if (m[2] && !m[3] && !KW[m[2].toUpperCase()]) words.push(m[2]);
    return new RegExp("\\b(" + words.join("|") + ")\\b");
  }
  /* Requete declaree par une table (customProperties.transformInputs), entiere. C'est la que se
     lisent jointures et filtres. */
  function queryHtml(id, words) {
    var n = data().nodes[id] || {}, query = ((n.meta || {}).customProperties || {}).transformInputs;
    if (!query) return "";
    copies.push(String(query));
    return '<div class="cp-sql"><div class="cp-sqlbar"><span>' + esc(n.relationName || id) + '</span><button class="cp-btn" data-cp-copy="' + (copies.length - 1) +
      '">Copy</button></div><pre><code>' + String(query).split("\n").map(function (line) {
        return '<span class="cp-line' + (words.test(line) ? " cp-hit" : "") + '">' + (hl(line) || " ") + "</span>";
      }).join("") + "</code></pre></div>";
  }
  /* Bloc resume, assemble sans rien reformuler : la colonne choisie et sa classification (declaree,
     et la plus haute en amont), les champs sources, puis les transformations par table, de la plus
     proche a la plus lointaine. */
  function summaryHtml(model, col, walk) {
    var m = metaOf(model, col), words = wordsOf(col, m.transformExpression);
    var h = '<div class="cp-dtitle">' + esc(col) + ' <span class="cp-note">' + esc(tableRef(model, col).table) + "</span></div>" +
      "<div>Declared: " + levelBadge(m.classification) +
      (walk.highest ? " Highest upstream: " + levelBadge(walk.highest) +
        '<div class="cp-note">Upstream includes fields used only for joins or filters.</div>' : "") + "</div>" +
      (columnOf(model, col).description ? "<div>" + esc(columnOf(model, col).description) + "</div>" : "") +
      '<div class="cp-h">Transformation ' + logicBadge(m) + "</div>" + transformationHtml(model, col);
    /* Colonne sans amont ni source externe : l'avertissement au-dessus du bloc suffit. */
    var traced = parentsOf(model, col).length || m.externalSources;
    var sources = traced ? sourcesHtml(walk) : "";
    if (sources) h += '<div class="cp-h">Sources</div>' + sources;
    var byTable = {}, ids = [];
    walk.steps.slice().reverse().forEach(function (s) {
      if (s.c === model && s.col === col) return;
      if (!byTable[s.c]) { byTable[s.c] = []; ids.push(s.c); }
      byTable[s.c].push(s);
    });
    if (ids.length) {
      h += '<div class="cp-h">Transformations</div>' + ids.map(function (id) {
        return '<div class="cp-table">' + esc(tableRef(id, byTable[id][0].col).table) + "</div>" +
          byTable[id].map(stepHtml).join("");
      }).join("");
    }
    if (traced && !walk.steps.length) h += '<div class="cp-note">No transformation declared: plain copies only.</div>';
    if (traced && walk.undocumented) h += '<div class="cp-note">' + plural(walk.undocumented, "step") + " not documented</div>";
    /* Un seul bloc replie pour le SQL des tables : celle du resultat, puis les tables amont. */
    var queries = [model].concat(ids.filter(function (id) { return id !== model; }))
      .map(function (id) { return queryHtml(id, words); }).join("");
    if (queries) {
      h += '<details class="cp-acc cp-query"><summary>Full table SQL</summary><div class="cp-in">' + queries + "</div></details>";
    }
    return '<div class="cp-summary">' + h + "</div>";
  }
  /* Colonne choisie : compteurs, resume, puis en option l'arbre et le detail. `node` est la ligne
     choisie dans l'arbre, absente tant qu'on n'a rien clique. */
  function traceBodyHtml(model, col, node) {
    var walk = { seen: {}, sources: [], steps: [], lines: 0, undocumented: 0, truncated: false, root: "", highest: "" };
    var shown = node || { c: model, col: col };
    var tree = treeNode(model, col, shown.c + SEP + shown.col, walk);
    var m = metaOf(model, col), why = "";
    if (!parentsOf(model, col).length && !m.externalSources) {
      why = '<div class="cp-note">' + (m.transformLogic === "create"
        ? "Created in this contract, no upstream source." : "No upstream lineage declared for this column.") + "</div>";
    }
    return why +
      (walk.truncated ? '<div class="cp-note cp-truncated">Trace truncated at ' + TRACE_MAX + " lines.</div>" : "") +
      summaryHtml(model, col, walk) +
      '<details class="cp-deep"' + (node ? " open" : "") + '><summary>Lineage tree</summary>' +
      '<div class="cp-split"><div class="cp-tree"><ul>' + tree + '</ul></div><div class="cp-detail">' +
      detailHtml(shown.c, shown.col) + "</div></div></details>";
  }
  /* Liste des colonnes du contrat (selecteur de l'onglet), avec leur classification declaree. */
  function traceListHtml(model, sel) {
    var cols = Object.keys(data().nodes[model].columns || {});
    return '<nav class="cp-cols"><div class="cp-colhead"><b>' + esc(model) + '</b><span class="cp-note">' +
      plural(cols.length, "column") + "</span></div>" +
      cols.map(function (c) {
        var level = metaOf(model, c).classification;
        return '<button type="button" class="cp-colbtn' + (c === sel ? " cp-on" : "") + '" data-cp-model="' + esc(model) +
          '" data-cp-col="' + esc(c) + '"><span>' + esc(c) + "</span>" +
          (level ? '<span class="cp-t">' + levelBadge(level) + "</span>" : "") + "</button>";
      }).join("") + "</nav>";
  }
  var TRACE_SEL = {}; /* contrat -> colonne selectionnee dans la liste des colonnes du panneau */
  var TRACE_NODE = {}; /* contrat + colonne -> ligne de l'arbre choisie (racine par defaut) */
  var SHOWN = null; /* contrat et colonne du dernier arbre rendu */
  var TRACE_MODEL = null; /* dernier contrat connu (clic de colonne) : la carte de colonnes de la
     vue lineage garde son propre etat interne, le rendu React du panneau peut donc rester sur un
     contrat absent. Sans ce repli, le panneau afficherait une invite vide. */
  /* Contrat affiche : la selection React, sinon le dernier contrat clique, sinon l'URL (?model=)
     que colibri met a jour. */
  function traceModelOf(model) {
    if (model) return model;
    if (TRACE_MODEL) return TRACE_MODEL;
    try {
      var p = new URLSearchParams((window.location || {}).search || "").get("model");
      if (p && data().nodes[p]) return p;
    } catch (e) { /* pas de window.location hors navigateur */ }
    return null;
  }
  /* Appele par la liste de l'onglet Trace et par la liste des colonnes du panneau du contrat
     (voir catalog_template.py) : met a jour l'onglet sans attendre un re-rendu React. */
  window.cpTraceColumnSet = function (model, col) {
    if (!model) return;
    TRACE_MODEL = model;
    TRACE_SEL[model] = col;
    delete TRACE_NODE[model + SEP + col];
    var panel = document.getElementById && document.getElementById("cp-trace-panel");
    if (!panel) return;
    var list = panel.querySelector(".cp-cols"), top = list ? list.scrollTop : 0;
    panel.innerHTML = window.cpTraceTabHtml(model);
    list = panel.querySelector(".cp-cols");
    if (list) list.scrollTop = top;
  };
  /* Clic sur une ligne de l'arbre : seuls le detail et le surlignage changent, l'arbre n'est pas
     redessine (les branches repliees le restent). */
  window.cpTraceNodeSet = function (c, col) {
    if (!SHOWN) return;
    TRACE_NODE[SHOWN] = { c: c, col: col };
    var panel = document.getElementById && document.getElementById("cp-trace-panel");
    var detail = panel && panel.querySelector(".cp-detail");
    if (!detail) return;
    detail.innerHTML = detailHtml(c, col);
    detail.scrollTop = 0;
    Array.prototype.forEach.call(panel.querySelectorAll(".cp-node"), function (b) {
      b.classList.toggle("cp-on", b.getAttribute("data-cp-node-model") === c && b.getAttribute("data-cp-node-col") === col);
    });
  };
  /* Onglet "Trace" : liste des colonnes a gauche, arbre et detail de la colonne choisie a droite.
     Aucune exception ne remonte : une erreur ne doit pas faire tomber tout le rendu React. */
  window.cpTraceTabHtml = function (model) {
    try {
      SHOWN = null;
      model = traceModelOf(model);
      var n = model && data().nodes[model];
      if (!n) return '<div class="cp-trace"><div class="cp-note">Select a contract to see its source trace.</div></div>';
      var sel = TRACE_SEL[model];
      if (!(n.columns || {})[sel]) sel = null;
      var body = '<div class="cp-note">Select a column to see what feeds it, down to the source systems.</div>';
      if (sel) {
        SHOWN = model + SEP + sel;
        body = traceBodyHtml(model, sel, TRACE_NODE[SHOWN]);
      }
      return '<div class="cp-trace">' + traceListHtml(model, sel) + '<div class="cp-chain"><div class="cp-h">Source trace · ' +
        esc(model) + "</div>" + body + "</div></div>";
    } catch (e) {
      return '<div class="cp-trace"><div class="cp-note">Source trace unavailable: ' + esc(e && e.message) + "</div></div>";
    }
  };

  function expertBlock(model, name, c, m) {
    var ex = "";
    if (c.tests && c.tests.length) ex += "<div><b>Quality checks</b></div>" + tests(c.tests);
    return ex ? '<div class="cp-expert-only">' + ex + "</div>" : "";
  }
  function typesLine(c) {
    return kv([["Logical type", esc(c.contractType)], ["Physical type", esc(c.dataType)]]);
  }
  function flagsOf(c) {
    var m = c.meta || {}, f = sens(c);
    if (m.primaryKey) f += badge("primary key" + (m.primaryKeyPosition ? " " + m.primaryKeyPosition : ""));
    return f ? "<div>" + f + "</div>" : "";
  }

  /* Fiche de colonne du panneau lateral : type et classification seulement. */
  window.cpColumnHtml = function (model, name) {
    var n = data().nodes[model], c = n && n.columns && n.columns[name];
    if (!c) return "";
    return '<div class="cp-col">' + flagsOf(c) + typesLine(c) + expertBlock(model, name, c, c.meta || {}) + "</div>";
  };

  /* Ligne depliee de l'onglet Columns : types, classification, transformation (description et SQL). */
  window.cpColumnTabHtml = function (model, name) {
    var n = data().nodes[model], c = n && n.columns && n.columns[name];
    if (!c) return "";
    var m = c.meta || {}, x = '<div class="cp-h">Types</div>' + typesLine(c);
    if (m.transformDescription || m.transformExpression) {
      x += '<div class="cp-h">Transformation</div>';
      if (m.transformDescription) x += "<div>" + esc(m.transformDescription) + "</div>";
      if (m.transformExpression) x += sql(m.transformExpression, "BigQuery SQL");
    }
    /* Types et transformation (SQL) : visibles uniquement en mode expert. La classification reste visible. */
    var ex = x;
    if (c.tests && c.tests.length) ex += "<div><b>Quality checks</b></div>" + tests(c.tests);
    return '<div class="cp-col cp-tab">' + flagsOf(c) + '<div class="cp-expert-only">' + ex + "</div></div>";
  };

  /* Valeurs du bloc "BigQuery schema" : type de l'objet et strategie de chargement, lus dans le contrat. */
  window.cpObjectType = function (model) {
    var n = data().nodes[model], m = (n && n.meta) || {};
    return m.objectType || "N/A";
  };
  var STRATEGY = { full_refresh: "Full refresh", incremental: "Incremental", append: "Append" };
  window.cpLoadStrategy = function (model) {
    var n = data().nodes[model], m = (n && n.meta) || {};
    if (!m.loadStrategy) return "Not specified";
    return (STRATEGY[m.loadStrategy] || m.loadStrategy) + (m.incrementalKey ? " (key: " + m.incrementalKey + ")" : "");
  };

  window.cpNodeHtml = function (model) {
    var n = data().nodes[model];
    if (!n) return "";
    var m = n.meta || {}, dp = m.descriptionParts || {}, h = "";
    h += '<div>' + badge("v" + (m.contractVersion || "?")) + badge(m.contractStatus || "?", m.contractStatus === "active" ? "ok" : "") + badge(m.domain || "") + "</div>";
    h += kv([["Team", esc(m.team)], ["Usage", esc(dp.usage)], ["Limitations", esc(dp.limitations)]]);
    var sla = (m.slaProperties || []).map(function (s) {
      return "<b>" + esc(s.property) + "</b> " + esc(s.value) + " " + esc(s.unit || "") + (s.element ? " (" + esc(s.element) + ")" : "");
    });
    if (sla.length) h += acc("SLA", list(sla), false);
    var sup = (m.support || []).map(function (s) { return esc((s.channel || "") + " " + (s.url || "")); });
    if (sup.length) h += acc("Support", list(sup), false);
    return '<div class="cp-card">' + h + "</div>";
  };
})();

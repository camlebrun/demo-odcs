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

  /* ---------- Onglet "Trace" : pour le contrat selectionne, toutes les modifications, des
     contrats raw (sources) jusqu'a lui. Une colonne amont n'est listee qu'une fois (diamants,
     cycles bornes), les contrats sont groupes par couche (raw, core, customer) dans le sens
     source -> contrat. Les contrats ne sont pas tous documentes de la meme facon : une etape
     sans transformation est signalee comme telle. ---------- */
  var PARENTS = null;
  var LAYER_RANK = { raw: 0, core: 1, customer: 2 };
  var TRACE_MAX = 400; /* garde-fou : contrat tres large ou lineage cyclique */

  /* Index des colonnes amont, construit une seule fois depuis les aretes colonne a colonne. */
  function parentsIndex() {
    if (PARENTS) return PARENTS;
    PARENTS = {};
    (((data().lineage || {}).edges) || []).forEach(function (e) {
      if (!e.sourceColumn || !e.targetColumn) return; /* arete de contrat a contrat */
      var k = e.target + "\u001f" + e.targetColumn;
      var list = PARENTS[k] || (PARENTS[k] = []);
      for (var i = 0; i < list.length; i++) if (list[i].c === e.source && list[i].col === e.sourceColumn) return;
      list.push({ c: e.source, col: e.sourceColumn });
    });
    return PARENTS;
  }
  function layerOf(id) {
    var n = data().nodes[id] || {};
    if (n.nodeType === "source") return "raw";
    return String(id).indexOf("core__") === 0 ? "core" : "customer";
  }
  /* Union des colonnes amont de plusieurs colonnes (celles du contrat selectionne),
     de la source (premiere) au contrat (dernier). */
  function traceSteps(seeds) {
    var seen = {}, steps = [], queue = [];
    seeds.forEach(function (s) {
      seen[s.c + "\u001f" + s.col] = 1;
      queue.push({ c: s.c, col: s.col, d: 0 });
    });
    while (queue.length && steps.length < TRACE_MAX) {
      var cur = queue.shift(), ps = parentsIndex()[cur.c + "\u001f" + cur.col] || [];
      steps.push(cur);
      for (var i = 0; i < ps.length && steps.length < TRACE_MAX; i++) {
        var k = ps[i].c + "\u001f" + ps[i].col;
        if (seen[k]) continue; /* diamant ou cycle : la colonne n'est listee qu'une fois */
        seen[k] = 1;
        queue.push({ c: ps[i].c, col: ps[i].col, d: cur.d + 1 });
      }
    }
    return steps.sort(function (a, b) {
      var ra = LAYER_RANK[layerOf(a.c)], rb = LAYER_RANK[layerOf(b.c)];
      return ra !== rb ? ra - rb : b.d - a.d;
    });
  }
  /* Colonne de la trace : nom, logique et transformation declaree du contrat qui la produit. */
  function traceColumnHtml(step, showFrom) {
    var n = data().nodes[step.c] || {}, c = (n.columns || {})[step.col] || {}, m = c.meta || {};
    var ps = showFrom ? parentsIndex()[step.c + "\u001f" + step.col] || [] : [];
    var h = '<li class="cp-tracecol"><div class="cp-stepline">' +
      '<span class="cp-hopcol">' + esc(step.col) + "</span>" + (m.transformLogic ? badge(m.transformLogic) : "") + "</div>";
    if (ps.length) {
      h += '<div class="cp-note">from ' + ps.slice(0, 8).map(function (p) { return esc(p.c + "#" + p.col); }).join(", ") +
        (ps.length > 8 ? " +" + (ps.length - 8) : "") + "</div>";
    }
    h += m.transformDescription ? '<div class="cp-hopdesc">' + esc(m.transformDescription) + "</div>"
      : '<div class="cp-note">Transformation not documented</div>';
    if (m.transformExpression) h += acc("SQL", sql(m.transformExpression, "Transformation SQL"), false);
    return h + "</li>";
  }
  /* Onglet "Trace" : trace du contrat selectionne. Aucune exception ne remonte : une erreur ne
     doit pas faire tomber tout le rendu React (page blanche). */
  window.cpTraceTabHtml = function (model) {
    try {
      var n = data().nodes[model];
      if (!n) return '<div class="cp-trace"><div class="cp-note">Select a contract to see its source trace.</div></div>';
      var head = '<div class="cp-trace"><div class="cp-h">Source trace · ' + esc(model) + "</div>";
      if (n.nodeType === "source") {
        return head + '<div class="cp-note">Raw contract: no upstream in the catalog; its sources are the external systems documented in each column.</div></div>';
      }
      var cols = Object.keys(n.columns || {});
      var steps = traceSteps(cols.map(function (c) { return { c: model, col: c }; }));
      var upstream = steps.filter(function (s) { return s.d > 0; });
      if (!upstream.length) {
        return head + '<div class="cp-note">No upstream lineage declared for this contract.</div></div>';
      }
      /* Un groupe par contrat, dans l'ordre des couches : la concatenation reste courte meme
         quand le contrat brasse tout le lineage (une colonne amont n'apparait qu'une fois). */
      var groups = [], byContract = {};
      steps.forEach(function (s) {
        var g = byContract[s.c] || (byContract[s.c] = { c: s.c, steps: [] });
        if (!g.steps.length) groups.push(g);
        g.steps.push(s);
      });
      var h = head + '<div class="cp-note">' + upstream.length + " upstream column" + (upstream.length > 1 ? "s" : "") +
        " · " + groups.length + " contracts</div>" + '<ol class="cp-steps">';
      groups.forEach(function (g) {
        var ly = layerOf(g.c);
        h += '<li class="cp-step"><div class="cp-stepline">' + badge(ly, ly === "raw" ? "mid" : ly === "customer" ? "ok" : "") +
          "<b>" + esc(g.c) + "</b>" + '<span class="cp-note">' + g.steps.length + (g.steps.length > 1 ? " columns" : " column") +
          '</span></div><ul class="cp-cols">';
        g.steps.forEach(function (s) { h += traceColumnHtml(s, s.d === 0); });
        h += "</ul></li>";
      });
      return h + "</ol></div>";
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

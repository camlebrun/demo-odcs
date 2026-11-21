/* Contenu ajoute au panneau natif "Model info" du catalogue : types, transformation SQL,
   mode expert. Lit window.colibriData (genere depuis les data contracts). Aucun appel reseau. */
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
    if (navigator.clipboard && txt != null) navigator.clipboard.writeText(txt).then(function () { b.textContent = "Copié"; });
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
      (copies.length - 1) + '">Copier</button></div><pre><code>' + hl(text) + "</code></pre></div>";
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
    return items.length ? '<ul class="cp-list">' + items.map(function (i) { return "<li>" + i + "</li>"; }).join("") + "</ul>" : '<span class="cp-note">Aucun</span>';
  }
  var LEVEL = { C0: "public", C1: "interne", C2: "confidentiel", C3: "restreint" };
  function sens(c) {
    var m = c.meta || {}, t = c.tags || [], h = "";
    if (m.classification) h += badge(LEVEL[m.classification] ? m.classification + " · " + LEVEL[m.classification] : m.classification, m.classification === "C3" ? "hi" : m.classification === "C2" ? "mid" : "");
    if (t.indexOf("pii") >= 0) h += badge("PII", "hi");
    if (t.indexOf("pseudonymized") >= 0) h += badge("pseudonymisé", "mid");
    if (t.indexOf("pii_potential") >= 0) h += badge("PII potentielle", "mid");
    return h;
  }
  function tests(ts) {
    return (ts || []).map(function (t) {
      var k = t.kwargs || {};
      return "<div><b>" + esc(t.name) + "</b> " + badge(k.dimension || "contrôle") + (t.config && t.config.severity ? badge(t.config.severity) : "") +
        (k.description ? '<div class="cp-note">' + esc(k.description) + "</div>" : "") +
        (k.query ? sql(k.query, "Requête de contrôle") : "") + "</div>";
    }).join("");
  }

  function expertBlock(model, name, c, m) {
    var ex = kv([["transformLogic", esc(m.transformLogic)], ["lineageType", esc(c.lineageType)]]);
    if (c.tests && c.tests.length) ex += "<div><b>Contrôles qualité</b></div>" + tests(c.tests);
    return ex ? '<div class="cp-expert-only">' + ex + "</div>" : "";
  }
  function typesLine(c) {
    return kv([["Type logique", esc(c.contractType)], ["Type physique", esc(c.dataType)]]);
  }
  function flagsOf(c) {
    var m = c.meta || {}, f = sens(c);
    if (m.primaryKey) f += badge("clé primaire" + (m.primaryKeyPosition ? " " + m.primaryKeyPosition : ""));
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
      if (m.transformExpression) x += sql(m.transformExpression, "SQL BigQuery");
    }
    /* Types et transformation (SQL) : visibles uniquement en mode expert. La classification reste visible. */
    var ex = x + (kv([["transformLogic", esc(m.transformLogic)], ["lineageType", esc(c.lineageType)]]) || "");
    if (c.tests && c.tests.length) ex += "<div><b>Contrôles qualité</b></div>" + tests(c.tests);
    return '<div class="cp-col cp-tab">' + flagsOf(c) + '<div class="cp-expert-only">' + ex + "</div></div>";
  };

  window.cpNodeHtml = function (model) {
    var n = data().nodes[model];
    if (!n) return "";
    var m = n.meta || {}, dp = m.descriptionParts || {}, h = "";
    h += '<div>' + badge("v" + (m.contractVersion || "?")) + badge(m.contractStatus || "?", m.contractStatus === "active" ? "ok" : "") + badge(m.domain || "") + "</div>";
    h += kv([["Équipe", esc(m.team)], ["Usage", esc(dp.usage)], ["Limites", esc(dp.limitations)]]);
    var sla = (m.slaProperties || []).map(function (s) {
      return "<b>" + esc(s.property) + "</b> " + esc(s.value) + " " + esc(s.unit || "") + (s.element ? " (" + esc(s.element) + ")" : "");
    });
    if (sla.length) h += acc("SLA", list(sla), false);
    var sup = (m.support || []).map(function (s) { return esc((s.channel || "") + " " + (s.url || "")); });
    if (sup.length) h += acc("Support", list(sup), false);
    return '<div class="cp-card">' + h + "</div>";
  };
})();

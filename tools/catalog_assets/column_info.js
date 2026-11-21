/* Contenu ajoute au panneau natif "Model info" du catalogue : types, transformation SQL,
   mode expert. Lit window.colibriData (genere depuis les data contracts). Aucun appel reseau. */
(function () {
  "use strict";
  var KEY = "catalog.expert";
  function get() { try { return localStorage.getItem(KEY); } catch (e) { return null; } }
  function set(v) { try { localStorage.setItem(KEY, v); } catch (e) { /* non memorise */ } }
  if (get() === "1") document.documentElement.classList.add("cp-expert");
  window.cpToggleExpert = function () {
    var on = document.documentElement.classList.toggle("cp-expert");
    set(on ? "1" : "0");
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
  function sens(c) {
    var m = c.meta || {}, t = c.tags || [], h = "";
    if (m.classification) h += badge(m.classification, m.classification === "restricted" ? "hi" : m.classification === "confidential" ? "mid" : "");
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
        (t.compiled_code ? sql(t.compiled_code, "Requête de contrôle") : "") + "</div>";
    }).join("");
  }
  function from(id, col) {
    return data().lineage.edges.filter(function (e) { return e.target === id && e.targetColumn === col && e.sourceColumn; })
      .map(function (e) { return esc(e.source + " . " + e.sourceColumn); });
  }
  function to(id, col) {
    return data().lineage.edges.filter(function (e) { return e.source === id && e.sourceColumn === col && e.targetColumn; })
      .map(function (e) { return esc(e.target + " . " + e.targetColumn); });
  }
  function links(id, dir) {
    var seen = {};
    return data().lineage.edges.filter(function (e) {
      if (e.sourceColumn || e.targetColumn) return false;
      var k = dir === "up" ? (e.target === id ? e.source : null) : (e.source === id ? e.target : null);
      if (!k || seen[k]) return false;
      seen[k] = 1;
      return true;
    }).map(function (e) { return esc(dir === "up" ? e.source : e.target); });
  }

  window.cpColumnHtml = function (model, name) {
    var n = data().nodes[model], c = n && n.columns && n.columns[name];
    if (!c) return "";
    var m = c.meta || {}, h = "";
    var flags = sens(c);
    if (m.primaryKey) flags += badge("clé primaire" + (m.primaryKeyPosition ? " " + m.primaryKeyPosition : ""));
    if (flags) h += "<div>" + flags + "</div>";
    h += acc("Types", kv([["Type logique", esc(c.contractType)], ["Type physique", esc(c.dataType)]]), false);
    if (m.transformDescription) h += '<div class="cp-note">' + esc(m.transformDescription) + "</div>";
    if (m.transformExpression) h += acc("SQL de transformation", sql(m.transformExpression, "BigQuery"), false);
    var ex = kv([
      ["transformLogic", esc(m.transformLogic)], ["lineageType", esc(c.lineageType)], ["classification", esc(m.classification)],
      ["obligatoire", m.required ? "oui" : ""], ["unique", m.unique ? "oui" : ""], ["tags", esc((c.tags || []).join(", "))]
    ]);
    ex += '<div><b>Sources</b></div>' + list(from(model, name));
    ex += '<div><b>Utilisé par</b></div>' + list(to(model, name));
    if (c.tests && c.tests.length) ex += "<div><b>Contrôles qualité</b></div>" + tests(c.tests);
    var rest = {};
    Object.keys(m).forEach(function (k) { if (["transformExpression", "transformDescription"].indexOf(k) < 0) rest[k] = m[k]; });
    ex += '<pre class="cp-json">' + esc(JSON.stringify(rest, null, 2)) + "</pre>";
    h += '<div class="cp-expert-only">' + ex + "</div>";
    return '<div class="cp-col">' + h + "</div>";
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
    var up = links(model, "up"), down = links(model, "down");
    if (up.length || down.length) h += acc("Alimenté par et alimente", "<b>Alimenté par</b>" + list(up) + "<b>Alimente</b>" + list(down), false);
    var s = Object.keys(n.columns).filter(function (k) {
      var c = n.columns[k], mm = c.meta || {}, t = c.tags || [];
      return mm.classification === "restricted" || t.indexOf("pii") >= 0 || t.indexOf("pseudonymized") >= 0 || t.indexOf("pii_potential") >= 0;
    });
    if (s.length) h += acc("Colonnes sensibles (" + s.length + ")", list(s.map(function (k) { return esc(k) + " " + sens(n.columns[k]); })), false);
    var cp = m.customProperties || {}, ex = "";
    Object.keys(cp).forEach(function (k) {
      var v = cp[k];
      ex += /SELECT/i.test(String(v)) ? sql(v, k) : kv([[k, esc(typeof v === "string" ? v : JSON.stringify(v))]]);
    });
    ex += kv([["apiVersion", esc(m.apiVersion)], ["tags", esc((n.tags || []).join(", "))], ["fichier", esc(n.path)]]);
    if (n.tests && n.tests.length) ex += "<div><b>Contrôles qualité du contrat</b></div>" + tests(n.tests);
    h += '<div class="cp-expert-only">' + ex + "</div>";
    return '<div class="cp-card">' + h + "</div>";
  };
})();

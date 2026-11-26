/* Graphe de lineage facon Obsidian (page Doc). Donnees : window.LINEAGE, ecrites par build_catalog.py. */
(function () {
  "use strict";
  var box = document.getElementById("graph"), data = window.LINEAGE;
  if (!box || !data) return;
  var NS = "http://www.w3.org/2000/svg", W = 900, H = 600;
  var info = document.getElementById("graph-info"), hint = info.textContent;
  var svg = el("svg", { viewBox: "0 0 " + W + " " + H }, box);
  var gl = el("g", {}, svg), gn = el("g", {}, svg);
  var open = {}, pos = {}, nodes = [], links = [], hover = null, drag = null, moved = false, heat = 1, running = false;

  function el(tag, attrs, parent) {
    var e = document.createElementNS(NS, tag);
    for (var k in attrs) e.setAttribute(k, attrs[k]);
    if (parent) parent.appendChild(e);
    return e;
  }

  /* Noeuds visibles : les contrats, plus les colonnes des contrats deplies. */
  function build() {
    nodes = []; links = []; gl.textContent = ""; gn.textContent = "";
    var byId = {};
    function add(id, label, kind, contract, near) {
      var p = pos[id];
      if (!p) {
        var a = nodes.length * 2.4, from = near && pos[near];
        p = pos[id] = from
          ? { x: from.x + 30 * Math.cos(a), y: from.y + 30 * Math.sin(a), vx: 0, vy: 0 }
          : { x: W / 2 + 200 * Math.cos(a), y: H / 2 + 200 * Math.sin(a), vx: 0, vy: 0 };
      }
      var n = { id: id, label: label, kind: kind, contract: contract, p: p, near: [] };
      n.g = el("g", { class: "n " + kind }, gn);
      el("circle", { r: kind === "column" ? 4 : kind === "raw" ? 9 : 13 }, n.g);
      el("text", { y: kind === "column" ? 14 : 24 }, n.g).textContent = label;
      n.g.addEventListener("pointerenter", function () { if (!drag) focus(n); });
      n.g.addEventListener("pointerleave", function () { if (!drag) focus(null); });
      n.g.addEventListener("pointerdown", function (ev) { drag = n; moved = false; svg.setPointerCapture(ev.pointerId); ev.preventDefault(); });
      nodes.push(n); byId[id] = n;
    }
    data.contracts.forEach(function (c) { add(c.id, c.id, c.layer, c.id); });
    data.contracts.forEach(function (c) {
      if (open[c.id]) c.columns.forEach(function (name) { add(c.id + "." + name, name, "column", c.id, c.id); });
    });
    var seen = {};
    function link(a, b, own) {
      var k = a.id + ">" + b.id;
      if (a === b || seen[k]) return;
      seen[k] = 1;
      var l = { a: a, b: b, own: own, line: el("line", { class: own ? "own" : "flow" }, gl) };
      links.push(l);
      if (!own) { a.near.push(b); b.near.push(a); }
    }
    nodes.forEach(function (n) { if (n.kind === "column") link(byId[n.contract], n, true); });
    /* [contrat source, colonne, contrat cible, colonne] : trait vers la colonne si elle est depliee, sinon vers le contrat. */
    data.edges.forEach(function (e) {
      link(byId[e[0] + "." + e[1]] || byId[e[0]], byId[e[2] + "." + e[3]] || byId[e[2]], false);
    });
    heat = 1; start();
  }

  /* Chemin complet en amont (dir "a") ou en aval (dir "b") d'un noeud. */
  function walk(n, dir, keep) {
    links.forEach(function (l) {
      var from = dir === "a" ? l.b : l.a, to = dir === "a" ? l.a : l.b;
      if (!l.own && from === n && !keep[to.id]) { keep[to.id] = 1; walk(to, dir, keep); }
    });
  }

  function focus(n) {
    hover = n;
    var keep = {};
    if (n) { keep[n.id] = 1; walk(n, "a", keep); walk(n, "b", keep); }
    nodes.forEach(function (m) {
      m.g.classList.toggle("dim", !!n && !keep[m.id]);
      m.g.classList.toggle("lit", !!n && !!keep[m.id]);
    });
    links.forEach(function (l) {
      l.line.classList.toggle("dim", !!n && !(keep[l.a.id] && keep[l.b.id]));
      l.line.classList.toggle("lit", !!n && !l.own && !!keep[l.a.id] && !!keep[l.b.id]);
    });
    info.textContent = n ? describe(n) : hint;
  }

  function describe(n) {
    var col = n.kind === "column";
    var from = data.edges.filter(function (e) {
      return col ? e[2] === n.contract && e[3] === n.label : e[2] === n.id;
    }).map(function (e) { return col ? e[0] + "." + e[1] : e[0]; });
    from = from.filter(function (v, i) { return from.indexOf(v) === i; });
    return (col ? n.id : n.label) + (from.length ? " ← " + from.join(", ") : "");
  }

  function step() {
    var i, j, a, b, dx, dy, d, f;
    for (i = 0; i < nodes.length; i++) {
      a = nodes[i];
      for (j = i + 1; j < nodes.length; j++) {
        b = nodes[j];
        dx = a.p.x - b.p.x || 0.1; dy = a.p.y - b.p.y || 0.1; d = dx * dx + dy * dy;
        f = (a.kind === "column" || b.kind === "column" ? 500 : 6000) / Math.max(d, 80);
        d = Math.sqrt(d);
        a.p.vx += dx / d * f; a.p.vy += dy / d * f; b.p.vx -= dx / d * f; b.p.vy -= dy / d * f;
      }
      a.p.vx += (W / 2 - a.p.x) * 0.004; a.p.vy += (H / 2 - a.p.y) * 0.006;
    }
    links.forEach(function (l) {
      dx = l.b.p.x - l.a.p.x; dy = l.b.p.y - l.a.p.y; d = Math.sqrt(dx * dx + dy * dy) || 1;
      f = (d - (l.own ? 45 : 130)) * (l.own ? 0.08 : 0.004);
      l.a.p.vx += dx / d * f; l.a.p.vy += dy / d * f; l.b.p.vx -= dx / d * f; l.b.p.vy -= dy / d * f;
    });
    nodes.forEach(function (n) {
      if (n === drag) { n.p.vx = n.p.vy = 0; return; }
      n.p.x = Math.max(40, Math.min(W - 40, n.p.x + n.p.vx * heat));
      n.p.y = Math.max(20, Math.min(H - 30, n.p.y + n.p.vy * heat));
      n.p.vx *= 0.8; n.p.vy *= 0.8;
    });
    heat = Math.max(0.02, heat * 0.99);
  }

  function draw() {
    links.forEach(function (l) {
      l.line.setAttribute("x1", l.a.p.x); l.line.setAttribute("y1", l.a.p.y);
      l.line.setAttribute("x2", l.b.p.x); l.line.setAttribute("y2", l.b.p.y);
    });
    nodes.forEach(function (n) { n.g.setAttribute("transform", "translate(" + n.p.x + "," + n.p.y + ")"); });
  }

  function loop() {
    step(); draw();
    if (heat > 0.03 || drag) requestAnimationFrame(loop); else running = false;
  }
  function start() { if (!running) { running = true; requestAnimationFrame(loop); } }

  svg.addEventListener("pointermove", function (ev) {
    if (!drag) return;
    var r = svg.getBoundingClientRect(), x = (ev.clientX - r.left) * W / r.width, y = (ev.clientY - r.top) * H / r.height;
    if (Math.abs(x - drag.p.x) + Math.abs(y - drag.p.y) > 3) moved = true;
    drag.p.x = x; drag.p.y = y; heat = Math.max(heat, 0.3); start();
  });
  svg.addEventListener("pointerup", function () {
    var n = drag; drag = null;
    if (n && !moved && n.kind !== "column") { open[n.id] = !open[n.id]; focus(null); build(); }
  });

  /* lineage.html#acquisition_monthly ouvre le graphe avec ce contrat deplie. */
  var wanted = location.hash.slice(1);
  if (data.contracts.some(function (c) { return c.id === wanted; })) open[wanted] = true;
  build();
  for (var i = 0; i < 300; i++) step();
  draw();
})();

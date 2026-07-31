/* SVDocGraph - client interactions: theme, nav filter, search palette, graph zoom */
(function () {
  "use strict";

  // ---- theme ----
  const root = document.documentElement;
  const saved = localStorage.getItem("svdg-theme");
  if (saved) root.setAttribute("data-theme", saved);
  else if (matchMedia("(prefers-color-scheme: dark)").matches)
    root.setAttribute("data-theme", "dark");
  const tt = document.getElementById("theme-toggle");
  if (tt) tt.addEventListener("click", () => {
    const next = root.getAttribute("data-theme") === "dark" ? "light" : "dark";
    root.setAttribute("data-theme", next);
    localStorage.setItem("svdg-theme", next);
  });

  // ---- sidebar filter ----
  const nf = document.getElementById("nav-filter");
  if (nf) nf.addEventListener("input", () => {
    const q = nf.value.trim().toLowerCase();
    document.querySelectorAll(".nav-group").forEach((g) => {
      let any = false;
      g.querySelectorAll(".nav-item").forEach((a) => {
        const hit = a.dataset.name.toLowerCase().includes(q);
        a.parentElement.style.display = hit ? "" : "none";
        if (hit) any = true;
      });
      g.style.display = any ? "" : "none";
    });
  });

  // ---- command palette ----
  // The index is inlined in every page so search works when the site is opened
  // straight from disk (file:// pages are not allowed to fetch design.json).
  let DATA = { modules: [], packages: [], docs: [], files: [] };
  const inline = document.getElementById("svdg-data");
  if (inline) {
    try {
      const d = JSON.parse(inline.textContent);
      if (d && d.modules) DATA = d;
    } catch (e) { /* fall through to the fetch below */ }
  }
  if (!DATA.modules.length)
    fetch("design.json").then((r) => r.json()).then((d) => { DATA = d; }).catch(() => {});

  const pal = document.getElementById("palette");
  const pin = document.getElementById("palette-input");
  const pres = document.getElementById("palette-results");
  let sel = 0, results = [];

  function openPal() { if (!pal) return; pal.hidden = false; pin.value = ""; render(""); pin.focus(); }
  function closePal() { if (pal) pal.hidden = true; }

  function score(item, q) {
    const n = item.name.toLowerCase();
    if (n === q) return 1000;
    if (n.startsWith(q)) return 500 - n.length;
    const i = n.indexOf(q);
    if (i >= 0) return 200 - i;
    if ((item.ports || []).some((p) => p.toLowerCase().includes(q))) return 60;
    return -1;
  }

  function render(q) {
    q = q.trim().toLowerCase();
    const items = [];
    for (const m of DATA.modules) {
      const s = q ? score(m, q) : (m.owned ? 1 : 0);
      if (s >= 0) items.push({ ...m, _s: s, _type: "module" });
    }
    for (const p of DATA.packages) {
      const s = q ? score({ name: p.name }, q) : -1;
      if (s >= 0) items.push({ name: p.name, url: p.url, _s: s, _type: "package" });
    }
    // The written pages match on the title, the path and the body text.
    for (const d of DATA.docs || []) {
      if (!q) continue;
      let s = score({ name: d.name }, q);
      if (s < 0 && (d.path || "").toLowerCase().includes(q)) s = 55;
      if (s < 0 && (d.text || "").toLowerCase().includes(q)) s = 40;
      if (s >= 0) items.push({ name: d.name, url: d.url, package: d.path, _s: s, _type: "doc" });
    }
    // The source files match on the file name and on the path.
    for (const f of DATA.files || []) {
      if (!q) continue;
      let s = score({ name: f.name }, q);
      if (s < 0 && (f.path || "").toLowerCase().includes(q)) s = 50;
      if (s >= 0) items.push({ name: f.path, url: f.url, package: f.lines + " lines", _s: s, _type: "file" });
    }
    items.sort((a, b) => b._s - a._s || a.name.localeCompare(b.name));
    results = items.slice(0, 40);
    sel = 0;
    pres.innerHTML = results.map((r, i) =>
      `<li class="${i === 0 ? "sel" : ""}" data-url="${r.url}">
         <span class="r-kind">${r._type === "doc" ? "doc" : (r._type === "file" ? "src" : (r._type === "package" ? "pkg" : (r.owned ? "mod" : "ext")))}</span>
         <span class="r-name">${r.name}</span>
         <span class="r-meta">${r._type === "module" ? (r.ni + "-&gt;" + r.no) : (r.package || "")}</span>
       </li>`).join("");
    Array.from(pres.children).forEach((li, i) => {
      li.addEventListener("click", () => go(i));
      li.addEventListener("mouseenter", () => setSel(i));
    });
  }
  function setSel(i) {
    sel = i;
    Array.from(pres.children).forEach((li, j) => li.classList.toggle("sel", j === i));
  }
  function go(i) { const r = results[i]; if (r) location.href = r.url; }

  if (pin) {
    pin.addEventListener("input", () => render(pin.value));
    pin.addEventListener("keydown", (e) => {
      if (e.key === "ArrowDown") { e.preventDefault(); setSel(Math.min(sel + 1, results.length - 1)); scrollSel(); }
      else if (e.key === "ArrowUp") { e.preventDefault(); setSel(Math.max(sel - 1, 0)); scrollSel(); }
      else if (e.key === "Enter") { e.preventDefault(); go(sel); }
      else if (e.key === "Escape") closePal();
    });
  }
  function scrollSel() { const li = pres.children[sel]; if (li) li.scrollIntoView({ block: "nearest" }); }

  const so = document.getElementById("search-open");
  if (so) so.addEventListener("click", openPal);
  document.addEventListener("keydown", (e) => {
    if (e.key === "/" && !/^(input|textarea)$/i.test(document.activeElement.tagName)) {
      e.preventDefault(); openPal();
    } else if ((e.key === "k" || e.key === "K") && (e.metaKey || e.ctrlKey)) {
      e.preventDefault(); openPal();
    } else if (e.key === "Escape") closePal();
  });
  if (pal) pal.addEventListener("click", (e) => { if (e.target === pal) closePal(); });

  // ---- graph pan / zoom ----
  document.querySelectorAll(".graph[data-zoom]").forEach((fig) => {
    const svg = fig.querySelector("svg.svdg-graph");
    if (!svg) return;
    let g = svg.querySelector("g"); // graphviz wraps content in <g class="graph">
    if (!g) return;
    let scale = 1, tx = 0, ty = 0, panning = false, sx = 0, sy = 0;
    // capture graphviz's initial transform and build on top of it
    const base = g.getAttribute("transform") || "";
    function apply() { g.setAttribute("transform", `translate(${tx},${ty}) scale(${scale}) ${base}`); }
    function zoomAt(factor, cx, cy) {
      const r = svg.getBoundingClientRect();
      const px = (cx - r.left - tx) / scale, py = (cy - r.top - ty) / scale;
      scale = Math.min(8, Math.max(0.1, scale * factor));
      tx = cx - r.left - px * scale; ty = cy - r.top - py * scale; apply();
    }
    svg.addEventListener("wheel", (e) => {
      e.preventDefault();
      zoomAt(e.deltaY < 0 ? 1.12 : 1 / 1.12, e.clientX, e.clientY);
    }, { passive: false });
    svg.addEventListener("pointerdown", (e) => {
      if (e.target.closest("a")) return; // let node links work
      panning = true; sx = e.clientX - tx; sy = e.clientY - ty; svg.setPointerCapture(e.pointerId);
    });
    svg.addEventListener("pointermove", (e) => {
      if (!panning) return; tx = e.clientX - sx; ty = e.clientY - sy; apply();
    });
    svg.addEventListener("pointerup", () => { panning = false; });
    const tools = fig.querySelector(".graph-tools");
    if (tools) {
      const c = () => { const r = svg.getBoundingClientRect(); return [r.left + r.width / 2, r.top + r.height / 2]; };
      tools.querySelector("[data-zoom-in]")?.addEventListener("click", () => zoomAt(1.25, ...c()));
      tools.querySelector("[data-zoom-out]")?.addEventListener("click", () => zoomAt(1 / 1.25, ...c()));
      tools.querySelector("[data-zoom-reset]")?.addEventListener("click", () => { scale = 1; tx = 0; ty = 0; apply(); });
    }
  });
})();

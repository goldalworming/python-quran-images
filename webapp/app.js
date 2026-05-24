// Single-page-app router + surah list logic.
//
// Routes:
//   #/             -> surah list
//   #/page/<N>     -> page viewer (N = 1..604)
(function () {
  const MAX_PAGE = 604;
  const listEl   = document.getElementById("list");
  const searchEl = document.getElementById("search");
  const backBtn  = document.getElementById("back-btn");

  // -------- Surah list rendering --------
  function normalize(s) {
    return (s || "")
      .toLowerCase()
      .normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "");
  }

  function renderList(filter) {
    const q = normalize(filter);
    listEl.innerHTML = "";
    let shown = 0;
    for (const [num, name, arabic, type, verses, page] of SURAHS) {
      if (q) {
        const hay = normalize(`${num} ${name} ${arabic}`);
        if (!hay.includes(q)) continue;
      }
      const li = document.createElement("li");
      li.className = "surah-row";
      li.innerHTML = `
        <div class="surah-num">${num}</div>
        <div class="surah-info">
          <div class="name">Surah ${name}</div>
          <div class="meta">${type} · ${verses} verses · page ${page}</div>
        </div>
        <div class="surah-arabic">${arabic}</div>
      `;
      li.addEventListener("click", () => {
        location.hash = "#/page/" + page;
      });
      listEl.appendChild(li);
      shown++;
    }
    if (!shown) {
      const empty = document.createElement("li");
      empty.className = "no-results";
      empty.textContent = "No surah found.";
      listEl.appendChild(empty);
    }
  }

  searchEl.addEventListener("input", (e) => renderList(e.target.value));
  renderList("");

  // -------- Router --------
  function parseRoute() {
    const m = location.hash.match(/^#\/page\/(\d+)$/);
    if (m) {
      const p = parseInt(m[1], 10);
      if (p >= 1 && p <= MAX_PAGE) return { name: "page", page: p };
    }
    return { name: "list" };
  }

  function route() {
    const r = parseRoute();
    if (r.name === "page") {
      document.body.classList.remove("route-list");
      document.body.classList.add("route-page");
      window.Viewer.loadPage(r.page);
      window.Viewer.activate();
    } else {
      document.body.classList.remove("route-page");
      document.body.classList.add("route-list");
      window.Viewer.deactivate();
    }
  }

  window.addEventListener("hashchange", route);

  backBtn.addEventListener("click", () => {
    location.hash = "#/";
  });

  // Initial route.
  route();
})();

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
  const tabsEl   = document.querySelector(".tabs");

  // -------- Bookmarks --------
  const BOOKMARKS_KEY = "quran:bookmarks";
  const LAST_PAGE_BY_SURAH_KEY = "quran:lastPageBySurah";
  function getBookmarks() {
    try {
      const arr = JSON.parse(localStorage.getItem(BOOKMARKS_KEY) || "[]");
      return new Set(arr.map(Number).filter(Number.isFinite));
    } catch (_) { return new Set(); }
  }
  function setBookmarks(set) {
    localStorage.setItem(BOOKMARKS_KEY, JSON.stringify([...set]));
  }
  function toggleBookmark(num) {
    const set = getBookmarks();
    if (set.has(num)) {
      set.delete(num);
      const m = getLastPageBySurah();
      delete m[String(num)];
      localStorage.setItem(LAST_PAGE_BY_SURAH_KEY, JSON.stringify(m));
      if (window.Viewer && window.Viewer.evictSurahPages) {
        window.Viewer.evictSurahPages(num);
      }
    } else {
      set.add(num);
      if (window.Viewer && window.Viewer.precacheSurahPages) {
        window.Viewer.precacheSurahPages(num);
      }
    }
    setBookmarks(set);
  }
  function getLastPageBySurah() {
    try { return JSON.parse(localStorage.getItem(LAST_PAGE_BY_SURAH_KEY) || "{}"); }
    catch (_) { return {}; }
  }

  let activeTab = "all"; // "all" | "bookmarks"

  // -------- Surah list rendering --------
  function normalize(s) {
    return (s || "")
      .toLowerCase()
      .normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "");
  }

  function renderList(filter) {
    const q = normalize(filter);
    const bookmarks = getBookmarks();
    const lastPages = getLastPageBySurah();
    listEl.innerHTML = "";
    let shown = 0;
    for (const [num, name, arabic, type, verses, page] of SURAHS) {
      if (activeTab === "bookmarks" && !bookmarks.has(num)) continue;
      if (q) {
        const hay = normalize(`${num} ${name} ${arabic}`);
        if (!hay.includes(q)) continue;
      }
      const isMarked = bookmarks.has(num);
      const resumePage = lastPages[String(num)];
      const target = (activeTab === "bookmarks" && resumePage) ? resumePage : page;
      const metaPage = (activeTab === "bookmarks" && resumePage && resumePage !== page)
        ? `page ${page} · ↻ resume p.${resumePage}`
        : `page ${page}`;
      const li = document.createElement("li");
      li.className = "surah-row";
      li.innerHTML = `
        <div class="surah-num">${num}</div>
        <div class="surah-info">
          <div class="name">Surah ${name}</div>
          <div class="meta">${type} · ${verses} verses · ${metaPage}</div>
        </div>
        <div class="surah-arabic">${arabic}</div>
        <button class="bookmark-btn ${isMarked ? "active" : ""}"
                data-num="${num}"
                aria-label="${isMarked ? "Remove bookmark" : "Add bookmark"}"
                aria-pressed="${isMarked}">
          <svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true">
            <path d="M6 3h12a1 1 0 0 1 1 1v17l-7-4-7 4V4a1 1 0 0 1 1-1z"
                  fill="${isMarked ? "currentColor" : "none"}"
                  stroke="currentColor" stroke-width="2"
                  stroke-linejoin="round"/>
          </svg>
        </button>
      `;
      li.addEventListener("click", (e) => {
        if (e.target.closest(".bookmark-btn")) return;
        if (window.Viewer && window.Viewer.setActiveSurah) {
          window.Viewer.setActiveSurah(num);
        }
        location.hash = "#/page/" + target;
      });
      listEl.appendChild(li);
      shown++;
    }
    if (!shown) {
      const empty = document.createElement("li");
      empty.className = "no-results";
      empty.textContent = activeTab === "bookmarks"
        ? "No bookmarks yet. Tap the star on a surah, or use the ⋮ menu inside a surah."
        : "No surah found.";
      listEl.appendChild(empty);
    }
  }

  listEl.addEventListener("click", (e) => {
    const btn = e.target.closest(".bookmark-btn");
    if (!btn) return;
    e.stopPropagation();
    const num = parseInt(btn.dataset.num, 10);
    if (!Number.isFinite(num)) return;
    toggleBookmark(num);
    renderList(searchEl.value);
  });

  tabsEl.addEventListener("click", (e) => {
    const tab = e.target.closest(".tab");
    if (!tab) return;
    const which = tab.dataset.tab;
    if (which === activeTab) return;
    activeTab = which;
    for (const t of tabsEl.querySelectorAll(".tab")) {
      const on = t.dataset.tab === activeTab;
      t.classList.toggle("active", on);
      t.setAttribute("aria-selected", on ? "true" : "false");
    }
    renderList(searchEl.value);
  });

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
      renderList(searchEl.value);
    }
  }

  window.addEventListener("hashchange", route);

  backBtn.addEventListener("click", () => {
    location.hash = "#/";
  });

  // Initial route.
  route();
})();

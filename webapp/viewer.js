// Quran page viewer (3-slide horizontal strip, swipe nav, marks, etc.).
// Exposes a small API used by app.js's router: window.Viewer.{ loadPage,
// activate, deactivate }.
(function () {
  const MAX_PAGE = 604;

  const titleEl   = document.getElementById("title");
  const areaEl    = document.getElementById("page-area");
  const stripEl   = document.getElementById("strip");
  const imgNext   = document.getElementById("img-next");
  const imgCurr   = document.getElementById("img-curr");
  const imgPrev   = document.getElementById("img-prev");
  const frameCurr = document.getElementById("frame-curr");
  const marksNext = document.getElementById("marks-next");
  const marksCurr = document.getElementById("marks-curr");
  const marksPrev = document.getElementById("marks-prev");

  let page = 1;
  let active = false;     // true when the viewer section is the visible route

  // -------- Preload cache --------
  // Folder containing the AVIF page images, relative to this HTML file.
  // Override at deploy time if the folder layout differs.
  const AVIF_BASE = window.QURAN_AVIF_BASE || "output-avif";
  const preloaded = new Set();
  function avifUrl(p) { return `${AVIF_BASE}/${p}.avif`; }
  function preload(p) {
    if (p < 1 || p > MAX_PAGE) return;
    if (preloaded.has(p)) return;
    preloaded.add(p);
    new Image().src = avifUrl(p);
  }
  function srcFor(p) {
    if (p < 1 || p > MAX_PAGE) return "";
    return avifUrl(p);
  }
  function clamp(p) { return Math.max(1, Math.min(MAX_PAGE, p | 0)); }

  // -------- Marks (memorisation notes) --------
  const MARKS_KEY = "quran:marks";
  const COLOR_KEY = "quran:markColor";
  const FALLBACK_COLOR = "#DC2626";
  const HIT_RADIUS = 0.025;
  let activeColor = localStorage.getItem(COLOR_KEY) || FALLBACK_COLOR;

  function getAllMarks() {
    try { return JSON.parse(localStorage.getItem(MARKS_KEY) || "[]"); }
    catch (_) { return []; }
  }
  function setAllMarks(arr) {
    localStorage.setItem(MARKS_KEY, JSON.stringify(arr));
  }
  function renderMarks(p, layerEl) {
    layerEl.innerHTML = "";
    if (p < 1 || p > MAX_PAGE) return;
    const all = getAllMarks();
    for (const m of all) {
      if (m.page !== p) continue;
      const dot = document.createElement("div");
      dot.className = "mark";
      dot.style.left = (m.x * 100) + "%";
      dot.style.top  = (m.y * 100) + "%";
      dot.style.background = (m.color || FALLBACK_COLOR) + "33";
      layerEl.appendChild(dot);
    }
  }
  function toggleMarkAt(p, x, y) {
    const all = getAllMarks();
    for (let i = 0; i < all.length; i++) {
      if (all[i].page !== p) continue;
      const dx = all[i].x - x, dy = all[i].y - y;
      if (Math.sqrt(dx * dx + dy * dy) < HIT_RADIUS) {
        all.splice(i, 1);
        setAllMarks(all);
        return;
      }
    }
    all.push({ page: p, x, y, color: activeColor });
    setAllMarks(all);
  }
  function eraseNearestMark(p, x, y) {
    const ERASE_RADIUS = 0.06;
    const all = getAllMarks();
    let bestIdx = -1, bestDist = Infinity;
    for (let i = 0; i < all.length; i++) {
      if (all[i].page !== p) continue;
      const dx = all[i].x - x, dy = all[i].y - y;
      const d = Math.sqrt(dx * dx + dy * dy);
      if (d < bestDist) { bestDist = d; bestIdx = i; }
    }
    if (bestIdx >= 0 && bestDist <= ERASE_RADIUS) {
      all.splice(bestIdx, 1);
      setAllMarks(all);
      return true;
    }
    return false;
  }

  // -------- Render --------
  function refresh() {
    titleEl.textContent = `Page ${page}`;
    imgNext.src = srcFor(page + 1);
    imgCurr.src = srcFor(page);
    imgPrev.src = srcFor(page - 1);
    renderMarks(page + 1, marksNext);
    renderMarks(page,     marksCurr);
    renderMarks(page - 1, marksPrev);
    stripEl.style.transition = "none";
    stripEl.style.transform = "translate3d(-33.3333%, 0, 0)";
    localStorage.setItem("quran:lastPage", String(page));
    saveLastPageForBookmarkedSurah();
    updateBookmarkLabel();
    updateBookmarkJumpVisibility();
    preload(page - 2);
    preload(page - 1);
    preload(page + 1);
    preload(page + 2);
  }

  function setHashForPage(p) {
    const hash = "#/page/" + p;
    if (location.hash !== hash) {
      history.replaceState(null, "", location.pathname + hash);
    }
  }

  // -------- Keyboard --------
  document.addEventListener("keydown", (e) => {
    if (!active) return;
    if (e.key === "ArrowRight") { if (page > 1)        { page--; refresh(); setHashForPage(page); } }
    else if (e.key === "ArrowLeft") { if (page < MAX_PAGE) { page++; refresh(); setHashForPage(page); } }
  });

  // -------- Swipe --------
  const SWIPE_MIN_DX = 40;
  const SWIPE_VELOCITY = 0.3;
  const SWIPE_MAX_OFF_AXIS_RATIO = 1.2;

  let pointerId = null;
  let startX = 0, startY = 0, startT = 0;
  let locked = null;
  let vw = window.innerWidth;
  let animating = null;

  window.addEventListener("resize", () => { vw = window.innerWidth; });

  function setOffset(dx) {
    stripEl.style.transform = `translate3d(${-vw + dx}px, 0, 0)`;
  }
  function commitAnimation(targetPage) {
    if (animating) {
      stripEl.removeEventListener("transitionend", animating.handler);
      clearTimeout(animating.timer);
      animating = null;
    }
    page = targetPage;
    refresh();
    setHashForPage(page);
  }
  function snapBack() {
    stripEl.style.transition = "transform 160ms ease-out";
    stripEl.style.transform = "translate3d(-33.3333%, 0, 0)";
  }
  function onStart(e) {
    if (!active) return;
    if (animating) return;
    if (e.pointerType === "mouse" && e.button !== 0) return;
    pointerId = e.pointerId;
    startX = e.clientX;
    startY = e.clientY;
    startT = e.timeStamp || performance.now();
    locked = null;
    vw = window.innerWidth;
    stripEl.style.transition = "none";
    try { areaEl.setPointerCapture(pointerId); } catch (_) {}
  }
  function onMove(e) {
    if (pointerId === null || e.pointerId !== pointerId) return;
    let dx = e.clientX - startX;
    const dy = e.clientY - startY;
    if (locked === null) {
      const adx = Math.abs(dx), ady = Math.abs(dy);
      if (adx < 4 && ady < 4) return;
      locked = adx >= ady ? "h" : "v";
    }
    if (locked === "v") return;
    if (e.cancelable) e.preventDefault();
    if ((dx > 0 && page >= MAX_PAGE) || (dx < 0 && page <= 1)) dx = dx / 3;
    setOffset(dx);
  }
  function onEnd(e) {
    if (pointerId === null || e.pointerId !== pointerId) return;
    const wasLocked = locked;
    const sx = startX, sy = startY, sT = startT;
    try { areaEl.releasePointerCapture(pointerId); } catch (_) {}
    pointerId = null;

    if (wasLocked === null) {
      const moved = Math.abs(e.clientX - sx) < 8
                 && Math.abs(e.clientY - sy) < 8;
      const quick = (e.timeStamp || performance.now()) - sT < 500;
      if (moved && quick) handleTap(e.clientX, e.clientY);
      return;
    }
    if (wasLocked !== "h") return;

    const dx = e.clientX - sx;
    const dt = Math.max(1, (e.timeStamp || performance.now()) - sT);
    const v  = Math.abs(dx) / dt;

    const passDx = Math.abs(dx) >= SWIPE_MIN_DX;
    const passV  = v >= SWIPE_VELOCITY && Math.abs(dx) >= 15;
    let target = page;
    if (passDx || passV) {
      if (dx > 0 && page < MAX_PAGE)      target = page + 1;
      else if (dx < 0 && page > 1)        target = page - 1;
    }

    if (target === page) { snapBack(); return; }

    const finalPct = (dx > 0) ? "0%" : "-66.6666%";
    stripEl.style.transition = "transform 200ms ease-out";
    stripEl.style.transform = `translate3d(${finalPct}, 0, 0)`;
    const handler = () => commitAnimation(target);
    const timer   = setTimeout(handler, 260);
    animating = { target, handler, timer };
    stripEl.addEventListener("transitionend", handler, { once: true });
  }
  function onCancel(e) {
    if (pointerId === null || e.pointerId !== pointerId) return;
    try { areaEl.releasePointerCapture(pointerId); } catch (_) {}
    pointerId = null;
    if (locked === "h") snapBack();
  }
  function handleTap(clientX, clientY) {
    const isMark  = document.body.classList.contains("mark-mode");
    const isErase = document.body.classList.contains("erase-mode");
    if (!isMark && !isErase) return;
    if (document.body.classList.contains("hide-marks")) return;
    const rect = frameCurr.getBoundingClientRect();
    if (clientX < rect.left || clientX > rect.right) return;
    if (clientY < rect.top  || clientY > rect.bottom) return;
    const x = (clientX - rect.left) / rect.width;
    const y = (clientY - rect.top)  / rect.height;
    if (isErase) eraseNearestMark(page, x, y);
    else         toggleMarkAt(page, x, y);
    renderMarks(page, marksCurr);
  }

  areaEl.addEventListener("pointerdown", onStart);
  areaEl.addEventListener("pointermove", onMove);
  areaEl.addEventListener("pointerup", onEnd);
  areaEl.addEventListener("pointercancel", onCancel);

  // -------- Menu --------
  const menuBtn       = document.getElementById("menu-btn");
  const menuEl        = document.getElementById("menu-dropdown");
  const toggleLabel   = document.getElementById("toggle-layer-label");
  const markLabel     = document.getElementById("toggle-mark-label");
  const eraseLabel    = document.getElementById("toggle-erase-label");
  const bookmarkLabel = document.getElementById("toggle-bookmark-label");
  const colorRow      = document.getElementById("color-row");

  function openMenu()  { menuEl.hidden = false; }
  function closeMenu() { menuEl.hidden = true;  }
  function toggleMenu(){ if (menuEl.hidden) openMenu(); else closeMenu(); }

  menuBtn.addEventListener("click", (e) => {
    e.stopPropagation();
    toggleMenu();
  });
  document.addEventListener("click", (e) => {
    if (!menuEl.hidden && !menuEl.contains(e.target) && e.target !== menuBtn) {
      closeMenu();
    }
  });

  function updateToggleLabel() {
    toggleLabel.textContent = document.body.classList.contains("hide-marks")
      ? "Show marks" : "Hide marks";
  }
  function updateEraseLabel() {
    eraseLabel.textContent = document.body.classList.contains("erase-mode")
      ? "Erase mode: ON" : "Erase mode";
  }
  function updateMarkLabel() {
    markLabel.textContent = document.body.classList.contains("mark-mode")
      ? "Mark mode: ON" : "Mark mode";
  }
  function updateColorSelection() {
    for (const sw of colorRow.querySelectorAll(".color-swatch")) {
      sw.classList.toggle("selected", sw.dataset.color === activeColor);
    }
  }

  menuEl.addEventListener("click", (e) => {
    const item = e.target.closest("[data-action]");
    if (item) {
      const action = item.dataset.action;
      if (action === "toggle-bookmark") {
        toggleBookmarkForCurrentSurah();
        updateBookmarkLabel();
        updateBookmarkJumpVisibility();
      } else if (action === "toggle-layer") {
        document.body.classList.toggle("hide-marks");
        if (document.body.classList.contains("hide-marks")) {
          document.body.classList.remove("mark-mode", "erase-mode");
          updateMarkLabel();
          updateEraseLabel();
        }
        updateToggleLabel();
      } else if (action === "toggle-mark") {
        if (document.body.classList.contains("hide-marks")) {
          document.body.classList.remove("hide-marks");
          updateToggleLabel();
        }
        document.body.classList.remove("erase-mode");
        document.body.classList.toggle("mark-mode");
        updateMarkLabel();
        updateEraseLabel();
      } else if (action === "toggle-erase") {
        if (document.body.classList.contains("hide-marks")) {
          document.body.classList.remove("hide-marks");
          updateToggleLabel();
        }
        document.body.classList.remove("mark-mode");
        document.body.classList.toggle("erase-mode");
        updateMarkLabel();
        updateEraseLabel();
      } else if (action === "clear-all") {
        const all = getAllMarks();
        const count = all.filter(m => m.page === page).length;
        if (count === 0) {
          alert(`No marks on page ${page}.`);
        } else if (confirm(`Are you sure? This will delete all ${count} mark(s) on page ${page}.`)) {
          setAllMarks(all.filter(m => m.page !== page));
          renderMarks(page, marksCurr);
        }
      }
      closeMenu();
      return;
    }
    const swatch = e.target.closest(".color-swatch");
    if (swatch) {
      activeColor = swatch.dataset.color;
      localStorage.setItem(COLOR_KEY, activeColor);
      updateColorSelection();
    }
  });

  updateToggleLabel();
  updateMarkLabel();
  updateEraseLabel();
  updateColorSelection();

  // -------- Bookmark jump dropdown --------
  const BOOKMARKS_KEY = "quran:bookmarks";
  const LAST_PAGE_BY_SURAH_KEY = "quran:lastPageBySurah";
  const bjBtn  = document.getElementById("bookmark-jump-btn");
  const bjMenu = document.getElementById("bookmark-jump-dropdown");

  function readBookmarks() {
    try {
      const arr = JSON.parse(localStorage.getItem(BOOKMARKS_KEY) || "[]");
      return arr.map(Number).filter(Number.isFinite);
    } catch (_) { return []; }
  }
  function writeBookmarks(arr) {
    localStorage.setItem(BOOKMARKS_KEY, JSON.stringify(arr));
  }
  function toggleBookmarkForCurrentSurah() {
    const s = surahForPage(page);
    if (!s) return;
    const arr = readBookmarks();
    const idx = arr.indexOf(s[0]);
    if (idx >= 0) {
      arr.splice(idx, 1);
      writeBookmarks(arr);
      const m = readLastPageBySurah();
      delete m[String(s[0])];
      writeLastPageBySurah(m);
    } else {
      arr.push(s[0]);
      writeBookmarks(arr);
      saveLastPageForBookmarkedSurah();
    }
  }
  function updateBookmarkLabel() {
    if (!bookmarkLabel) return;
    const s = surahForPage(page);
    if (!s) { bookmarkLabel.textContent = "Bookmark this surah"; return; }
    const bookmarked = readBookmarks().includes(s[0]);
    bookmarkLabel.textContent = bookmarked
      ? `Remove bookmark (${s[1]})`
      : `Bookmark this surah (${s[1]})`;
  }
  function updateBookmarkJumpVisibility() {
    if (!bjBtn) return;
    bjBtn.style.display = readBookmarks().length > 0 ? "" : "none";
  }

  function readLastPageBySurah() {
    try { return JSON.parse(localStorage.getItem(LAST_PAGE_BY_SURAH_KEY) || "{}"); }
    catch (_) { return {}; }
  }
  function writeLastPageBySurah(map) {
    localStorage.setItem(LAST_PAGE_BY_SURAH_KEY, JSON.stringify(map));
  }
  function saveLastPageForBookmarkedSurah() {
    const s = surahForPage(page);
    if (!s) return;
    const bookmarks = readBookmarks();
    if (!bookmarks.includes(s[0])) return;
    const m = readLastPageBySurah();
    m[String(s[0])] = page;
    writeLastPageBySurah(m);
  }

  // Find the surah a given page belongs to (largest startPage <= page).
  function surahForPage(p) {
    let best = null;
    for (const s of SURAHS) {
      const start = s[5];
      if (start <= p && (best === null || start > best[5])) best = s;
    }
    return best;
  }

  function renderBookmarkJump() {
    const nums = readBookmarks();
    bjMenu.innerHTML = "";
    if (nums.length === 0) {
      const empty = document.createElement("div");
      empty.className = "bookmark-jump-empty";
      empty.textContent = "No bookmarks yet.";
      bjMenu.appendChild(empty);
      return;
    }
    const currentSurah = surahForPage(page);
    const currentNum = currentSurah ? currentSurah[0] : -1;
    const lastPages = readLastPageBySurah();
    const ordered = nums
      .map((n) => SURAHS.find((s) => s[0] === n))
      .filter(Boolean)
      .sort((a, b) => a[0] - b[0]);
    for (const s of ordered) {
      const [num, name, , , , startPage] = s;
      const resumePage = lastPages[String(num)] || startPage;
      const isResumed = resumePage !== startPage;
      const btn = document.createElement("button");
      btn.className = "bookmark-jump-item" + (num === currentNum ? " current" : "");
      btn.dataset.page = String(resumePage);
      btn.innerHTML = `
        <span class="bj-num">${num}</span>
        <span class="bj-name">${name}</span>
        <span class="bj-page">${isResumed ? "↻ p." + resumePage : "p." + startPage}</span>
      `;
      bjMenu.appendChild(btn);
    }
  }

  function openBookmarkJump() {
    renderBookmarkJump();
    bjMenu.hidden = false;
    bjBtn.setAttribute("aria-expanded", "true");
  }
  function closeBookmarkJump() {
    bjMenu.hidden = true;
    bjBtn.setAttribute("aria-expanded", "false");
  }

  bjBtn.addEventListener("click", (e) => {
    e.stopPropagation();
    if (bjMenu.hidden) openBookmarkJump(); else closeBookmarkJump();
  });
  bjMenu.addEventListener("click", (e) => {
    const item = e.target.closest(".bookmark-jump-item");
    if (!item) return;
    const target = parseInt(item.dataset.page, 10);
    closeBookmarkJump();
    if (!Number.isFinite(target)) return;
    page = clamp(target);
    refresh();
    setHashForPage(page);
  });
  document.addEventListener("click", (e) => {
    if (!bjMenu.hidden && !bjMenu.contains(e.target) && e.target !== bjBtn
        && !bjBtn.contains(e.target)) {
      closeBookmarkJump();
    }
  });

  // -------- Wake lock --------
  let wakeLock = null;
  async function requestWakeLock() {
    if (!("wakeLock" in navigator)) return;
    if (!active) return;
    if (document.visibilityState !== "visible") return;
    try {
      wakeLock = await navigator.wakeLock.request("screen");
      wakeLock.addEventListener("release", () => { wakeLock = null; });
    } catch (_) {}
  }
  function releaseWakeLock() {
    if (wakeLock) {
      try { wakeLock.release(); } catch (_) {}
      wakeLock = null;
    }
  }
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "visible" && active && !wakeLock) {
      requestWakeLock();
    }
  });

  // -------- Public API --------
  window.Viewer = {
    loadPage(p) {
      page = clamp(p);
      refresh();
    },
    activate() {
      active = true;
      requestWakeLock();
    },
    deactivate() {
      active = false;
      releaseWakeLock();
      // Reset transient modes when leaving the viewer.
      document.body.classList.remove("mark-mode", "erase-mode");
      updateMarkLabel();
      updateEraseLabel();
      closeMenu();
      closeBookmarkJump();
    },
  };
})();

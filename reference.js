// Поиск, фильтры и карточки справочника.
// Данные оставлены в reference.html, чтобы справочник работал офлайн.
// Структура файла: данные и DOM -> фильтрация -> рендеринг -> тема -> события.
"use strict";
const ENTRIES = JSON.parse(document.getElementById("reference-data").textContent);
const COURSE_LABELS = {
  python: "Python",
  javascript: "JavaScript",
  cpp: "C++",
  sql: "SQL",
  java: "Java",
  csharp: "C#",
  go: "Go",
  rust: "Rust",
  "git-terminal": "Терминал / Git Bash",
};
const COURSE_ICONS = {
  python: "🐍",
  javascript: "🟨",
  cpp: "⚙️",
  sql: "🗄️",
  java: "☕",
  csharp: "🔷",
  go: "🐹",
  rust: "🦀",
  "git-terminal": "⌘",
};
const COURSE_ORDER = Object.keys(COURSE_LABELS);
const PAGE_SIZE = 30;
const querySelector = (selector) => document.querySelector(selector);
const searchInput = querySelector("#searchInput");
const courseFilter = querySelector("#courseFilter");
const categoryFilter = querySelector("#categoryFilter");
const resultGrid = querySelector("#results");
const resultCount = querySelector("#resultCount");
const moreRow = querySelector("#moreRow");
let shownLimit = PAGE_SIZE;
let toastTimer;

// Curriculum text is untrusted input: escape it before it reaches an HTML template.
function escapeHtml(value) {
  return String(value).replace(
    /[&<>"']/g,
    (ch) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[ch],
  );
}
function normalize(value) {
  return String(value ?? "")
    .normalize("NFKC")
    .toLocaleLowerCase("ru-RU");
}
// --- Course counts and filter options ---
function populateCourses() {
  const counts = Object.fromEntries(COURSE_ORDER.map((id) => [id, 0]));
  ENTRIES.forEach((entry) => {
    if (counts[entry.course] !== undefined) counts[entry.course]++;
  });
  courseFilter.innerHTML =
    '<option value="all">Все языки и инструменты · ' +
    ENTRIES.length +
    "</option>" +
    COURSE_ORDER.map(
      (id) =>
        '<option value="' +
        id +
        '">' +
        COURSE_ICONS[id] +
        " " +
        COURSE_LABELS[id] +
        " · " +
        counts[id] +
        "</option>",
    ).join("");
  querySelector("#totalEntries").textContent = String(ENTRIES.length);
}
function updateCategories(preserve = true) {
  const prior = preserve ? categoryFilter.value : "all";
  const selectedCourse = courseFilter.value;
  const categories = [
    ...new Set(
      ENTRIES.filter((entry) => selectedCourse === "all" || entry.course === selectedCourse).map(
        (entry) => entry.category,
      ),
    ),
  ].sort((a, b) => a.localeCompare(b, "ru"));
  categoryFilter.innerHTML =
    '<option value="all">Все категории</option>' +
    categories
      .map(
        (category) =>
          '<option value="' + escapeHtml(category) + '">' + escapeHtml(category) + "</option>",
      )
      .join("");
  categoryFilter.value = categories.includes(prior) ? prior : "all";
}
// --- Search and filtering ---
function getMatchingEntries() {
  const course = courseFilter.value,
    category = categoryFilter.value;
  const terms = normalize(searchInput.value).trim().split(/\s+/).filter(Boolean);
  return ENTRIES.map((entry, index) => ({ entry, index })).filter(({ entry }) => {
    if (course !== "all" && entry.course !== course) return false;
    if (category !== "all" && entry.category !== category) return false;
    if (!terms.length) return true;
    const haystack = normalize(
      [
        COURSE_LABELS[entry.course],
        entry.category,
        entry.name,
        entry.syntax,
        entry.description,
        entry.usage,
        entry.example,
        entry.mistakes,
        entry.note,
      ].join(" "),
    );
    return terms.every((term) => haystack.includes(term));
  });
}
// --- Escaped HTML builders and paginated results ---
function renderCodePanel(title, text, index, kind) {
  return (
    '<section class="code-panel"><div class="code-head"><span>' +
    title +
    '</span><button class="copy-button" type="button" data-copy-index="' +
    index +
    '" data-copy-kind="' +
    kind +
    '" aria-label="Скопировать ' +
    title.toLocaleLowerCase("ru-RU") +
    '">Копировать</button></div><pre><code>' +
    escapeHtml(text) +
    "</code></pre></section>"
  );
}
function renderEntries() {
  const matches = getMatchingEntries();
  const visible = matches.slice(0, shownLimit);
  const shown = visible.length;
  resultCount.innerHTML =
    "<strong>Найдено " +
    matches.length +
    "</strong> · показано " +
    shown +
    (matches.length === 1 ? " карточка" : " карточек");
  if (!matches.length) {
    resultGrid.innerHTML =
      '<div class="empty-state"><div class="empty-icon">⌕</div><b>Ничего не нашлось</b><p>Попробуй изменить запрос или снять один из фильтров.</p></div>';
  } else {
    resultGrid.innerHTML = visible
      .map(
        ({ entry, index }) =>
          '<article class="entry-card"><div class="entry-head"><div class="entry-title-wrap"><div class="entry-kicker"><span class="language-chip">' +
          COURSE_ICONS[entry.course] +
          " " +
          escapeHtml(COURSE_LABELS[entry.course]) +
          '</span><span class="category-chip">' +
          escapeHtml(entry.category) +
          "</span></div><h2>" +
          escapeHtml(entry.name) +
          '</h2></div><span class="entry-number">' +
          String(index + 1).padStart(3, "0") +
          '</span></div><p class="entry-description">' +
          escapeHtml(entry.description) +
          '</p><div class="entry-usage"><b>Как и где использовать</b><p>' +
          escapeHtml(entry.usage) +
          '</p></div><div class="code-grid">' +
          renderCodePanel("Синтаксис", entry.syntax, index, "syntax") +
          renderCodePanel("Пример", entry.example, index, "example") +
          '</div><div class="entry-mistakes"><span class="mistake-mark" aria-hidden="true">⚠</span><div><b>Частые ошибки</b><p>' +
          escapeHtml(entry.mistakes) +
          '</p></div></div><div class="entry-note"><b>На заметку</b><span>' +
          escapeHtml(entry.note) +
          "</span></div></article>",
      )
      .join("");
  }
  moreRow.hidden = shown >= matches.length;
  querySelector("#showMore").textContent = "Показать ещё " + Math.min(PAGE_SIZE, matches.length - shown);
}
function changeFilters(resetLimit = true) {
  if (resetLimit) shownLimit = PAGE_SIZE;
  updateCategories(true);
  renderEntries();
}
function showToast(message) {
  const element = querySelector("#toast");
  element.textContent = message;
  element.classList.add("show");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => element.classList.remove("show"), 1800);
}
async function copyText(text) {
  try {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(text);
      return true;
    }
  } catch {}
  try {
    const field = document.createElement("textarea");
    field.value = text;
    field.setAttribute("readonly", "");
    field.style.position = "fixed";
    field.style.opacity = "0";
    document.body.appendChild(field);
    field.select();
    const ok = document.execCommand("copy");
    field.remove();
    return ok;
  } catch {
    return false;
  }
}

// Тема читается и обновляется в общем состоянии Codeflow, остальные данные прогресса не меняются.
// --- Theme preference: update only the two theme fields in shared local storage ---
const STORAGE_KEY = "codeflow-trainer-v1";
const THEME_NAMES = ["violet", "ocean", "mint", "coral", "rose", "night", "glitch", "custom"];
let appState = {};
try {
  const stored = JSON.parse(localStorage.getItem(STORAGE_KEY) || "{}");
  if (stored && typeof stored === "object" && !Array.isArray(stored)) appState = stored;
} catch {}
let activeTheme = THEME_NAMES.includes(appState.theme) ? appState.theme : "violet";
let customAccent = /^#[0-9a-fA-F]{6}$/.test(appState.customAccent || "")
  ? appState.customAccent
  : "#7067e9";
function saveTheme() {
  try {
    const raw = JSON.parse(localStorage.getItem(STORAGE_KEY) || "{}");
    const next = raw && typeof raw === "object" && !Array.isArray(raw) ? raw : {};
    next.theme = activeTheme;
    next.customAccent = customAccent;
    localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
  } catch {}
}
function applyTheme() {
  document.body.dataset.theme = activeTheme;
  if (activeTheme === "custom") document.body.style.setProperty("--accent", customAccent);
  else document.body.style.removeProperty("--accent");
  querySelector("#customAccentInput").value = customAccent;
  document.querySelectorAll("[data-theme-pick]").forEach((button) => {
    const selected = button.dataset.themePick === activeTheme;
    button.classList.toggle("active", selected);
    button.setAttribute("aria-pressed", String(selected));
  });
}
function closeThemeMenu() {
  const menu = querySelector("#themeMenu");
  menu.hidden = true;
  querySelector("#themeToggle").setAttribute("aria-expanded", "false");
}
function setTheme(theme) {
  if (!THEME_NAMES.includes(theme)) return;
  activeTheme = theme;
  applyTheme();
  saveTheme();
  closeThemeMenu();
  showToast(theme === "custom" ? "Свой цвет сохранён" : "Тема изменена");
}

// --- Initial page setup and event wiring ---
populateCourses();
const params = new URLSearchParams(location.search);
if (COURSE_ORDER.includes(params.get("course"))) courseFilter.value = params.get("course");
if (params.get("q")) searchInput.value = params.get("q").slice(0, 120);
updateCategories(false);
renderEntries();
applyTheme();

searchInput.addEventListener("input", () => {
  shownLimit = PAGE_SIZE;
  renderEntries();
});
courseFilter.addEventListener("change", () => changeFilters(true));
categoryFilter.addEventListener("change", () => {
  shownLimit = PAGE_SIZE;
  renderEntries();
});
querySelector("#clearSearch").addEventListener("click", () => {
  searchInput.value = "";
  shownLimit = PAGE_SIZE;
  renderEntries();
  searchInput.focus();
});
querySelector("#resetFilters").addEventListener("click", () => {
  searchInput.value = "";
  courseFilter.value = "all";
  categoryFilter.value = "all";
  shownLimit = PAGE_SIZE;
  updateCategories(false);
  renderEntries();
  searchInput.focus();
});
querySelector("#showMore").addEventListener("click", () => {
  shownLimit += PAGE_SIZE;
  renderEntries();
});
querySelector("#themeToggle").addEventListener("click", () => {
  const menu = querySelector("#themeMenu"),
    opening = menu.hidden;
  menu.hidden = !opening;
  querySelector("#themeToggle").setAttribute("aria-expanded", String(opening));
});
document.addEventListener("click", async (event) => {
  const themeButton = event.target.closest("[data-theme-pick]");
  if (themeButton) {
    setTheme(themeButton.dataset.themePick);
    return;
  }
  const copyButton = event.target.closest("[data-copy-index]");
  if (copyButton) {
    const entry = ENTRIES[Number(copyButton.dataset.copyIndex)];
    if (!entry) return;
    const text = entry[copyButton.dataset.copyKind];
    const ok = await copyText(text);
    showToast(ok ? "Скопировано в буфер обмена" : "Не удалось скопировать — выдели текст вручную");
    return;
  }
  if (!event.target.closest(".theme-picker")) closeThemeMenu();
});
querySelector("#customAccentInput").addEventListener("input", (event) => {
  customAccent = event.target.value;
  activeTheme = "custom";
  applyTheme();
  saveTheme();
});
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") closeThemeMenu();
  if (event.key === "/" && !/INPUT|TEXTAREA|SELECT/.test(document.activeElement.tagName)) {
    event.preventDefault();
    searchInput.focus();
  }
});
if ("serviceWorker" in navigator)
  window.addEventListener("load", () =>
    navigator.serviceWorker.register("./service-worker.js").catch(() => {}),
  );

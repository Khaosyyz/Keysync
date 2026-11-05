import { api, applyTheme, errorCode, h, icon, isDark, onSystemScheme, percent, segmented, THEMES, trackFocusMode, watchModel } from "./shared.js";
import { initOnboarding } from "./onboarding.js";
import { formatDuration, keyLabel, LANGUAGES, locale, setLanguage, t, tNodes, translateStatic } from "./i18n.js";

const $ = (sel) => document.querySelector(sel);
const TOAST_MS = 1800;
const DISARM_MS = 2500;
const PAGES = ["history", "vocab", "settings"];

let py, cfg, onboarding;
let records = [];
let words = [];
let playing = null;
let currentPage = PAGES[0];
let fadeTimer;

const booted = init();
window.addEventListener("ks:result", async (e) => {
  await booted;
  addRecord(e.detail.record);
});

async function init() {
  try {
    py = await api;
    cfg = await py.bootstrap();
    records = cfg.history;
    words = cfg.hotwords;
    trackFocusMode();
    bindNav();
    bindComposer();
    bindSettings();
    bindModel();
    const scroller = $("#page-history .scroll");
    scroller.addEventListener("scroll", () =>
      $(".topbar").classList.toggle("scrolled", scroller.scrollTop > 0), { passive: true });
    onboarding = initOnboarding({ py, cfg, save: saveSetting, onFinish: () => setMode("app") });
    applyTheme(cfg.theme);
    onSystemScheme(syncChrome);
    renderText();
    setMode(cfg.onboarded ? "app" : "onboarding");
  } finally {
    py?.ready();
  }
}

/* ---------- shells ----------
   The window is either the onboarding or the app (rail + panel), never both.
   The app always has a page selected; it opens on History. */

function setMode(mode) {
  document.body.dataset.mode = mode;
  if (mode === "onboarding") onboarding.enter();
  else showPage(PAGES[0]);
  syncChrome();
}

function bindNav() {
  document.querySelectorAll(".rail-btn").forEach((b) => b.addEventListener("click", () => showPage(b.dataset.page)));
}

function showPage(page) {
  currentPage = PAGES.includes(page) ? page : PAGES[0];
  document.querySelectorAll(".rail-btn").forEach((b) => b.classList.toggle("active", b.dataset.page === currentPage));
  document.querySelectorAll(".page").forEach((p) => (p.hidden = p.id !== `page-${currentPage}`));
}

/* ---------- settings changes ----------
   A theme change only swaps colours (cross-faded); any other change re-renders
   the text from the current language and cfg. Neither path reloads anything. */

async function saveSetting(key, value) {
  Object.assign(cfg, await py.update_setting(key, value));
  if (key === "theme") fadeTheme();
  else renderText();
}

function fadeTheme() {
  const root = document.documentElement;
  const duration = parseFloat(getComputedStyle(root).getPropertyValue("--theme-fade"));
  root.classList.add("theme-fade");
  applyTheme(cfg.theme);
  clearTimeout(fadeTimer);
  fadeTimer = setTimeout(() => root.classList.remove("theme-fade"), duration);
  renderChoices();
  syncChrome();
}

/* The title bar takes the colour of whichever shell is showing, read from an
   untransitioned probe so it is the destination colour, never a mid-fade one. */
function syncChrome() {
  const rgb = getComputedStyle($(".caption-probe")).backgroundColor.match(/\d+/g).slice(0, 3).map(Number);
  py.set_chrome(rgb, isDark());
}

function renderText() {
  setLanguage(cfg.language);
  translateStatic();
  document.querySelectorAll(".hotkey").forEach((el) => (el.textContent = keyLabel(cfg.hotkey)));
  $("#word-input").maxLength = cfg.hotword_max_length;
  renderFeed();
  renderStats();
  renderWords();
  renderChoices();
  renderModel();
}

function renderChoices() {
  renderSettings();
  onboarding.render();
}

function toast(text, isError = false) {
  const el = $("#toast");
  el.replaceChildren(icon(isError ? "alert" : "check", 14), text);
  el.classList.toggle("error", isError);
  el.classList.add("show");
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => el.classList.remove("show"), TOAST_MS);
}

function shake(el) {
  el.classList.remove("invalid");
  void el.offsetWidth;
  el.classList.add("invalid");
}

const setIcon = (btn, name) => (btn.firstElementChild.className = `icon i-${name}`);

const actionBtn = (name, tipKey, onclick) =>
  h("button", { class: "icon-btn", "data-tip": t(tipKey), onclick }, icon(name));

/* ---------- history ---------- */

const dayOf = (r) => r.timestamp.slice(0, 10);

function dayLabel(key) {
  const date = new Date(`${key}T00:00:00`);
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const diff = Math.round((today - date) / 86400000);
  const sameYear = date.getFullYear() === today.getFullYear();
  const md = new Intl.DateTimeFormat(locale(), { month: "short", day: "numeric", year: sameYear ? undefined : "numeric" }).format(date);
  const weekday = new Intl.DateTimeFormat(locale(), { weekday: "short" }).format(date);
  const name = diff === 0 ? t("today") : diff === 1 ? t("yesterday") : md;
  return h("h2", { class: "day-label" }, name, h("small", {}, diff <= 1 ? `${md} ${weekday}` : weekday));
}

const dayGroup = (key) => h("section", { class: "day", dataset: { day: key } }, dayLabel(key));

const feedEmpty = () => h("div", { class: "empty-state" },
  h("div", { class: "badge" }, icon("mic", 24)),
  h("strong", {}, t("feed.empty.title")),
  h("span", {}, t("feed.empty.body", { days: cfg.retention_days })));

function renderFeed(freshId) {
  const feed = $("#feed");
  feed.replaceChildren();
  if (!records.length) return feed.append(feedEmpty());
  let group;
  for (const r of records) {
    if (group?.dataset.day !== dayOf(r)) feed.append((group = dayGroup(dayOf(r))));
    group.append(entryCard(r, r.id === freshId));
  }
}

function addRecord(r) {
  records.unshift(r);
  renderStats();
  const first = $("#feed .day");
  if (first?.dataset.day === dayOf(r)) first.querySelector(".day-label").after(entryCard(r, true));
  else renderFeed(r.id);
}

function renderStats() {
  const stats = $("#stats");
  stats.hidden = !records.length;
  const chars = records.reduce((n, r) => n + r.text.length, 0);
  const minutes = records.reduce((n, r) => n + r.duration_s, 0) / 60;
  stats.replaceChildren(...tNodes("stats", {
    days: cfg.retention_days,
    minutes: h("b", {}, minutes < 10 ? minutes.toFixed(1) : Math.round(minutes)),
    chars: h("b", {}, chars.toLocaleString(locale())),
  }));
}

const clampObserver = new ResizeObserver((items) => {
  for (const { target } of items) {
    const card = target.closest(".entry");
    if (card && !card.classList.contains("expanded"))
      card.querySelector(".more").hidden = target.scrollHeight <= target.clientHeight + 1;
  }
});

function fillText(card, r) {
  const text = card.querySelector(".entry-text");
  text.replaceChildren(...(r.text ? [r.text] : [t("empty.text"), h("small", {}, t("empty.hint"))]));
  text.classList.toggle("selectable", !!r.text);
  card.classList.toggle("empty", !r.text);
  card.querySelector(".act-copy").hidden = !r.text;
}

function entryCard(r, fresh) {
  let disarmTimer;
  const more = h("button", { class: "more", hidden: true, onclick: () => {
    const expanded = card.classList.toggle("expanded");
    more.textContent = t(expanded ? "less" : "more");
  } }, t("more"));

  const copyBtn = actionBtn("copy", "act.copy", async () => {
    try { await py.copy(r.text); } catch { return toast(t("toast.copyFailed"), true); }
    setIcon(copyBtn, "check");
    copyBtn.classList.add("done");
    setTimeout(() => { setIcon(copyBtn, "copy"); copyBtn.classList.remove("done"); }, TOAST_MS);
    toast(t("toast.copied"));
  });
  copyBtn.classList.add("act-copy");

  const playBtn = actionBtn("play", "act.play", () => togglePlay(playBtn, r));

  const rewriteBtn = actionBtn("rewrite", "act.rewrite", async () => {
    rewriteBtn.classList.add("busy");
    try {
      Object.assign(r, await py.retranscribe(r.id));
      fillText(card, r);
      const text = card.querySelector(".entry-text");
      text.classList.remove("swapping");
      void text.offsetWidth;
      text.classList.add("swapping");
      renderStats();
      toast(t("toast.rewritten"));
    } catch {
      toast(t("toast.rewriteFailed"), true);
    } finally {
      rewriteBtn.classList.remove("busy");
    }
  });

  const deleteBtn = actionBtn("delete", "act.delete", () => {
    if (!deleteBtn.classList.contains("armed")) {
      deleteBtn.classList.add("armed");
      deleteBtn.dataset.tip = t("act.confirm");
      disarmTimer = setTimeout(() => {
        deleteBtn.classList.remove("armed");
        deleteBtn.dataset.tip = t("act.delete");
      }, DISARM_MS);
      return;
    }
    clearTimeout(disarmTimer);
    removeEntry(card, r);
  });

  const delivery = { typed: "delivery.typed", shown: "delivery.shown" }[r.delivery];
  const text = h("p", { class: "entry-text" });
  const card = h("article", { class: `entry${fresh ? " fresh" : ""}` },
    text,
    h("footer", { class: "entry-meta" },
      h("time", {}, r.timestamp.slice(11, 16)),
      h("span", {}, formatDuration(r.duration_s)),
      delivery && h("span", { class: `tag ${r.delivery}` }, t(delivery)),
      more,
      h("div", { class: "actions" }, copyBtn, playBtn, rewriteBtn, deleteBtn)));
  fillText(card, r);
  clampObserver.observe(text);
  return card;
}

function resetPlay() {
  if (!playing) return;
  clearTimeout(playing.timer);
  setIcon(playing.btn, "play");
  playing.btn.dataset.tip = t("act.play");
  playing.btn.classList.remove("on");
  playing = null;
}

async function togglePlay(btn, r) {
  const same = playing?.btn === btn;
  if (playing) {
    resetPlay();
    await py.stop();
  }
  if (same) return;
  try { await py.play(r.id); } catch { return toast(t("toast.noAudio"), true); }
  setIcon(btn, "stop");
  btn.dataset.tip = t("act.stop");
  btn.classList.add("on");
  playing = { btn, timer: setTimeout(resetPlay, r.duration_s * 1000) };
}

async function removeEntry(card, r) {
  if (playing && card.contains(playing.btn)) {
    resetPlay();
    await py.stop();
  }
  try { await py.delete(r.id); } catch { return toast(t("toast.deleteFailed"), true); }
  records.splice(records.indexOf(r), 1);
  renderStats();
  await card.animate(
    [{ height: `${card.offsetHeight}px`, opacity: 1 },
     { height: "0px", opacity: 0, marginBottom: "0px", paddingTop: "0px", paddingBottom: "0px", borderWidth: "0px" }],
    { duration: 220, easing: "cubic-bezier(.2, .8, .2, 1)", fill: "forwards" }).finished;
  const group = card.parentElement;
  clampObserver.unobserve(card.querySelector(".entry-text"));
  card.remove();
  if (!group.querySelector(".entry")) group.remove();
  if (!records.length) renderFeed();
}

/* ---------- vocabulary ---------- */

const wordError = (code) => {
  const key = `err.${code}`;
  const n = code === "full" ? cfg.hotword_max_count : cfg.hotword_max_length;
  return ["empty", "duplicate", "too_long", "full", "missing"].includes(code) ? t(key, { n }) : t("err.unknown");
};

const wordsEmpty = () => h("li", { class: "empty-state" },
  h("div", { class: "badge" }, icon("vocab", 24)),
  h("strong", {}, t("vocab.empty.title")),
  h("span", {}, t("vocab.empty.body")));

function renderWords(freshWord) {
  $("#words").replaceChildren(...(words.length ? words.map((w) => wordTile(w, w === freshWord)) : [wordsEmpty()]));
  $("#word-counter").textContent = `${words.length} / ${cfg.hotword_max_count}`;
  composerHint();
}

function wordTile(word, fresh) {
  const tile = h("li", { class: `word${fresh ? " fresh" : ""}`, ondblclick: () => editWord(tile, word) },
    h("span", { class: "word-text", title: word }, word),
    h("div", { class: "actions" },
      h("button", { class: "icon-btn", "data-tip": t("act.edit"), onclick: () => editWord(tile, word) }, icon("edit", 14)),
      h("button", { class: "icon-btn", "data-tip": t("act.delete"), onclick: () => removeWord(tile, word) }, icon("delete", 14))));
  return tile;
}

function editWord(tile, word) {
  const input = h("input", { maxlength: cfg.hotword_max_length, spellcheck: "false" });
  input.value = word;
  tile.classList.add("editing");
  tile.replaceChildren(input);
  input.focus();
  input.select();

  let settled = false;
  const finish = async (commit, viaBlur = false) => {
    if (settled) return;
    settled = true;
    const next = input.value.trim();
    if (!commit || next === word) return renderWords();
    try {
      words = await py.update_word(word, next);
      renderWords();
    } catch (err) {
      if (viaBlur) return renderWords();
      settled = false;
      shake(tile);
      toast(wordError(errorCode(err)), true);
      input.focus();
    }
  };
  input.addEventListener("input", () => tile.classList.remove("invalid"));
  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter") finish(true);
    if (e.key === "Escape") finish(false);
  });
  input.addEventListener("blur", () => finish(true, true));
}

async function removeWord(tile, word) {
  try { words = await py.remove_word(word); } catch { return toast(t("toast.deleteFailed"), true); }
  tile.addEventListener("transitionend", () => renderWords(), { once: true });
  tile.classList.add("leaving");
}

function composerHint(text = t("vocab.hint", { n: cfg.hotword_max_length }), isError = false) {
  const msg = $("#composer-msg");
  msg.textContent = text;
  msg.classList.toggle("error", isError);
}

function bindComposer() {
  const form = $("#composer");
  const input = $("#word-input");
  input.addEventListener("input", () => {
    form.classList.remove("invalid");
    composerHint();
  });
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    try {
      words = await py.add_word(input.value);
    } catch (err) {
      shake(form);
      return composerHint(wordError(errorCode(err)), true);
    }
    input.value = "";
    renderWords(words[0]);
  });
}

/* ---------- model ----------
   The rail names the model; while it is not installed the button beside it
   downloads it, then shows a spinner (checking) and a progress ring. */

const MODEL_TIPS = { missing: "model.download", failed: "model.retry" };

function bindModel() {
  $("#model-action").addEventListener("click", () => py.download_models());
  watchModel((next) => {
    cfg.model = next;
    renderModel();
  });
}

function renderModel() {
  const { name, state, progress } = cfg.model;
  const action = $("#model-action");
  $("#model").dataset.state = state;
  $("#model-name").textContent = name;
  $("#model-name").title = name;
  if (MODEL_TIPS[state]) action.dataset.tip = t(MODEL_TIPS[state]);
  else delete action.dataset.tip;
  const ring = action.querySelector(".ring");
  if (state === "downloading") ring.style.setProperty("--p", progress);
  else ring.style.removeProperty("--p");
  action.querySelector(".model-pct").textContent = state === "downloading" ? percent(progress) : "";
}

/* ---------- settings ---------- */

function renderSettings() {
  if (!document.querySelector("#key-capture").classList.contains("listening")) {
    $("#hotkey-desc").textContent = t("settings.hotkey.desc");
    $("#hotkey-desc").classList.remove("error");
    $("#key-capture").textContent = keyLabel(cfg.hotkey);
  }
  segmented($("#seg-language"), LANGUAGES, cfg.language, (v) => saveSetting("language", v));
  segmented($("#seg-theme"), Object.fromEntries(THEMES.map((v) => [v, t(`theme.${v}`)])), cfg.theme,
    (v) => saveSetting("theme", v));
}

function bindSettings() {
  const btn = $("#key-capture");
  const stopListening = () => {
    btn.classList.remove("listening");
    py.suspend_hotkey(false);
    renderSettings();
  };
  btn.addEventListener("click", () => {
    if (btn.classList.contains("listening")) return stopListening();
    py.suspend_hotkey(true);
    btn.classList.add("listening");
    btn.textContent = t("settings.hotkey.listen");
  });
  btn.addEventListener("blur", () => btn.classList.contains("listening") && stopListening());
  btn.addEventListener("keydown", async (e) => {
    if (!btn.classList.contains("listening")) return;
    e.preventDefault();
    if (e.key === "Escape") return stopListening();
    if (!cfg.hotkeys.includes(e.code)) {
      shake(btn);
      $("#hotkey-desc").textContent = t("settings.hotkey.invalid");
      return $("#hotkey-desc").classList.add("error");
    }
    btn.classList.remove("listening");
    await saveSetting("hotkey", e.code);
    py.suspend_hotkey(false);
    toast(t("toast.saved"));
  });
}

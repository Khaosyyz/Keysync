import { h, icon, percent, segmented, THEMES, watchModel } from "./shared.js";
import { keyLabel, LANGUAGES, t } from "./i18n.js";

const STEPS = ["setup", "try"];
const BAR_COUNT = 36;
const GATE = 0.12;
const GAIN = 2.2;
const ATTACK = 0.6;
const RELEASE = 0.15;
const MENU_GAP = 6;
const MENU_MAX_HEIGHT = 280;
const STATUS = { missing: "spin", checking: "spin", failed: "fail", downloading: "ok", ready: "ok" };

/* First-run shell. Step "setup" runs the level meter and, when the models are
   missing, starts their download; step "try" leaves the hotkey live so the
   field can receive a real dictation. */
export function initOnboarding({ py, cfg, save, onFinish }) {
  const $ = (id) => document.getElementById(id);
  const picker = $("mic-picker");
  const menu = $("mic-menu");
  const bars = Array.from({ length: BAR_COUNT }, () => h("i"));
  $("ob-meter").append(...bars);

  let step = 0;
  let mics = null;
  let metering = false;
  let level = 0;
  let smooth = 0;
  let frame = 0;
  let meterCalls = Promise.resolve();
  let model = cfg.model;
  let fetched = model.state !== "ready";

  /* ---- level meter: bars light up from the left, the first one brightest ---- */

  function paint() {
    const lit = Math.min(BAR_COUNT, Math.ceil(Math.max(0, smooth - GATE) * GAIN * BAR_COUNT));
    bars.forEach((bar, i) => (bar.className = i >= lit ? "" : i === 0 ? "lit" : "soft"));
  }

  function tick() {
    smooth += (level - smooth) * (level > smooth ? ATTACK : RELEASE);
    paint();
    frame = requestAnimationFrame(tick);
  }

  const meterCall = (method) => (meterCalls = meterCalls.then(() => py[method]()));

  function setMetering(on) {
    if (on === metering) return;
    metering = on;
    level = smooth = 0;
    if (on) {
      $("ob-error").hidden = true;
      meterCall("meter_start");
      frame = requestAnimationFrame(tick);
    } else {
      cancelAnimationFrame(frame);
      paint();
      meterCall("meter_stop");
    }
  }

  window.addEventListener("ks:level", (e) => {
    if (metering) level = e.detail.value;
  });
  window.addEventListener("ks:meter_error", () => {
    $("ob-error").textContent = t("error.microphone");
    $("ob-error").hidden = false;
  });

  /* ---- model download: shown once the models were found missing ---- */

  function renderModel() {
    $("ob-model").hidden = !fetched;
    $("ob-model-status").className = `status ${STATUS[model.state]}`;
    $("ob-model-failed").hidden = model.state !== "failed";
    const progress = $("ob-model-progress");
    progress.hidden = !["downloading", "ready"].includes(model.state);
    progress.classList.toggle("done", model.state === "ready");
    $("ob-model-note").textContent = t(model.state === "ready" ? "ob.model.done" : "ob.model.downloading");
    $("ob-model-pct").textContent = percent(model.state === "ready" ? 1 : model.progress);
    $("ob-model-bar").style.width = percent(model.state === "ready" ? 1 : model.progress);
  }

  watchModel((next) => {
    model = next;
    fetched ||= model.state !== "ready";
    renderModel();
  });
  $("ob-model-retry").addEventListener("click", () => py.download_models());

  /* ---- microphone picker: a listbox positioned against the viewport ---- */

  function renderPicker() {
    const none = mics?.length === 0;
    $("mic-name").textContent = none ? t("ob.mic.none") : cfg.mic;
    picker.disabled = !mics?.length;
  }

  function openMenu() {
    const rect = picker.getBoundingClientRect();
    const below = innerHeight - rect.bottom - MENU_GAP * 2;
    const above = rect.top - MENU_GAP * 2;
    const down = below >= MENU_MAX_HEIGHT || below >= above;
    menu.style.width = `${rect.width}px`;
    menu.style.left = `${rect.left}px`;
    menu.style.maxHeight = `${Math.min(MENU_MAX_HEIGHT, down ? below : above)}px`;
    menu.style.top = down ? `${rect.bottom + MENU_GAP}px` : "";
    menu.style.bottom = down ? "" : `${innerHeight - rect.top + MENU_GAP}px`;
    menu.replaceChildren(...mics.map((name) => h("li", {
      class: "picker-option", role: "option", "aria-selected": String(name === cfg.mic), title: name,
      onclick: () => pickMic(name),
    }, h("span", {}, name), icon("check", 14))));
    menu.hidden = false;
    picker.setAttribute("aria-expanded", "true");
  }

  function closeMenu() {
    if (menu.hidden) return;
    menu.hidden = true;
    picker.setAttribute("aria-expanded", "false");
  }

  async function pickMic(name) {
    closeMenu();
    if (name === cfg.mic) return;
    Object.assign(cfg, await py.set_mic(name));
    renderPicker();
    if (metering) {
      meterCall("meter_stop");
      meterCall("meter_start");
    }
  }

  picker.addEventListener("click", () => (menu.hidden ? openMenu() : closeMenu()));
  document.addEventListener("pointerdown", (e) => {
    if (!menu.contains(e.target) && !picker.contains(e.target)) closeMenu();
  }, true);
  document.addEventListener("keydown", (e) => e.key === "Escape" && closeMenu());
  addEventListener("resize", closeMenu);
  document.querySelector(".ob-body").addEventListener("scroll", closeMenu, { passive: true });

  /* ---- steps ---- */

  function go(index) {
    step = index;
    document.querySelectorAll(".ob-page").forEach((page) => (page.hidden = page.dataset.step !== STEPS[step]));
    closeMenu();
    setMetering(STEPS[step] === "setup");
    if (STEPS[step] === "setup" && model.state === "missing") py.download_models();
    render();
  }

  async function finish() {
    closeMenu();
    setMetering(false);
    Object.assign(cfg, await py.complete_onboarding());
    onFinish();
  }

  $("ob-skip").addEventListener("click", finish);
  $("ob-next").addEventListener("click", () => (step < STEPS.length - 1 ? go(step + 1) : finish()));

  /* Rebuilds every string this shell owns from the current language and cfg. */
  function render() {
    const id = STEPS[step];
    $("ob-title").textContent = t(id === "setup" ? "ob.welcome" : "ob.try.title");
    $("ob-desc").textContent = t(id === "setup" ? "ob.welcome.desc" : "ob.try.desc");
    $("ob-next").textContent = t(step < STEPS.length - 1 ? "ob.next" : "ob.enter");
    $("ob-steps").replaceChildren(...STEPS.map((name, i) => h("button", {
      class: `ob-step${i === step ? " active" : ""}`, "aria-label": t(`ob.step.${name}`),
      onclick: () => i !== step && go(i),
    })));
    segmented($("ob-language"), LANGUAGES, cfg.language, (v) => save("language", v));
    segmented($("ob-theme"), Object.fromEntries(THEMES.map((v) => [v, t(`theme.${v}`)])), cfg.theme,
      (v) => save("theme", v));
    $("ob-field").placeholder = t("ob.try.placeholder", { key: keyLabel(cfg.hotkey) });
    renderPicker();
    renderModel();
  }

  py.list_mics().then((names) => {
    mics = names;
    renderPicker();
  });

  return { render, enter: () => go(step) };
}

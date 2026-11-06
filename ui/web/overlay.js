import { api, h, icon, percent } from "./shared.js";
import { setLanguage, t } from "./i18n.js";

const BAR_COUNT = 9;
const BAR_FLOOR = 0.24;
const NOISE_GATE = 0.05;
const SENSITIVITY = 1.8;
const ATTACK = 0.8;
const RELEASE = 0.3;
const BAR_RANDOM = 0.65;

const stage = document.getElementById("stage");
let py, cfg;
let hideTimer, autoHideMs, live, complete;

const booted = (async () => {
  py = await api;
  cfg = await py.bootstrap();
  setLanguage(cfg.language);
})();

const handlers = { recording, level, transcribing, polishing, result, error: failure, config, model_missing: modelMissing };
for (const [name, handle] of Object.entries(handlers))
  window.addEventListener(`ks:${name}`, async (e) => {
    await booted;
    handle(e.detail);
  });

stage.addEventListener("mouseenter", () => clearTimeout(hideTimer));
stage.addEventListener("mouseleave", () => autoHideMs && schedule(autoHideMs));

function config(next) {
  Object.assign(cfg, next);
  setLanguage(cfg.language);
}

function schedule(ms) {
  autoHideMs = ms;
  clearTimeout(hideTimer);
  hideTimer = setTimeout(hide, ms);
}

function stopLive() {
  if (!live) return;
  cancelAnimationFrame(live.frame);
  live = null;
}

function show(view, ms) {
  complete = null;
  stopLive();
  clearTimeout(hideTimer);
  autoHideMs = null;
  stage.replaceChildren(view);
  py.fit(view.offsetWidth, view.offsetHeight, devicePixelRatio);
  if (ms) schedule(ms);
}

function hide() {
  stopLive();
  clearTimeout(hideTimer);
  autoHideMs = null;
  py.hide();
}

const closeBtn = () => h("button", { class: "icon-btn", onclick: hide }, icon("close", 14));

const wave = () => h("div", { class: "wave" }, Array.from({ length: BAR_COUNT }, () => h("i")));


function recording() {
  const meter = wave();
  show(h("div", { class: "pill" }, meter));
  const bars = [...meter.children];
  const current = Array.from({ length: BAR_COUNT }, () => 0);
  live = { targets: current.map(() => 0) };
  const draw = () => {
    bars.forEach((bar, i) => {
      const target = live.targets[i];
      current[i] += (target - current[i]) * (target > current[i] ? ATTACK : RELEASE);
      bar.style.transform = `scaleY(${BAR_FLOOR + (1 - BAR_FLOOR) * current[i]})`;
    });
    live.frame = requestAnimationFrame(draw);
  };
  draw();
}

function level({ value }) {
  if (!live) return;
  const gated = Math.min(1, Math.max(0, (value - NOISE_GATE) / (1 - NOISE_GATE)) * SENSITIVITY);
  live.targets = Array.from({ length: BAR_COUNT },
    () => gated * (1 - BAR_RANDOM + BAR_RANDOM * Math.random()));
}

function transcribing() {
  const bar = h("i");
  show(h("div", { class: "pill" }, h("span", {}, t("overlay.transcribing")), h("i", { class: "load" }, bar)));
  const fill = (width, ms) => {
    bar.style.transitionDuration = `${ms}ms`;
    bar.style.width = width;
  };
  requestAnimationFrame(() => requestAnimationFrame(() => fill("80%", cfg.load_ms)));
  complete = (after) => {
    complete = null;
    fill("100%", 150);
    setTimeout(after, 170);
  };
}

function polishing() {
  const bar = stage.querySelector(".pill .load i");
  if (complete && bar && cfg.polish_ms > 0) {
    bar.style.transitionDuration = `${cfg.polish_ms}ms`;
    bar.style.width = "96%";
  }
}

function result({ record }) {
  const settle = () => {
    if (record.delivery === "typed") return hide();
    if (record.delivery === "none") return notice(t("overlay.none"), t("overlay.noneHint"));
    deliver(record);
  };
  if (complete) return complete(settle);
  settle();
}

function deliver(record) {
  const idleFace = h("span", { class: "face on" }, icon("copy", 14), t("overlay.copy"));
  const doneFace = h("span", { class: "face" }, t("overlay.copied"));
  const copy = h("button", { class: "btn btn-primary btn-swap", onclick: async () => {
    try {
      await py.copy(record.text);
    } catch {
      doneFace.textContent = t("overlay.copyFailed");
    }
    idleFace.classList.remove("on");
    doneFace.classList.add("on");
    copy.classList.add("done");
    schedule(cfg.delivered_ms);
  } }, idleFace, doneFace);

  show(h("div", { class: "card" },
    h("div", { class: "card-head" }, icon("alert", 16), t("overlay.shown"), closeBtn()),
    h("p", { class: "card-text selectable" }, record.text),
    h("div", { class: "card-foot" }, h("span", {}, t("overlay.shownHint")), copy)), cfg.result_ms);
}

function notice(title, sub, alarm = true) {
  show(h("div", { class: alarm ? "card notice" : "card" },
    h("div", { class: "card-head" }, icon("alert", 16), title, closeBtn()),
    h("p", { class: "card-sub" }, sub)), cfg.notice_ms);
}

function modelMissing({ model }) {
  if (["checking", "downloading"].includes(model.state))
    return notice(t("overlay.modelBusy"), t("overlay.modelBusyHint", { pct: percent(model.progress) }), false);
  const download = h("button", { class: "btn btn-primary", onclick: () => {
    py.download_models();
    hide();
  } }, icon("download", 14), t("overlay.download"));
  show(h("div", { class: "card" },
    h("div", { class: "card-head" }, icon("alert", 16), t("overlay.noModel"), closeBtn()),
    h("div", { class: "card-foot" }, h("span", {}, t("overlay.noModelHint")), download)), cfg.result_ms);
}

function failure({ code }) {
  const settle = () => {
    const key = ["microphone", "engine"].includes(code) ? code : "internal";
    notice(t(`error.${key}`), t(`error.${key}Hint`));
  };
  if (complete) return complete(settle);
  settle();
}

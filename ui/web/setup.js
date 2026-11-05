import { api, captionRgb, isDark, onSystemScheme, percent } from "./shared.js";
import { setLanguage, t, translateStatic } from "./i18n.js";

const $ = (id) => document.getElementById(id);
let py, defaults;

const syncChrome = () => py.set_chrome(captionRgb(), isDark());

function show(view) {
  document.querySelectorAll(".view").forEach((v) => (v.hidden = v.dataset.view !== view));
}

function fail(code) {
  $("error").textContent = t(`setup.err.${code}`, { dir: defaults.dir });
  $("error").hidden = false;
  $("path").parentElement.classList.toggle("invalid", code !== "failed");
}

async function install() {
  $("error").hidden = true;
  $("path").parentElement.classList.remove("invalid");
  try {
    await py.install($("path").value);
  } catch (err) {
    return fail(err?.name === "SetupError" ? err.message : "failed");
  }
  $("bar").style.width = "0%";
  $("pct").textContent = percent(0);
  show("installing");
}

window.addEventListener("ks:progress", ({ detail }) => {
  $("bar").style.width = percent(detail.value);
  $("pct").textContent = percent(detail.value);
});
window.addEventListener("ks:done", () => show("done"));
window.addEventListener("ks:failed", () => {
  show("idle");
  fail("failed");
});

(async () => {
  try {
    py = await api;
    defaults = await py.bootstrap();
    setLanguage(defaults.language);
    translateStatic();
    $("path").value = defaults.dir;
    $("browse").addEventListener("click", async () => {
      const picked = await py.browse($("path").value);
      if (picked) $("path").value = picked;
    });
    $("install").addEventListener("click", install);
    $("path").addEventListener("keydown", (e) => e.key === "Enter" && install());
    $("open").addEventListener("click", () => py.launch());
    syncChrome();
    onSystemScheme(syncChrome);
  } finally {
    py?.ready();
  }
})();

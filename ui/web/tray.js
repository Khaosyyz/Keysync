import { api, applyTheme, onSystemScheme } from "./shared.js";
import { setLanguage, translateStatic } from "./i18n.js";

let theme = "system";

document.getElementById("open").addEventListener("click", () => api.then((py) => py.open_main()));
document.getElementById("quit").addEventListener("click", () => api.then((py) => py.quit()));

(async () => {
  const cfg = await (await api).bootstrap();
  theme = cfg.theme;
  setLanguage(cfg.language);
  applyTheme(theme);
  onSystemScheme(() => theme === "system" && applyTheme("system"));
  translateStatic();
})();

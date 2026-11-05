export const api = new Promise((resolve) => {
  if (window.pywebview?.api) resolve(window.pywebview.api);
  else window.addEventListener("pywebviewready", () => resolve(window.pywebview.api), { once: true });
});

const darkQuery = matchMedia("(prefers-color-scheme: dark)");

export function applyTheme(theme) {
  const root = document.documentElement;
  if (theme === "system") delete root.dataset.theme;
  else root.dataset.theme = theme;
}

export const isDark = () => {
  const theme = document.documentElement.dataset.theme;
  return theme ? theme === "dark" : darkQuery.matches;
};

export const onSystemScheme = (fn) => darkQuery.addEventListener("change", fn);

export function trackFocusMode() {
  const root = document.documentElement;
  addEventListener("keydown", (e) => e.key === "Tab" && (root.dataset.keyboard = ""), true);
  addEventListener("pointerdown", () => delete root.dataset.keyboard, true);
}

export function h(tag, props = {}, ...children) {
  const el = document.createElement(tag);
  for (const [key, value] of Object.entries(props)) {
    if (value == null || value === false) continue;
    if (key.startsWith("on")) el.addEventListener(key.slice(2), value);
    else if (key === "class") el.className = value;
    else if (key === "dataset") Object.assign(el.dataset, value);
    else el.setAttribute(key, value === true ? "" : value);
  }
  el.append(...children.flat().filter((c) => c != null && c !== false));
  return el;
}

export const icon = (name, size) =>
  h("span", { class: `icon i-${name}`, style: size ? `--size:${size}px` : null });

export const errorCode = (err) => (err?.name === "HotwordError" ? err.message : "unknown");

export const THEMES = ["system", "light", "dark"];

export function segmented(container, options, active, onPick) {
  container.replaceChildren(...Object.entries(options).map(([value, label]) =>
    h("button", { class: value === active ? "active" : null, onclick: () => value !== active && onPick(value) }, label)));
}

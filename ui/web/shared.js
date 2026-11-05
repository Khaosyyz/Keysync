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

/* The colour the title bar should take, read from the untransitioned .caption-probe. */
export const captionRgb = () =>
  getComputedStyle(document.querySelector(".caption-probe")).backgroundColor.match(/\d+/g).slice(0, 3).map(Number);

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

const CHECK_HOLD_MS = 700;

/* Delivers ks:model snapshots, holding "checking" long enough to be seen. */
export function watchModel(render) {
  let since = 0;
  let latest;
  let timer;
  window.addEventListener("ks:model", ({ detail }) => {
    if (detail.state === "checking" && latest?.state !== "checking") since = performance.now();
    latest = detail;
    clearTimeout(timer);
    const wait = detail.state === "checking" ? 0 : since + CHECK_HOLD_MS - performance.now();
    timer = setTimeout(() => render(latest), Math.max(0, wait));
  });
}

export const percent = (fraction) => `${Math.floor(fraction * 100)}%`;

export function segmented(container, options, active, onPick) {
  container.replaceChildren(...Object.entries(options).map(([value, label]) =>
    h("button", { class: value === active ? "active" : null, onclick: () => value !== active && onPick(value) }, label)));
}

/* Loaded before each page module, with no imports of its own, so it still
   reports when a module fails to load or its startup throws. */
const bridge = new Promise((resolve) => {
  if (window.pywebview?.api) resolve(window.pywebview.api);
  else window.addEventListener("pywebviewready", () => resolve(window.pywebview.api), { once: true });
});

const report = (message) => bridge.then((py) => py.log_error(message));

window.addEventListener("error", (e) =>
  report(`${e.message} (${e.filename?.split("/").pop()}:${e.lineno})`));
window.addEventListener("unhandledrejection", (e) =>
  report(`unhandled rejection: ${e.reason?.stack ?? e.reason}`));

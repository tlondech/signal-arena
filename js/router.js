import { setMainTab } from "./ui.js";
import { refreshAnalytics } from "./analytics.js";

const PATH_TO_TAB = {
  "/":          "signals",
  "/history":   "history",
  "/analytics": "analytics",
};
const TAB_TO_PATH = {
  signals:   "/",
  history:   "/history",
  analytics: "/analytics",
};

function activateTab(tab) {
  const resolved = TAB_TO_PATH[tab] ? tab : "signals";
  setMainTab(resolved);
  if (resolved === "analytics") refreshAnalytics();
}

export function navigate(tab) {
  const path = TAB_TO_PATH[tab] ?? "/";
  if (window.location.pathname !== path) {
    history.pushState({ tab }, "", path);
  }
  activateTab(tab);
}

export function initRouter() {
  window.addEventListener("popstate", (e) => {
    const tab = e.state?.tab ?? PATH_TO_TAB[window.location.pathname] ?? "signals";
    activateTab(tab);
  });

  const initialTab = PATH_TO_TAB[window.location.pathname] ?? "signals";
  if (!PATH_TO_TAB[window.location.pathname]) {
    history.replaceState({ tab: "signals" }, "", "/");
  } else {
    history.replaceState({ tab: initialTab }, "", window.location.pathname);
  }
  return initialTab;
}

(() => {
  const root = document.querySelector("[data-librarian-analytics]");
  if (!(root instanceof HTMLElement)) return;

  const showError = (reason) => {
    if (root.getAttribute("aria-busy") !== "true") return;
    root.setAttribute("aria-busy", "false");
    root.querySelector("[data-analytics-loading]").hidden = true;
    root.querySelector("[data-analytics-results]").hidden = true;
    root.querySelector("[data-analytics-status]").textContent = "Analytics are unavailable.";
    root.querySelector("[data-analytics-error-message]").textContent =
      reason instanceof Error ? reason.message : "The analytics script could not run.";
    root.querySelector("[data-analytics-error]").hidden = false;
    root.querySelector("[data-analytics-retry]").hidden = false;
  };

  window.addEventListener("error", (event) => {
    const failedAnalyticsScript = event.target instanceof HTMLScriptElement
      && event.target.src.includes("/js/librarian-analytics.js");
    if (failedAnalyticsScript || (event.target === window && root.getAttribute("aria-busy") === "true")) {
      showError(event.error);
    }
  });
  window.addEventListener("unhandledrejection", (event) => showError(event.reason));
})();

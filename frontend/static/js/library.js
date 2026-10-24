(() => {
  const dialog = document.querySelector("[data-search-dialog]");
  if (!dialog) return;

  const input = dialog.querySelector("[data-search-input]");
  const closeButton = dialog.querySelector("[data-search-close]");

  document.querySelectorAll("[data-search-open]").forEach((button) => {
    button.addEventListener("click", () => {
      dialog.showModal();
      input?.focus();
    });
  });

  closeButton?.addEventListener("click", () => dialog.close());
  dialog.addEventListener("click", (event) => {
    if (event.target === dialog) dialog.close();
  });

  document.querySelectorAll("[data-select-all]").forEach((selectAll) => {
    selectAll.addEventListener("change", () => {
      const form = selectAll.closest("form");
      form?.querySelectorAll("[data-basket-select]").forEach((checkbox) => {
        checkbox.checked = selectAll.checked;
      });
    });
  });
})();

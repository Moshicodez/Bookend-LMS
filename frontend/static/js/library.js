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

  // Mobile menu toggle — works on every page
  const menuToggle = document.querySelector("[data-menu-toggle]");
  const navigation = document.querySelector("[data-navigation]");

  if (menuToggle instanceof HTMLButtonElement && navigation instanceof HTMLElement) {
    const setMenuOpen = (open) => {
      menuToggle.setAttribute("aria-expanded", String(open));
      menuToggle.setAttribute("aria-label", open ? "Close navigation menu" : "Open navigation menu");
      navigation.classList.toggle("is-open", open);
    };

    menuToggle.addEventListener("click", () => {
      setMenuOpen(menuToggle.getAttribute("aria-expanded") !== "true");
    });

    navigation.querySelectorAll("a").forEach((link) => {
      link.addEventListener("click", () => setMenuOpen(false));
    });

    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && menuToggle.getAttribute("aria-expanded") === "true") {
        setMenuOpen(false);
        menuToggle.focus();
      }
    });
  }

  // Account drawer — opens the side panel from the navbar account button.
  // The button is a <summary> inside a <details>; intercept its click so the
  // native dropdown never opens and the drawer is the only account menu.
  const drawer = document.querySelector("[data-account-drawer]");
  const backdrop = document.querySelector("[data-account-backdrop]");
  const openButtons = document.querySelectorAll("[data-account-open]");
  const closeButtons = document.querySelectorAll("[data-account-close]");
  const dropdowns = document.querySelectorAll("details.account-dropdown");

  const setDrawerOpen = (open) => {
    document.body.classList.toggle("is-drawer-open", open);
    if (drawer instanceof HTMLElement) {
      drawer.setAttribute("aria-hidden", String(!open));
    }
    dropdowns.forEach((details) => {
      details.toggleAttribute("open", false);
    });
  };

  if (drawer instanceof HTMLElement) {
    openButtons.forEach((button) => {
      button.addEventListener("click", (event) => {
        event.preventDefault();
        event.stopPropagation();
        setDrawerOpen(true);
      });
    });
    closeButtons.forEach((button) => {
      button.addEventListener("click", () => setDrawerOpen(false));
    });
    backdrop?.addEventListener("click", () => setDrawerOpen(false));
    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape") {
        setDrawerOpen(false);
      }
    });
  }
})();

(() => {
  const closeOtherPanels = (except) => {
    document.dispatchEvent(new CustomEvent("bookend:close-panels", {
      detail: { except },
    }));
  };

  const getFocusable = (panel) => Array.from(panel.querySelectorAll(
    'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])',
  )).filter((element) => element instanceof HTMLElement && element.getClientRects().length);

  const trapFocus = (panel, event) => {
    if (event.key !== "Tab") return;
    const focusable = getFocusable(panel);
    if (!focusable.length) {
      event.preventDefault();
      panel.focus();
      return;
    }
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    if (event.shiftKey && (document.activeElement === first || !panel.contains(document.activeElement))) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && (document.activeElement === last || !panel.contains(document.activeElement))) {
      event.preventDefault();
      first.focus();
    }
  };

  const dialog = document.querySelector("[data-search-dialog]");
  if (dialog instanceof HTMLDialogElement) {
    const input = dialog.querySelector("[data-search-input]");
    const closeButton = dialog.querySelector("[data-search-close]");

    document.querySelectorAll("[data-search-open]").forEach((button) => {
      button.addEventListener("click", () => {
        closeOtherPanels("search");
        dialog.showModal();
        input?.focus();
      });
    });

    closeButton?.addEventListener("click", () => dialog.close());
    dialog.addEventListener("click", (event) => {
      if (event.target === dialog) dialog.close();
    });
  }

  document.querySelectorAll("[data-select-all]").forEach((selectAll) => {
    selectAll.addEventListener("change", () => {
      const form = selectAll.closest("form");
      const checkboxes = form
        ? form.querySelectorAll("[data-basket-select], [data-book-select]")
        : document.querySelectorAll("[data-book-select]");
      checkboxes.forEach((checkbox) => {
        checkbox.checked = selectAll.checked;
      });
    });
  });
  const archivedBulkForm = document.querySelector("#archived-bulk-form");
  if (archivedBulkForm instanceof HTMLFormElement) {
    const checkboxes = Array.from(document.querySelectorAll("[data-book-select]"));
    const selectAll = document.querySelector("[data-select-all]");
    const bulkBar = archivedBulkForm.querySelector("[data-bulk-bar]");
    const selectedCount = archivedBulkForm.querySelector("[data-selected-count]");
    const updateSelection = () => {
      const selected = checkboxes.filter((checkbox) => checkbox.checked);
      if (bulkBar instanceof HTMLElement) bulkBar.hidden = selected.length === 0;
      if (selectedCount instanceof HTMLElement) selectedCount.textContent = String(selected.length);
      if (selectAll instanceof HTMLInputElement) {
        selectAll.checked = selected.length === checkboxes.length;
        selectAll.indeterminate = selected.length > 0 && selected.length < checkboxes.length;
      }
    };
    checkboxes.forEach((checkbox) => checkbox.addEventListener("change", updateSelection));
    selectAll?.addEventListener("change", updateSelection);
    archivedBulkForm.addEventListener("submit", (event) => {
      if (event.submitter instanceof HTMLElement && event.submitter.hasAttribute("data-confirm-skip")) {
        event.stopImmediatePropagation();
      }
    }, true);
    updateSelection();
  }

  const navDrawer = document.querySelector("[data-nav-drawer]");
  const navBackdrop = document.querySelector("[data-nav-drawer-backdrop]");
  const navToggle = document.querySelector("[data-nav-drawer-toggle]");
  const navClose = document.querySelector("[data-nav-drawer-close]");
  const genreDisclosure = navDrawer?.querySelector(".nav-drawer-more-genres");
  const genreDisclosureSummary = genreDisclosure?.querySelector("summary");
  let navCloseTimer;
  let genreCloseTimer;
  const closeGenreDisclosure = (returnFocus = false) => {
    if (!(genreDisclosure instanceof HTMLDetailsElement) || !genreDisclosure.open) return;
    genreDisclosure.dataset.closing = "true";
    window.clearTimeout(genreCloseTimer);
    genreCloseTimer = window.setTimeout(() => {
      genreDisclosure.open = false;
      delete genreDisclosure.dataset.closing;
      if (returnFocus && genreDisclosureSummary instanceof HTMLElement) genreDisclosureSummary.focus();
    }, window.matchMedia("(prefers-reduced-motion: reduce)").matches ? 1 : 180);
  };
  if (genreDisclosure instanceof HTMLDetailsElement && genreDisclosureSummary instanceof HTMLElement) {
    genreDisclosureSummary.addEventListener("click", (event) => {
      event.preventDefault();
      if (genreDisclosure.dataset.closing === "true") {
        window.clearTimeout(genreCloseTimer);
        delete genreDisclosure.dataset.closing;
      } else if (genreDisclosure.open) {
        closeGenreDisclosure();
      } else {
        window.clearTimeout(genreCloseTimer);
        delete genreDisclosure.dataset.closing;
        genreDisclosure.open = true;
      }
    });
    document.addEventListener("pointerdown", (event) => {
      if (!genreDisclosure.contains(event.target)) closeGenreDisclosure();
    });
  }
  const setNavDrawerOpen = (open, returnFocus = false) => {
    if (!(navDrawer instanceof HTMLElement) || !(navToggle instanceof HTMLButtonElement)) return;
    window.clearTimeout(navCloseTimer);
    navToggle.setAttribute("aria-expanded", String(open));
    navToggle.setAttribute("aria-label", open ? "Close menu" : "Open menu");
    navDrawer.setAttribute("aria-hidden", String(!open));
    navDrawer.inert = !open;
    document.body.classList.toggle("is-nav-open", open);
    document.body.classList.toggle("has-open-panel", open || document.body.classList.contains("is-drawer-open"));
    if (open) {
      closeOtherPanels("navigation");
      navDrawer.classList.add("is-open");
      requestAnimationFrame(() => navClose?.focus());
    } else {
      window.clearTimeout(genreCloseTimer);
      if (genreDisclosure instanceof HTMLDetailsElement) {
        genreDisclosure.open = false;
        delete genreDisclosure.dataset.closing;
      }
      navDrawer.classList.remove("is-open");
      if (returnFocus) navToggle.focus();
      navCloseTimer = window.setTimeout(() => {
        if (navToggle.getAttribute("aria-expanded") === "false") {
          navDrawer.setAttribute("aria-hidden", "true");
          navDrawer.inert = true;
        }
      }, 450);
    }
  };
  if (navDrawer instanceof HTMLElement && navToggle instanceof HTMLButtonElement) {
    navToggle.addEventListener("click", () => {
      setNavDrawerOpen(navToggle.getAttribute("aria-expanded") !== "true");
    });
    navClose?.addEventListener("click", () => setNavDrawerOpen(false, true));
    navBackdrop?.addEventListener("click", () => setNavDrawerOpen(false, true));
    navDrawer.querySelectorAll("a").forEach((link) => {
      link.addEventListener("click", () => setNavDrawerOpen(false, true));
    });
    navDrawer.querySelectorAll("form").forEach((form) => {
      form.addEventListener("submit", () => setNavDrawerOpen(false, true));
    });
    document.addEventListener("bookend:close-panels", (event) => {
      if (event.detail?.except !== "navigation") setNavDrawerOpen(false);
    });
    document.addEventListener("keydown", (event) => {
      if (navToggle.getAttribute("aria-expanded") !== "true") return;
      if (event.key === "Escape") {
        event.preventDefault();
        if (genreDisclosure instanceof HTMLDetailsElement && genreDisclosure.open) {
          event.stopImmediatePropagation();
          closeGenreDisclosure(true);
          return;
        }
        setNavDrawerOpen(false, true);
      } else {
        trapFocus(navDrawer, event);
      }
    });
    window.addEventListener("resize", () => {
      if (window.getComputedStyle(navToggle).display === "none") {
        setNavDrawerOpen(false, true);
      }
    });
  }

  const notificationButton = document.querySelector("[data-notification-toggle]");
  const notificationControl = document.querySelector("[data-notification-control]");
  const notificationPanel = document.querySelector("[data-notification-panel]");
  const notificationList = document.querySelector("[data-notification-list]");
  const notificationError = document.querySelector("[data-notification-error]");
  const markAllButton = document.querySelector("[data-notifications-read-all]");

  if (
    notificationButton instanceof HTMLButtonElement
    && notificationControl instanceof HTMLElement
    && notificationPanel instanceof HTMLElement
    && notificationList instanceof HTMLElement
    && notificationError instanceof HTMLElement
    && markAllButton instanceof HTMLButtonElement
  ) {
    const csrfToken = notificationButton.dataset.csrfToken || "";
    let activeNotifications = [];
    const setUnreadCount = (value) => {
      const count = Math.max(0, Number(value) || 0);
      notificationButton.dataset.unreadCount = String(count);
      notificationButton.setAttribute(
        "aria-label",
        `Notifications, ${count} unread`,
      );
      const badge = notificationButton.querySelector(".notification-count");
      if (badge instanceof HTMLElement) {
        badge.textContent = count > 9 ? "9+" : String(count);
        badge.hidden = count === 0;
      }
      markAllButton.disabled = count === 0;
    };

    const relativeTime = (value) => {
      const timestamp = new Date(value).getTime();
      if (!Number.isFinite(timestamp)) return "";
      const seconds = Math.round((timestamp - Date.now()) / 1000);
      const units = [
        ["year", 31536000],
        ["month", 2592000],
        ["week", 604800],
        ["day", 86400],
        ["hour", 3600],
        ["minute", 60],
      ];
      const formatter = new Intl.RelativeTimeFormat(undefined, { numeric: "auto" });
      for (const [unit, unitSeconds] of units) {
        if (Math.abs(seconds) >= unitSeconds) {
          return formatter.format(Math.round(seconds / unitSeconds), unit);
        }
      }
      return formatter.format(seconds, "second");
    };

    const iconPaths = {
      loan: '<path d="M5 4.5A2.5 2.5 0 0 1 7.5 2H20v18H7.5A2.5 2.5 0 0 0 5 22V4.5Z"></path><path d="M5 5h12M5 20h12"></path>',
      reservation: '<rect x="4" y="3" width="16" height="18" rx="2"></rect><path d="M8 8h8M8 12h5m-5 4 2 2 4-4"></path>',
      fee: '<circle cx="12" cy="12" r="9"></circle><path d="M15.5 8.5c-.7-.8-1.8-1.2-3.1-1.2-1.8 0-3 .8-3 2s1.2 1.8 3 2.2 3 1 3 2.3-1.2 2.2-3.2 2.2c-1.4 0-2.7-.5-3.5-1.5M12.4 5.5v13"></path>',
      inventory: '<path d="M4 4h16v4H4zM5 8v12h14V8m-9 4h4"></path>',
      member: '<circle cx="9" cy="8" r="3"></circle><path d="M3.5 20v-1.5a5.5 5.5 0 0 1 11 0V20zM16 5.3a3 3 0 0 1 0 5.8m1.5 3.1a4.8 4.8 0 0 1 3 4.5V20h-3"></path>',
      book: '<path d="M12 6.5v14m0-14C10.7 5 8.8 4 6.7 4 5.3 4 4 4.4 3 5.2v13c1-.8 2.3-1.2 3.7-1.2 2.1 0 4 .9 5.3 2.5m0-13C13.3 5 15.2 4 17.3 4c1.4 0 2.7.4 3.7 1.2v13c-1-.8-2.3-1.2-3.7-1.2-2.1 0-4 .9-5.3 2.5"></path>',
      general: '<path d="M18 9a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9"></path><path d="M10 21h4"></path>',
    };

    const createCategoryIcon = (category) => {
      const wrapper = document.createElement("span");
      wrapper.className = "notification-category-icon";
      wrapper.setAttribute("aria-hidden", "true");
      const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
      svg.setAttribute("viewBox", "0 0 24 24");
      svg.innerHTML = iconPaths[category] || iconPaths.general;
      wrapper.append(svg);
      return wrapper;
    };

    const showError = (message) => {
      notificationError.textContent = message;
      notificationError.hidden = !message;
    };

    const renderNotifications = (notifications) => {
      activeNotifications = notifications;
      notificationList.replaceChildren();
      if (!notifications.length) {
        const empty = document.createElement("p");
        empty.className = "notification-panel-empty";
        empty.textContent = "You're all caught up.";
        notificationList.append(empty);
        return;
      }

      const fragment = document.createDocumentFragment();
      notifications.forEach((item) => {
        const row = document.createElement("a");
        row.className = `notification-row${item.read ? "" : " is-unread"}`;
        row.href = item.link;
        row.dataset.readUrl = item.read_url;
        row.dataset.notificationId = String(item.id);

        const content = document.createElement("span");
        content.className = "notification-row-content";
        const title = document.createElement("span");
        title.className = "notification-row-title";
        title.textContent = item.title;
        const message = document.createElement("span");
        message.className = "notification-row-message";
        message.textContent = item.message;
        const time = document.createElement("time");
        time.dateTime = item.created_at;
        time.textContent = relativeTime(item.created_at);
        content.append(title, message, time);

        const unreadDot = document.createElement("span");
        unreadDot.className = "notification-unread-dot";
        unreadDot.setAttribute("aria-label", item.read ? "Read" : "Unread");
        row.append(createCategoryIcon(item.category), content, unreadDot);
        row.addEventListener("click", async (event) => {
          if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) {
            return;
          }
          event.preventDefault();
          showError("");
          try {
            const response = await fetch(item.read_url, {
              method: "POST",
              headers: {
                "Accept": "application/json",
                "X-CSRFToken": csrfToken,
              },
              credentials: "same-origin",
            });
            if (!response.ok) throw new Error("Could not mark this notification as read.");
            const result = await response.json();
            item.read = true;
            row.classList.remove("is-unread");
            unreadDot.setAttribute("aria-label", "Read");
            setUnreadCount(result.unread_count);
            window.location.assign(result.link || item.link);
          } catch {
            showError("This notification could not be opened. Please try again.");
          }
        });
        fragment.append(row);
      });
      notificationList.append(fragment);
    };

    const loadNotifications = async () => {
      notificationList.replaceChildren();
      const loading = document.createElement("p");
      loading.className = "notification-panel-loading";
      loading.textContent = "Loading notifications...";
      notificationList.append(loading);
      showError("");
      try {
        const response = await fetch(notificationButton.dataset.recentUrl, {
          headers: { "Accept": "application/json" },
          credentials: "same-origin",
        });
        if (!response.ok) throw new Error("Notifications could not be loaded.");
        const result = await response.json();
        renderNotifications(result.notifications);
        setUnreadCount(result.unread_count);
      } catch {
        notificationList.replaceChildren();
        showError("Notifications could not be loaded. Close the panel and try again.");
      }
    };

    const closePanel = (returnFocus = false) => {
      if (notificationButton.getAttribute("aria-expanded") !== "true") return;
      notificationButton.setAttribute("aria-expanded", "false");
      notificationPanel.setAttribute("aria-hidden", "true");
      notificationPanel.inert = true;
      notificationPanel.classList.remove("is-open");
      if (returnFocus) notificationButton.focus();
    };

    const openPanel = async () => {
      closeOtherPanels("notification");
      if (window.getComputedStyle(notificationPanel).position === "fixed") {
        const bell = notificationButton.getBoundingClientRect();
        const panelWidth = Math.min(360, window.innerWidth * 0.92);
        const maxRight = window.innerWidth - panelWidth - 8;
        const right = Math.max(
          8,
          Math.min(window.innerWidth - bell.right, maxRight),
        );
        notificationPanel.style.setProperty("--notification-panel-right", `${right}px`);
      }
      notificationPanel.setAttribute("aria-hidden", "false");
      notificationPanel.inert = false;
      notificationButton.setAttribute("aria-expanded", "true");
      requestAnimationFrame(() => {
        notificationPanel.classList.add("is-open");
        notificationPanel.focus();
      });
      await loadNotifications();
    };

    notificationButton.addEventListener("click", () => {
      if (notificationButton.getAttribute("aria-expanded") === "true") {
        closePanel();
      } else {
        void openPanel();
      }
    });

    markAllButton.addEventListener("click", async () => {
      showError("");
      markAllButton.disabled = true;
      try {
        const response = await fetch(notificationButton.dataset.readAllUrl, {
          method: "POST",
          headers: {
            "Accept": "application/json",
            "X-CSRFToken": csrfToken,
          },
          credentials: "same-origin",
        });
        if (!response.ok) throw new Error("Notifications could not be updated.");
        const result = await response.json();
        activeNotifications.forEach((item) => { item.read = true; });
        renderNotifications(activeNotifications);
        setUnreadCount(result.unread_count);
      } catch {
        showError("Notifications could not be updated. Please try again.");
        markAllButton.disabled = false;
      }
    });

    document.addEventListener("pointerdown", (event) => {
      if (!notificationControl.contains(event.target)) closePanel();
    });
    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape") closePanel(true);
    });
    document.addEventListener("bookend:close-panels", (event) => {
      if (event.detail?.except !== "notification") closePanel();
    });
  }

  const drawer = document.querySelector("[data-account-drawer]");
  const backdrop = document.querySelector("[data-account-backdrop]");
  const openButtons = document.querySelectorAll("[data-account-open]");
  const closeButtons = document.querySelectorAll("[data-account-close]");
  let activeAccountButton = null;
  let accountCloseTimer;

  const setDrawerOpen = (open) => {
    if (!(drawer instanceof HTMLElement)) return;
    window.clearTimeout(accountCloseTimer);
    if (open) closeOtherPanels("account");
    document.body.classList.toggle("is-drawer-open", open);
    document.body.classList.toggle("has-open-panel", open || document.body.classList.contains("is-nav-open"));
    drawer.setAttribute("aria-hidden", String(!open));
    drawer.inert = !open;
    openButtons.forEach((button) => {
      button.setAttribute("aria-expanded", String(open));
    });
    if (open) {
      activeAccountButton = document.activeElement;
      drawer.classList.add("is-open");
      getFocusable(drawer)[0]?.focus();
    } else if (activeAccountButton instanceof HTMLElement) {
      drawer.classList.remove("is-open");
      accountCloseTimer = window.setTimeout(() => {
        if (!document.body.classList.contains("is-drawer-open")) {
          drawer.setAttribute("aria-hidden", "true");
          drawer.inert = true;
        }
      }, 450);
      if (document.activeElement instanceof HTMLElement && drawer.contains(document.activeElement)) {
        activeAccountButton.focus();
      }
      activeAccountButton = null;
    }
  };

  if (drawer instanceof HTMLElement) {
    openButtons.forEach((button) => {
      button.addEventListener("click", () => setDrawerOpen(true));
    });
    closeButtons.forEach((button) => {
      button.addEventListener("click", () => setDrawerOpen(false));
    });
    backdrop?.addEventListener("click", () => setDrawerOpen(false));
    document.addEventListener("bookend:close-panels", (event) => {
      if (event.detail?.except !== "account") setDrawerOpen(false);
    });
    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && document.body.classList.contains("is-drawer-open")) {
        setDrawerOpen(false);
      } else if (document.body.classList.contains("is-drawer-open")) {
        trapFocus(drawer, event);
      }
    });
  }

  document.documentElement.classList.add("js");
  const viewTransitionPreference = window.matchMedia("(prefers-reduced-motion: no-preference)");
  let viewTransitionStyle = null;
  const setViewTransitions = () => {
    if (viewTransitionPreference.matches && !viewTransitionStyle) {
      viewTransitionStyle = document.createElement("style");
      viewTransitionStyle.textContent = "@view-transition { navigation: auto; }";
      document.head.append(viewTransitionStyle);
    } else if (!viewTransitionPreference.matches && viewTransitionStyle) {
      viewTransitionStyle.remove();
      viewTransitionStyle = null;
    }
  };
  setViewTransitions();
  viewTransitionPreference.addEventListener("change", setViewTransitions);

  const isAuthScreen = document.querySelector(".login-screen, .form-panel") !== null;
  const page = document.querySelector("[data-motion-page]");
  if (!isAuthScreen && page instanceof HTMLElement) {
    page.classList.add("motion-page-enter");
    page.addEventListener("animationend", () => page.classList.remove("motion-page-enter"), { once: true });

    document.querySelector(".landing-navbar")?.classList.add("motion-navbar-enter");
    const navbar = document.querySelector(".landing-navbar");
    navbar?.addEventListener("animationend", () => navbar.classList.remove("motion-navbar-enter"), { once: true });

    const staggerItems = new Set();
    page.querySelectorAll(".catalog-book-grid, .book-grid, .review-list, .profile-stats, .admin-table tbody").forEach((group) => {
      Array.from(group.children).forEach((item, index) => {
        item.style.setProperty("--i", String(index < 8 ? index : 0));
        staggerItems.add(item);
      });
    });

    const revealTargets = new Set([
      ...page.querySelectorAll(".book-detail-layout > section, .reviews-section, .admin-panel, .dashboard-card, .loan-card"),
      ...staggerItems,
    ]);
    if ("IntersectionObserver" in window) {
      const revealObserver = new IntersectionObserver((entries, observer) => {
        entries.forEach((entry) => {
          if (!entry.isIntersecting) return;
          entry.target.classList.add("is-visible");
          observer.unobserve(entry.target);
        });
      }, { threshold: 0.12 });
      revealTargets.forEach((target) => {
        target.classList.add("motion-reveal");
        revealObserver.observe(target);
      });
    }
  }

  document.querySelectorAll("[data-toast]").forEach((toast) => {
    if (!(toast instanceof HTMLElement)) return;
    let toastTimer;
    const dismissToast = () => {
      window.clearTimeout(toastTimer);
      toast.classList.add("is-leaving");
      window.setTimeout(
        () => toast.remove(),
        window.matchMedia("(prefers-reduced-motion: reduce)").matches ? 1 : 220,
      );
    };
    toast.querySelector("[data-toast-close]")?.addEventListener("click", dismissToast);
    if (!toast.classList.contains("error")) {
      toastTimer = window.setTimeout(dismissToast, 4000);
    }
  });

  const confirmDialog = document.querySelector("[data-confirm-dialog]");
  if (confirmDialog instanceof HTMLDialogElement) {
    const message = confirmDialog.querySelector("[data-confirm-message]");
    const title = confirmDialog.querySelector("#confirm-dialog-title");
    const note = confirmDialog.querySelector("[data-confirm-note]");
    const acceptButton = confirmDialog.querySelector("[data-confirm-accept]");
    const cancelButton = confirmDialog.querySelector("[data-confirm-cancel]");
    const phraseWrap = confirmDialog.querySelector("[data-confirm-phrase-wrap]");
    const phraseLabel = confirmDialog.querySelector("[data-confirm-phrase-label]");
    const phraseInput = confirmDialog.querySelector("[data-confirm-phrase-input]");
    let pendingForm = null;
    let pendingSubmitter = null;
    let previousFocus = null;
    let closeTimer;

    const closeConfirmDialog = (afterClose) => {
      if (!confirmDialog.open) return;
      confirmDialog.dataset.closing = "true";
      window.clearTimeout(closeTimer);
      closeTimer = window.setTimeout(() => {
        delete confirmDialog.dataset.closing;
        confirmDialog.close();
        if (previousFocus instanceof HTMLElement && previousFocus.isConnected) {
          previousFocus.focus();
        }
        previousFocus = null;
        afterClose?.();
      }, window.matchMedia("(prefers-reduced-motion: reduce)").matches ? 1 : 180);
    };

    const clearPending = () => {
      pendingForm = null;
      pendingSubmitter = null;
      if (phraseInput instanceof HTMLInputElement) phraseInput.value = "";
      if (acceptButton instanceof HTMLButtonElement) acceptButton.disabled = false;
    };

    const selectedBookSummary = (form) => {
      const selected = Array.from(document.querySelectorAll("[data-book-select]:checked"));
      if (form.id !== "archived-bulk-form" || !selected.length) return null;
      const titles = selected.slice(0, 5).map((checkbox) => checkbox.dataset.bookTitle || "Untitled book");
      const remainder = selected.length > titles.length ? `, and ${selected.length - titles.length} more` : "";
      return `${selected.length} book${selected.length === 1 ? "" : "s"} selected: ${titles.join(", ")}${remainder}. Loan history is kept; favorites and reviews are removed.`;
    };

    document.querySelectorAll("form[data-confirm-message]").forEach((form) => {
      form.addEventListener("submit", (event) => {
        if (event.submitter instanceof HTMLElement && event.submitter.hasAttribute("data-confirm-skip")) return;
        if (form.dataset.confirmed === "true") {
          delete form.dataset.confirmed;
          return;
        }
        event.preventDefault();
        pendingForm = form;
        pendingSubmitter = event.submitter instanceof HTMLElement ? event.submitter : null;
        previousFocus = document.activeElement;
        const summary = selectedBookSummary(form);
        if (message instanceof HTMLElement) message.textContent = summary || form.dataset.confirmMessage || "Are you sure you want to continue?";
        if (title instanceof HTMLElement) title.textContent = form.dataset.confirmTitle || "Confirm this action";
        if (note instanceof HTMLElement) {
          note.textContent = form.dataset.confirmNote || "";
          note.hidden = !form.dataset.confirmNote;
        }
        const phrase = form.dataset.confirmPhrase || "";
        if (phraseWrap instanceof HTMLElement) phraseWrap.hidden = !phrase;
        if (phraseLabel instanceof HTMLElement) phraseLabel.textContent = phrase;
        if (phraseInput instanceof HTMLInputElement) {
          phraseInput.value = "";
          phraseInput.dataset.requiredPhrase = phrase;
        }
        if (acceptButton instanceof HTMLButtonElement) {
          acceptButton.textContent = form.dataset.confirmAction || "Continue";
          acceptButton.classList.toggle("button-danger", form.dataset.confirmDanger === "true");
          acceptButton.disabled = Boolean(phrase);
        }
        confirmDialog.showModal();
        cancelButton?.focus();
      });
    });

    phraseInput?.addEventListener("input", () => {
      if (acceptButton instanceof HTMLButtonElement && phraseInput instanceof HTMLInputElement) {
        acceptButton.disabled = phraseInput.value !== phraseInput.dataset.requiredPhrase;
      }
    });

    confirmDialog.addEventListener("keydown", (event) => {
      if (event.key === "Escape") {
        event.preventDefault();
        clearPending();
        closeConfirmDialog();
        return;
      }
      if (event.key !== "Tab") return;
      const focusable = getFocusable(confirmDialog);
      if (!focusable.length) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    });

    acceptButton?.addEventListener("click", () => {
      if (!(pendingForm instanceof HTMLFormElement) || acceptButton.disabled) return;
      const form = pendingForm;
      const submitter = pendingSubmitter;
      const confirmationField = form.querySelector('input[name="confirm_action"]');
      if (confirmationField instanceof HTMLInputElement) confirmationField.value = "confirmed";
      const confirmTextField = form.querySelector('input[name="confirm_text"]');
      if (confirmTextField instanceof HTMLInputElement && phraseInput instanceof HTMLInputElement) {
        confirmTextField.value = phraseInput.value;
      }
      pendingForm = null;
      pendingSubmitter = null;
      form.dataset.confirmed = "true";
      closeConfirmDialog(() => {
        if (submitter instanceof HTMLElement) form.requestSubmit(submitter);
        else form.requestSubmit();
      });
    });

    cancelButton?.addEventListener("click", () => {
      clearPending();
      closeConfirmDialog();
    });
    confirmDialog.addEventListener("cancel", (event) => {
      event.preventDefault();
      clearPending();
      closeConfirmDialog();
    });
    confirmDialog.addEventListener("click", (event) => {
      if (event.target !== confirmDialog) return;
      clearPending();
      closeConfirmDialog();
    });
    document.addEventListener("bookend:close-panels", () => {
      if (confirmDialog.open) {
        clearPending();
        closeConfirmDialog();
      }
    });
  }
})();

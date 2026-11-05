(() => {
  const dialog = document.querySelector("[data-search-dialog]");
  if (dialog instanceof HTMLDialogElement) {
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
  }

  document.querySelectorAll("[data-select-all]").forEach((selectAll) => {
    selectAll.addEventListener("change", () => {
      const form = selectAll.closest("form");
      form?.querySelectorAll("[data-basket-select]").forEach((checkbox) => {
        checkbox.checked = selectAll.checked;
      });
    });
  });

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
    navigation.querySelectorAll("a, button").forEach((link) => {
      link.addEventListener("click", () => setMenuOpen(false));
    });
    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && menuToggle.getAttribute("aria-expanded") === "true") {
        setMenuOpen(false);
        menuToggle.focus();
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
    let closingTimer;

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
      notificationPanel.classList.remove("is-open");
      window.clearTimeout(closingTimer);
      closingTimer = window.setTimeout(() => {
        if (notificationButton.getAttribute("aria-expanded") === "false") {
          notificationPanel.hidden = true;
        }
      }, 260);
      if (returnFocus) notificationButton.focus();
    };

    const openPanel = async () => {
      window.clearTimeout(closingTimer);
      if (window.matchMedia("(max-width: 680px)").matches) {
        const bell = notificationButton.getBoundingClientRect();
        const panelWidth = Math.min(360, window.innerWidth * 0.92);
        const maxRight = window.innerWidth - panelWidth - 8;
        const right = Math.max(
          8,
          Math.min(window.innerWidth - bell.right, maxRight),
        );
        notificationPanel.style.setProperty("--notification-panel-right", `${right}px`);
      }
      notificationPanel.hidden = false;
      notificationPanel.setAttribute("aria-hidden", "false");
      notificationButton.setAttribute("aria-expanded", "true");
      requestAnimationFrame(() => notificationPanel.classList.add("is-open"));
      notificationPanel.focus();
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
  }

  const drawer = document.querySelector("[data-account-drawer]");
  const backdrop = document.querySelector("[data-account-backdrop]");
  const openButtons = document.querySelectorAll("[data-account-open]");
  const closeButtons = document.querySelectorAll("[data-account-close]");
  let activeAccountButton = null;

  const setDrawerOpen = (open) => {
    if (!(drawer instanceof HTMLElement)) return;
    document.body.classList.toggle("is-drawer-open", open);
    drawer.setAttribute("aria-hidden", String(!open));
    openButtons.forEach((button) => {
      button.setAttribute("aria-expanded", String(open));
    });
    if (open) {
      activeAccountButton = document.activeElement;
      drawer.querySelector("button, a")?.focus();
    } else if (activeAccountButton instanceof HTMLElement) {
      activeAccountButton.focus();
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
    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && document.body.classList.contains("is-drawer-open")) {
        setDrawerOpen(false);
      }
    });
  }
})();

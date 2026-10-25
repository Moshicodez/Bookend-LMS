const bookStage    = document.querySelector("[data-book-stage]");
const bookTrigger  = document.querySelector("[data-book-trigger]");
const bookInvitation = document.querySelector("[data-book-invitation]");
const bookCard     = document.querySelector("#book-card");
const bookPages    = document.querySelector(".book-pages");
const rightPage    = document.querySelector("[data-right-page]");

const openBook = (focusForm = false) => {
  if (!(bookStage instanceof HTMLElement) || !(bookCard instanceof HTMLElement)) return;

  bookStage.classList.add("is-open");
  bookTrigger?.setAttribute("aria-expanded", "true");
  bookInvitation?.setAttribute("aria-hidden", "true");
  bookInvitation?.setAttribute("inert", "");
  bookCard.removeAttribute("inert");
  bookCard.setAttribute("aria-hidden", "false");

  if (focusForm) {
    setTimeout(() => {
      const target = bookPages?.dataset.page === "register" ? "#email" : "#login-username";
      document.querySelector(target)?.focus();
    }, 500);
  }
};

// ── open book on trigger click ────────────────────────────────────────────────
bookTrigger?.addEventListener("click", () => {
  openBook(true);
  bookTrigger.blur();
});

if (window.matchMedia("(max-width: 760px)").matches) {
  openBook();
} else if (bookStage?.classList.contains("is-open")) {
  bookCard?.removeAttribute("inert");
  bookCard?.setAttribute("aria-hidden", "false");
}

// ── in-place page flip ────────────────────────────────────────────────────────
document.querySelectorAll("[data-flip], [data-page-turn]").forEach((link) => {
  link.addEventListener("click", (e) => {
    e.preventDefault();
    if (!(bookPages instanceof HTMLElement) || !(rightPage instanceof HTMLElement)) return;

    const currentPage = bookPages.dataset.page ?? "login";
    const targetPage  = link.dataset.flip
      ?? (link.dataset.pageTurn === "next" ? "register" : "login");
    if (currentPage === targetPage) return;

    const goingForward = targetPage === "register";
    const animClass    = goingForward ? "is-turning" : "is-turning-back";

    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      bookPages.dataset.page = targetPage;
      return;
    }

    rightPage.style.pointerEvents = "none";
    bookPages.classList.add(animClass);

    // forward: 90deg is at 40% of 800ms = 320ms
    // backward: 90deg is at 60% of 800ms = 480ms
    const swapAt = goingForward ? 320 : 480;

    setTimeout(() => {
      bookPages.dataset.page = targetPage;
    }, swapAt);

    setTimeout(() => {
      bookPages.classList.remove(animClass);
      rightPage.style.removeProperty("pointer-events");
    }, 800);
  });
});

// ── password toggles ──────────────────────────────────────────────────────────
document.querySelectorAll("[data-password-toggle]").forEach((btn) => {
  btn.addEventListener("click", () => {
    const inputId = btn.dataset.passwordToggle;
    const input   = document.getElementById(inputId);
    if (!(input instanceof HTMLInputElement)) return;
    const visible = input.type === "text";
    input.type = visible ? "password" : "text";
    btn.textContent = visible ? "Show" : "Hide";
    btn.setAttribute("aria-label",   visible ? "Show password" : "Hide password");
    btn.setAttribute("aria-pressed", String(!visible));
  });
});

document.querySelectorAll(".login-form").forEach((form) => {
  const isRegisterForm = form instanceof HTMLFormElement && form.classList.contains("register-form");
  const password = isRegisterForm ? form.querySelector("#reg-password") : null;
  const confirmation = isRegisterForm ? form.querySelector("#reg-confirm") : null;
  const passwordError = isRegisterForm ? form.querySelector('[data-field-error="password"]') : null;
  const confirmationError = isRegisterForm
    ? form.querySelector('[data-field-error="confirm_password"]')
    : null;

  const validateRegistrationPasswords = () => {
    if (
      !(password instanceof HTMLInputElement) ||
      !(confirmation instanceof HTMLInputElement) ||
      !(passwordError instanceof HTMLElement) ||
      !(confirmationError instanceof HTMLElement)
    ) return false;

    const tooShort = password.value.length < 8;
    const mismatch = password.value !== confirmation.value;
    passwordError.textContent = tooShort ? "Password must be at least 8 characters." : "";
    passwordError.hidden = !tooShort;
    confirmationError.textContent = mismatch ? "Passwords don't match." : "";
    confirmationError.hidden = !mismatch;
    password.setAttribute("aria-invalid", String(tooShort));
    confirmation.setAttribute("aria-invalid", String(mismatch));
    return tooShort || mismatch;
  };

  if (
    password instanceof HTMLInputElement &&
    confirmation instanceof HTMLInputElement
  ) {
    password.addEventListener("input", validateRegistrationPasswords);
    confirmation.addEventListener("input", validateRegistrationPasswords);
  }

  form.addEventListener("submit", (event) => {
    if (isRegisterForm) {
      if (validateRegistrationPasswords()) {
        event.preventDefault();
        if (password instanceof HTMLInputElement && password.value.length < 8) {
          password.focus();
        } else if (confirmation instanceof HTMLInputElement) {
          confirmation.focus();
        }
        return;
      }
    }

    if (!(form instanceof HTMLFormElement)) return;
    const submitButton = form.querySelector('button[type="submit"]');
    const submitLabel = submitButton?.querySelector("[data-submit-label]");
    if (!(submitButton instanceof HTMLButtonElement) || !(submitLabel instanceof HTMLElement)) return;

    submitButton.disabled = true;
    form.setAttribute("aria-busy", "true");
    submitLabel.textContent = submitButton.dataset.loadingLabel ?? "Submitting...";
  });
});

const bookStage = document.querySelector("[data-book-stage]");
const bookTrigger = document.querySelector("[data-book-trigger]");
const bookInvitation = document.querySelector("[data-book-invitation]");
const loginCard = document.querySelector("#login-card");
const passwordToggle = document.querySelector("[data-password-toggle]");

bookTrigger?.addEventListener("click", () => {
  if (!(bookStage instanceof HTMLElement) || !(loginCard instanceof HTMLElement)) {
    return;
  }

  bookStage.classList.add("is-open");
  bookTrigger.setAttribute("aria-expanded", "true");
  bookTrigger.blur();
  bookInvitation?.setAttribute("aria-hidden", "true");
  bookInvitation?.setAttribute("inert", "");
  loginCard.removeAttribute("inert");
  loginCard.setAttribute("aria-hidden", "false");

  const focusDelay = window.matchMedia("(prefers-reduced-motion: reduce)").matches ? 0 : 900;
  window.setTimeout(() => {
    document.querySelector("[data-initial-focus]")?.focus();
  }, focusDelay);
});

if (bookStage?.classList.contains("is-open")) {
  document.querySelector("[data-initial-focus]")?.focus();
}

passwordToggle?.addEventListener("click", () => {
  const passwordInput = document.querySelector("#password");

  if (!(passwordInput instanceof HTMLInputElement)) {
    return;
  }

  const isVisible = passwordInput.type === "text";
  passwordInput.type = isVisible ? "password" : "text";
  passwordToggle.textContent = isVisible ? "Show" : "Hide";
  passwordToggle.setAttribute("aria-label", isVisible ? "Show password" : "Hide password");
  passwordToggle.setAttribute("aria-pressed", String(!isVisible));
});

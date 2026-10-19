const bookStage    = document.querySelector("[data-book-stage]");
const bookTrigger  = document.querySelector("[data-book-trigger]");
const bookInvitation = document.querySelector("[data-book-invitation]");
const bookCard     = document.querySelector("#book-card");
const bookPages    = document.querySelector(".book-pages");
const rightPage    = document.querySelector("[data-right-page]");

// ── open book on trigger click ────────────────────────────────────────────────
bookTrigger?.addEventListener("click", () => {
  if (!(bookStage instanceof HTMLElement) || !(bookCard instanceof HTMLElement)) return;

  bookStage.classList.add("is-open");
  bookTrigger.setAttribute("aria-expanded", "true");
  bookTrigger.blur();
  bookInvitation?.setAttribute("aria-hidden", "true");
  bookInvitation?.setAttribute("inert", "");
  bookCard.removeAttribute("inert");
  bookCard.setAttribute("aria-hidden", "false");
});

if (bookStage?.classList.contains("is-open")) {
  document.querySelector("[data-initial-focus]")?.focus();
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

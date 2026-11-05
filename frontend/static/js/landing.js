const carouselButtons = Array.from(document.querySelectorAll("[data-carousel-target]"));
const updateCarouselButtons = (track) => {
  if (!(track instanceof HTMLElement)) return;
  const maxScroll = track.scrollWidth - track.clientWidth;
  const buttons = carouselButtons.filter((button) => button.dataset.carouselTarget === track.id);
  buttons.forEach((button) => {
    const direction = Number(button.dataset.carouselDirection);
    button.disabled = direction < 0
      ? track.scrollLeft <= 1
      : track.scrollLeft >= maxScroll - 1;
  });
};

document.querySelectorAll(".book-carousel[id]").forEach((track) => {
  if (!(track instanceof HTMLElement)) return;
  track.addEventListener("scroll", () => updateCarouselButtons(track), { passive: true });
  window.addEventListener("resize", () => updateCarouselButtons(track));
  requestAnimationFrame(() => updateCarouselButtons(track));
});

carouselButtons.forEach((button) => {
  button.addEventListener("click", () => {
    const track = document.getElementById(button.dataset.carouselTarget || "");
    if (!(track instanceof HTMLElement)) return;

    const direction = Number(button.dataset.carouselDirection);
    track.scrollBy({
      left: direction * Math.max(track.clientWidth * 0.78, 240),
      behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth",
    });
  });
});

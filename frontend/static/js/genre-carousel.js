const genreRow = document.querySelector("[data-genre-row]");
const genreRing = document.querySelector("[data-genre-ring]");
const genrePanel = document.querySelector("#genre-books-panel");
const genreCarousel = document.querySelector("[data-genre-carousel]");
const genreCaret = document.querySelector("[data-genre-caret]");

if (genreRow instanceof HTMLElement &&
    genreRing instanceof HTMLElement &&
    genrePanel instanceof HTMLElement &&
    genreCarousel instanceof HTMLElement &&
    genreCaret instanceof HTMLElement) {
  const genreCards = Array.from(genreRing.querySelectorAll("[data-genre-card]"));
  const genrePanels = Array.from(genrePanel.querySelectorAll("[data-genre-panel]"));
  const genreArrows = Array.from(genreCarousel.querySelectorAll("[data-genre-direction]"));
  const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const angleStep = 360 / genreCards.length;
  const driftSpeed = angleStep / 3;
  let rotation = 0;
  let selectedIndex = -1;
  let frameId;
  let previousFrame = 0;
  let pointerStart = null;
  let pointerSample = null;
  let dragVelocity = 0;
  let momentumFrame;
  let dragged = false;
  let suppressClick = false;

  const wrapIndex = (index) => (index + genreCards.length) % genreCards.length;
  const nearestIndex = () => wrapIndex(Math.round(-rotation / angleStep));
  const shortestIndexOffset = (from, to) => {
    let offset = wrapIndex(to - from);
    if (offset > genreCards.length / 2) offset -= genreCards.length;
    return offset;
  };

  const updateCaret = () => {
    const selected = genreCards[selectedIndex];
    const cardBounds = selected.getBoundingClientRect();
    const panelBounds = genreCarousel.parentElement.getBoundingClientRect();
    const position = cardBounds.left + cardBounds.width / 2 - panelBounds.left;
    genreCaret.style.left = `${Math.min(panelBounds.width - 18, Math.max(18, position))}px`;
  };

  const render = () => {
    genreRing.style.transform = `rotateY(${rotation}deg)`;
    const frontIndex = nearestIndex();
    const stepRadians = Math.PI / 180;

    genreCards.forEach((card, index) => {
      const angle = ((rotation + index * angleStep) % 360 + 360) % 360;
      const normalizedAngle = angle > 180 ? angle - 360 : angle;
      const facing = Math.cos(normalizedAngle * stepRadians);
      const distance = Math.abs(shortestIndexOffset(frontIndex, index));
      card.style.setProperty("--genre-opacity", String(Math.max(0, (facing + 0.18) / 1.18)));
      card.style.zIndex = String(Math.round((facing + 1) * 50));
      card.classList.toggle("is-selected", index === frontIndex);
      card.setAttribute("aria-pressed", String(index === frontIndex));
      card.setAttribute("aria-hidden", String(distance > 2));
      card.tabIndex = index === frontIndex ? 0 : -1;
      card.inert = distance > 2;
    });

    if (frontIndex !== selectedIndex) {
      selectedIndex = frontIndex;
      const selected = genreCards[selectedIndex];
      genrePanels.forEach((panel) => {
        panel.hidden = panel.dataset.genreName !== selected.dataset.genreName;
      });
      genreArrows.forEach((arrow) => {
        const direction = Number(arrow.dataset.genreDirection);
        const target = genreCards[wrapIndex(selectedIndex + direction)];
        arrow.setAttribute("aria-label", `Show ${target.dataset.genreName}`);
      });
      updateCaret();
    }
  };

  const snapTo = (index, focus = false) => {
    const nextIndex = wrapIndex(index);
    const offset = shortestIndexOffset(selectedIndex, nextIndex);
    rotation -= offset * angleStep;
    genreRing.classList.add("is-snapping");
    render();
    window.setTimeout(() => genreRing.classList.remove("is-snapping"), 900);
    if (focus) genreCards[nextIndex].focus();
  };

  const stopDrifting = () => {
    if (frameId) window.cancelAnimationFrame(frameId);
    frameId = undefined;
    previousFrame = 0;
  };

  const settleDrag = () => {
    const startRotation = rotation;
    const momentum = Math.max(-24, Math.min(24, dragVelocity * 140));
    const duration = 260;
    let startTime;

    const animateSettle = (timestamp) => {
      if (startTime === undefined) startTime = timestamp;
      const progress = Math.min((timestamp - startTime) / duration, 1);
      const eased = 1 - (1 - progress) ** 3;
      rotation = startRotation + momentum * eased;
      render();
      if (progress < 1) {
        momentumFrame = window.requestAnimationFrame(animateSettle);
      } else {
        momentumFrame = undefined;
        snapTo(nearestIndex());
        startDrifting();
      }
    };

    momentumFrame = window.requestAnimationFrame(animateSettle);
  };

  const drift = (timestamp) => {
    if (!previousFrame) previousFrame = timestamp;
    const elapsed = Math.min(timestamp - previousFrame, 50);
    previousFrame = timestamp;
    rotation -= elapsed * driftSpeed / 1000;
    render();
    frameId = window.requestAnimationFrame(drift);
  };

  const startDrifting = () => {
    if (reducedMotion ||
        frameId ||
        momentumFrame ||
        pointerStart ||
        document.hidden ||
        genreCarousel.matches(":hover") ||
        genreCarousel.contains(document.activeElement) ||
        genreCards.length < 2) return;
    frameId = window.requestAnimationFrame(drift);
  };

  const setRadius = () => {
    const radius = Math.min(330, Math.max(210, genreRow.clientWidth * 0.32));
    genreCards.forEach((card, index) => {
      card.style.setProperty("--genre-angle", `${index * angleStep}deg`);
      card.style.setProperty("--genre-radius", `${radius}px`);
    });
    updateCaret();
  };

  genreRing.addEventListener("click", (event) => {
    if (suppressClick) {
      event.preventDefault();
      event.stopPropagation();
      suppressClick = false;
      return;
    }
    const target = event.target;
    if (!(target instanceof Element)) return;
    const card = target.closest("[data-genre-card]");
    const index = genreCards.indexOf(card);
    if (index >= 0) snapTo(index);
  });

  genreRow.addEventListener("keydown", (event) => {
    if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
    event.preventDefault();
    const nextIndex = event.key === "Home"
      ? 0
      : event.key === "End"
        ? genreCards.length - 1
        : selectedIndex + (event.key === "ArrowRight" ? 1 : -1);
    snapTo(nextIndex, true);
  });

  genreArrows.forEach((arrow) => {
    arrow.addEventListener("click", () => {
      snapTo(selectedIndex + Number(arrow.dataset.genreDirection));
    });
  });

  genreRow.addEventListener("pointerdown", (event) => {
    if (!event.isPrimary || event.button !== 0) return;
    if (!(event.target instanceof Element) || !event.target.closest("[data-genre-card]")) return;
    pointerStart = { x: event.clientX, y: event.clientY, rotation };
    pointerSample = { x: event.clientX, time: event.timeStamp };
    dragVelocity = 0;
    dragged = false;
    stopDrifting();
    if (momentumFrame) window.cancelAnimationFrame(momentumFrame);
    momentumFrame = undefined;
    genreRing.classList.remove("is-snapping");
    genreRow.setPointerCapture(event.pointerId);
  });

  genreRow.addEventListener("pointermove", (event) => {
    if (!pointerStart) return;
    const deltaX = event.clientX - pointerStart.x;
    const deltaY = event.clientY - pointerStart.y;
    if (!dragged && Math.abs(deltaX) > 6 && Math.abs(deltaX) > Math.abs(deltaY)) dragged = true;
    if (!dragged) return;
    rotation = pointerStart.rotation - deltaX * 0.22;
    const elapsed = event.timeStamp - pointerSample.time;
    if (elapsed > 0) {
      const sampleVelocity = -(event.clientX - pointerSample.x) * 0.22 / elapsed;
      dragVelocity = dragVelocity * 0.65 + sampleVelocity * 0.35;
    }
    pointerSample = { x: event.clientX, time: event.timeStamp };
    render();
  });

  const finishDrag = () => {
    if (!pointerStart) return;
    pointerStart = null;
    pointerSample = null;
    if (dragged) {
      dragged = false;
      suppressClick = true;
      window.setTimeout(() => { suppressClick = false; }, 0);
      settleDrag();
    } else {
      startDrifting();
    }
  };

  genreRow.addEventListener("pointerup", finishDrag);
  genreRow.addEventListener("pointercancel", finishDrag);

  genreCarousel.addEventListener("mouseenter", stopDrifting);
  genreCarousel.addEventListener("mouseleave", startDrifting);
  genreCarousel.addEventListener("focusin", stopDrifting);
  genreCarousel.addEventListener("focusout", (event) => {
    if (!genreCarousel.contains(event.relatedTarget)) startDrifting();
  });
  document.addEventListener("visibilitychange", () => {
    if (document.hidden) stopDrifting();
    else startDrifting();
  });
  window.addEventListener("resize", setRadius);

  selectedIndex = 0;
  setRadius();
  render();
  startDrifting();
}

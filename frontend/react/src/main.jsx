import React, { useEffect, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import CircularCarousel from "./components/CircularCarousel.jsx";
import "./genre-carousel-theme.css";

const mount = document.getElementById("genre-carousel-root");

function GenreCarousel({ items, genrePanels }) {
  const [bookActive, setBookActive] = useState(false);
  const bookActiveRef = useRef(bookActive);
  const keyboardFocusRef = useRef(false);
  const updateBookActive = (active) => {
    bookActiveRef.current = active;
    setBookActive(active);
  };

  useEffect(() => {
    const panel = document.getElementById("genre-books-panel");
    if (!panel) return undefined;

    let hovered = false;
    let held = false;
    let focused = false;
    let lastInputWasPointer = false;
    let resumeTimer;

    const cancelResume = () => {
      window.clearTimeout(resumeTimer);
      resumeTimer = undefined;
    };
    const activate = () => {
      cancelResume();
      updateBookActive(true);
    };
    const resumeWhenIdle = () => {
      if (hovered || held || focused) return;
      cancelResume();
      resumeTimer = window.setTimeout(() => {
        resumeTimer = undefined;
        if (!hovered && !held && !focused) updateBookActive(false);
      }, 600);
    };
    const handlePointerEnter = () => {
      hovered = true;
      activate();
    };
    const handlePointerLeave = () => {
      hovered = false;
      resumeWhenIdle();
    };
    const handlePointerDown = () => {
      lastInputWasPointer = true;
      focused = false;
      keyboardFocusRef.current = false;
      held = true;
      activate();
    };
    const handlePointerEnd = () => {
      held = false;
      resumeWhenIdle();
    };
    const handleFocusIn = () => {
      if (lastInputWasPointer) return;
      focused = true;
      keyboardFocusRef.current = true;
      activate();
    };
    const handleKeyDown = () => {
      lastInputWasPointer = false;
      if (panel.contains(document.activeElement)) {
        focused = true;
        keyboardFocusRef.current = true;
        activate();
      }
    };
    const handleFocusOut = (event) => {
      if (event.relatedTarget instanceof Node && panel.contains(event.relatedTarget)) return;
      focused = false;
      keyboardFocusRef.current = false;
      resumeWhenIdle();
    };

    panel.addEventListener("pointerenter", handlePointerEnter);
    panel.addEventListener("pointerleave", handlePointerLeave);
    panel.addEventListener("pointerdown", handlePointerDown);
    panel.addEventListener("pointerup", handlePointerEnd);
    panel.addEventListener("pointercancel", handlePointerEnd);
    window.addEventListener("pointerup", handlePointerEnd);
    window.addEventListener("pointercancel", handlePointerEnd);
    window.addEventListener("keydown", handleKeyDown, true);
    panel.addEventListener("focusin", handleFocusIn);
    panel.addEventListener("focusout", handleFocusOut);

    return () => {
      cancelResume();
      panel.removeEventListener("pointerenter", handlePointerEnter);
      panel.removeEventListener("pointerleave", handlePointerLeave);
      panel.removeEventListener("pointerdown", handlePointerDown);
      panel.removeEventListener("pointerup", handlePointerEnd);
      panel.removeEventListener("pointercancel", handlePointerEnd);
      window.removeEventListener("pointerup", handlePointerEnd);
      window.removeEventListener("pointercancel", handlePointerEnd);
      window.removeEventListener("keydown", handleKeyDown, true);
      panel.removeEventListener("focusin", handleFocusIn);
      panel.removeEventListener("focusout", handleFocusOut);
    };
  }, []);

  return (
    <div
      className="genre-carousel-stage"
      onPointerEnter={() => {
        if (!keyboardFocusRef.current) updateBookActive(false);
      }}
      onFocusCapture={() => updateBookActive(false)}
    >
      <CircularCarousel
        items={items}
        preset="cylinder"
        intro="rise"
        cardWidth={220}
        aspectRatio={1}
        speed={14}
        captions={false}
        gap={25}
        tilt={-5}
        curve={1}
        perspective={2500}
        autoplay={bookActive ? "off" : "drift"}
        interval={3}
        direction="left"
        momentum={0.6}
        snap
        pauseOnHover
        focusOnClick
        draggable
        parallax={0.3}
        stretch={0.5}
        fadeColor="#000000"
        depthFade={0.55}
        innerShade={0.6}
        cornerRadius={12}
        onChange={(index) => {
          if (bookActiveRef.current) return;
          const selectedGenre = items[index]?.title;
          genrePanels.forEach((panel) => {
            panel.hidden = panel.dataset.genreName !== selectedGenre;
          });
        }}
      />
    </div>
  );
}

if (mount) {
  const items = JSON.parse(mount.dataset.items || "[]");
  const genrePanels = Array.from(document.querySelectorAll("[data-genre-panel]"));
  createRoot(mount).render(
    <GenreCarousel items={items} genrePanels={genrePanels} />
  );
}

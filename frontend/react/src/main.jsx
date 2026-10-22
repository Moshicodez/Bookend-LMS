import React from "react";
import { createRoot } from "react-dom/client";
import CircularCarousel from "./components/CircularCarousel.jsx";
import "./genre-carousel-theme.css";

const mount = document.getElementById("genre-carousel-root");

if (mount) {
  const items = JSON.parse(mount.dataset.items || "[]");
  const genrePanels = Array.from(document.querySelectorAll("[data-genre-panel]"));

  createRoot(mount).render(
    <div className="genre-carousel-stage">
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
        autoplay="drift"
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
          const selectedGenre = items[index]?.title;
          genrePanels.forEach((panel) => {
            panel.hidden = panel.dataset.genreName !== selectedGenre;
          });
        }}
      />
    </div>
  );
}

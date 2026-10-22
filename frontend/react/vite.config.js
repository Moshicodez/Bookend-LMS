import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  base: "/static/dist/",
  publicDir: false,
  build: {
    outDir: "../static/dist",
    emptyOutDir: true,
    rollupOptions: {
      input: "src/main.jsx",
      output: {
        entryFileNames: "genre-carousel.js",
        chunkFileNames: "assets/[name]-[hash].js",
        assetFileNames: (asset) => (
          asset.name?.endsWith(".css")
            ? "genre-carousel.css"
            : "assets/[name]-[hash][extname]"
        ),
      },
    },
  },
});

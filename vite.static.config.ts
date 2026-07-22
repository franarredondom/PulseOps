import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  root: "static",
  publicDir: "../public",
  plugins: [react()],
  define: {
    "process.env.NEXT_PUBLIC_API_URL": JSON.stringify(
      "https://pulseops-api-qlqu.onrender.com",
    ),
  },
  build: {
    outDir: "../dist-static",
    emptyOutDir: true,
  },
});

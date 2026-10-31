import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// `npm run build` writes dist/, a folder of static files with fingerprinted names under assets/.
// Cornea caches those for a year and serves index.html for every page route.
export default defineConfig({
  plugins: [react()],
});

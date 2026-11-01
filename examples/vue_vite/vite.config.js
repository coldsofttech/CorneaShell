import vue from "@vitejs/plugin-vue";
import { defineConfig } from "vite";

// `npm run build` writes dist/, a folder of static files that Cornea serves.
export default defineConfig({
  plugins: [vue()],
});

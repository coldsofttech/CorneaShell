// Builds the script and styles that ship in the Python wheel (../src/cornea_menus/static), and the
// npm package (dist/) with the React wrapper. Run: npm run build
import { build } from "esbuild";
import { mkdirSync } from "node:fs";

const common = { bundle: true, target: "es2020", minify: false, legalComments: "none", logLevel: "info" };
const out = "../src/cornea_menus/static";
mkdirSync(out, { recursive: true });

// What the page loads: one plain script each, no module system, so it works under the strict policy.
await build({ ...common, entryPoints: { "menus": "src/global.ts" }, outdir: out, format: "iife", minify: true });
await build({ ...common, entryPoints: { "frame": "src/frame-entry.ts" }, outdir: out, format: "iife", minify: true });

// For bundlers: the core and the React wrapper. React stays the app's own copy.
await build({
  ...common,
  entryPoints: { index: "src/index.ts", react: "src/react.tsx" },
  outdir: "dist",
  format: "esm",
  external: ["react", "react/jsx-runtime"],
});

import * as menus from "./index";

// A plain <script> gets one global. (`window.cornea` is frozen by client.js, so it cannot hold this.)
(window as unknown as { corneaMenus: typeof menus }).corneaMenus = Object.freeze({ ...menus });

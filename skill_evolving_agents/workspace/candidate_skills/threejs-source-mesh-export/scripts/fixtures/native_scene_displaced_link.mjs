// Native fixture variant: exposes createScene() but displaces only the support
// link.  Produce from this module and check against the clean native_scene.mjs
// to exercise a link-placement violation.

export { createDisplacedLinkScene as createScene } from "./native_scene.mjs";

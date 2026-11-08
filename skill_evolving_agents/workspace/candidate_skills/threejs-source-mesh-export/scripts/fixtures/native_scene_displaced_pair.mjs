// Native fixture variant: createScene() returns a graph whose outer-rim part
// and support link are both displaced.  Check it against the clean
// native_scene.mjs; the one-command producer must fail both meshes.

export { createDisplacedPairScene as createScene } from "./native_scene.mjs";

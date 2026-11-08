// Native near-miss fixture: one part Group and its link OBJ are renamed.
//
// Run the producer on this module, then check the produced tree against the
// clean native_scene.mjs module.  The checker must report the missing
// wheel_structure part directory and link OBJ plus the extra renamed ones.

import { createScene as createCleanScene } from "./native_scene.mjs";

export function createScene() {
  const scene = createCleanScene();
  scene.children[0].children[0].name = "wheel_assembly";
  return scene;
}

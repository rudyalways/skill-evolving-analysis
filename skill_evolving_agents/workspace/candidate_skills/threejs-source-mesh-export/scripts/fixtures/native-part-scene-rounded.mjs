// Native near-miss fixture: one live position coordinate loses precision.
//
// Run the producer on this module, then check the produced tree against the
// clean native_scene.mjs module.  The name sets still match, so the checker
// must fail only on the inexact coordinate path.

import { createScene as createCleanScene } from "./native_scene.mjs";

export function createScene() {
  const scene = createCleanScene();
  const rim = scene.children[0].children[0].children[0];
  const positions = rim.geometry.attributes.position.array;
  for (let i = 0; i < positions.length; i += 1) {
    const rounded = Math.round(Number(positions[i]) * 1000) / 1000;
    if (Math.abs(rounded - Number(positions[i])) > 1e-6) {
      positions[i] = rounded;
      break;
    }
  }
  return scene;
}

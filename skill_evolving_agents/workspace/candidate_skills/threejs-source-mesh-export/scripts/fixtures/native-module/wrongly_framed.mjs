// Near-miss native module: identical geometry, counts, names, and manifest to
// the clean fixture, but the returned root carries a +90 degree X rotation.
// Exporting it with the mandated -90 degree X frame transfer cancels the frame
// change, so the OBJ looks self-consistent while every world-space position is
// wrong. An independent world-space preflight must reject it and name the frame.

import { createScene as createCleanScene } from "./scene.mjs";

export function createScene() {
  const scene = createCleanScene();
  scene.name = "root";
  scene.rotation = [Math.PI / 2, 0, 0];
  return scene;
}

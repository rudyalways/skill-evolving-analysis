// Native fixture variant: one part's live position buffer is distorted along
// X while its normals are recomputed for that same distortion.  The result is
// internally self-consistent (a locally patched reference that reads the same
// createScene() buffers would accept it) but geometrically wrong against the
// clean source.  It exists to prove the independent surface preflight fails
// closed instead of trusting a producer-derived expectation.

import { createScene as createCleanScene } from "./native_scene.mjs";

const X_SCALE = 1.18;

export function createScene() {
  const scene = createCleanScene();
  const rim = scene.children[0].children[0].children[0];
  const geometry = rim.geometry;
  const position = geometry.attributes.position.array;
  const normal = geometry.attributes.normal.array;
  for (let i = 0; i < position.length; i += 3) {
    position[i] *= X_SCALE;
  }
  // Inverse-transpose of the non-uniform X scale, then renormalize.
  for (let i = 0; i < normal.length; i += 3) {
    normal[i] /= X_SCALE;
    const length = Math.hypot(normal[i], normal[i + 1], normal[i + 2]);
    if (length) {
      normal[i] /= length;
      normal[i + 1] /= length;
      normal[i + 2] /= length;
    }
  }
  return scene;
}

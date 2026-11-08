// One-command native-module fixture.
//
// The same executable module consumed by
// `node scripts/export_threejs_scene.mjs --module scripts/fixtures/native-scene.mjs`
// exposes createScene().  Its `outer_rim` mesh is indexed and its `support`
// mesh is non-indexed, so the command must call toNonIndexed() for the indexed
// mesh and traverse the non-indexed triangles directly.

import { createScene as createCleanScene } from "./native_scene.mjs";

export function createScene() {
  return createCleanScene();
}

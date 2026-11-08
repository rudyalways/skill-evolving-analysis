// Native fixture variant: exposes createScene() but returns the displaced graph.
// Produce from this module while checking against native_scene.mjs to exercise
// a real placement violation.

export { createDisplacedScene as createScene } from "./native_scene.mjs";

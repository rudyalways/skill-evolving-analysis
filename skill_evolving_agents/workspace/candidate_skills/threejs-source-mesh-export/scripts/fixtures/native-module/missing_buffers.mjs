// Rejection fixture: createScene() exists, but the returned mesh has no
// geometry.attributes.position buffer.
export function createScene() {
  return {
    name: "root",
    position: [0, 0, 0],
    children: [{
      name: "shell",
      position: [0, 0, 0],
      children: [{ name: "panel", geometry: { attributes: {}, index: null } }],
    }],
  };
}

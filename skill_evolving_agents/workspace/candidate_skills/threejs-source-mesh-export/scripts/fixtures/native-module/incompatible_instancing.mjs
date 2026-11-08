// Native-module near-miss: an instanced mesh declares no readable
// instanceMatrix. The producer must fail closed with UNSUPPORTED_INSTANCING
// instead of guessing instance transforms or probing further.

const node = (name, extra = {}) => ({
  name,
  position: [0, 0, 0],
  rotation: [0, 0, 0],
  scale: [1, 1, 1],
  children: [],
  ...extra,
});

export function createScene() {
  return node("root", {
    children: [
      node("fixture", {
        isInstancedMesh: true,
        count: 3,
        geometry: {
          attributes: {
            position: {
              array: new Float32Array([0, 0, 0, 1, 0, 0, 0, 1, 0]),
              itemSize: 3,
            },
          },
          index: { array: new Uint32Array([0, 1, 2]), itemSize: 1 },
        },
      }),
    ],
  });
}

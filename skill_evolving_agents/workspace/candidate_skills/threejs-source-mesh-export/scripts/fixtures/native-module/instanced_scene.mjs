// Native Three.js-compatible module for producer-first, hierarchy, and
// instanced-mesh regression coverage. It depends on no npm package.
//
// createScene() returns a nested non-identity parent chain and an
// InstancedMesh with two instances. The producer must compose every world
// transform and expand every instance from its own instanceMatrix while
// exporting the shared geometry's native position/index buffers.

const indexedGeometry = (positions, indices) => {
  const position = {
    array: new Float32Array(positions),
    itemSize: 3,
    count: positions.length / 3,
  };
  return {
    attributes: { position },
    index: {
      array: new Uint32Array(indices),
      itemSize: 1,
      count: indices.length,
    },
    toNonIndexed() {
      const expanded = new Float32Array(indices.length * 3);
      const source = position.array;
      indices.forEach((vertex, i) => {
        expanded[i * 3] = source[vertex * 3];
        expanded[i * 3 + 1] = source[vertex * 3 + 1];
        expanded[i * 3 + 2] = source[vertex * 3 + 2];
      });
      return { attributes: { position: { array: expanded, itemSize: 3 } }, index: null };
    },
  };
};

const node = (name, extra = {}) => ({
  name,
  position: [0, 0, 0],
  rotation: [0, 0, 0],
  scale: [1, 1, 1],
  children: [],
  ...extra,
});

// Column-major 4x4 translation used by THREE.InstancedMesh.instanceMatrix.
const instanceTranslation = (x, y, z) => {
  const matrix = new Float32Array([
    1, 0, 0, 0,
    0, 1, 0, 0,
    0, 0, 1, 0,
    0, 0, 0, 1,
  ]);
  matrix[12] = x;
  matrix[13] = y;
  matrix[14] = z;
  return matrix;
};

export function createScene() {
  const curved = indexedGeometry(
    [
      0.25, 1.125, -0.375,
      1.0000000000000002, 0.5, 2.25,
      -0.1234567890123456, 3.5, 0.75,
      4.25, -2.125, 0.3333333333333333,
      1.75, 0.625, -1.5,
      -2.5, 1.0625, 0.4375,
    ],
    [0, 1, 2, 2, 3, 4, 4, 5, 0, 1, 3, 5],
  );
  const plate = node("plate", {
    geometry: indexedGeometry(
      [
        0.1, 0.2, 0.3,
        1.1, 0.25, -0.4,
        -0.5, 1.4, 0.6,
      ],
      [0, 1, 2],
    ),
  });
  const lugs = node("lugs", {
    isInstancedMesh: true,
    count: 2,
    instanceMatrix: {
      array: new Float32Array([
        ...instanceTranslation(0, 0, 0),
        ...instanceTranslation(2.5, -0.75, 1.25),
      ]),
      itemSize: 16,
    },
    geometry: curved,
  });
  return node("root", {
    children: [
      node("rig", {
        position: [0.5, -1.25, 2],
        rotation: [0.25, -0.5, 0.125],
        scale: [1, 2, 1],
        children: [
          plate,
          node("hub", {
            position: [-0.75, 0.5, 1.5],
            rotation: [0.125, 0.25, -0.375],
            children: [lugs],
          }),
        ],
      }),
    ],
  });
}

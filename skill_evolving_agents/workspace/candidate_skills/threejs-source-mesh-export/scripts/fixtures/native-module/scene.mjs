// Native Three.js-compatible scene module used by the producer-first evals.
// It deliberately depends on no npm package: createScene() returns objects with
// the same fields the producer reads from live THREE.Object3D and BufferGeometry
// instances (position/rotation/scale/children, geometry.attributes.position,
// geometry.index, geometry.toNonIndexed()).

const geometry = (positions, indices) => {
  const position = {
    array: new Float32Array(positions),
    itemSize: 3,
    count: positions.length / 3,
  };
  const value = { attributes: { position }, index: null };
  if (indices) {
    value.index = { array: new Uint32Array(indices), itemSize: 1, count: indices.length };
    value.toNonIndexed = () => {
      const expanded = new Float32Array(indices.length * 3);
      const source = position.array;
      indices.forEach((vertex, i) => {
        expanded[i * 3] = source[vertex * 3];
        expanded[i * 3 + 1] = source[vertex * 3 + 1];
        expanded[i * 3 + 2] = source[vertex * 3 + 2];
      });
      return { attributes: { position: { array: expanded, itemSize: 3 } }, index: null };
    };
  }
  return value;
};

const node = (name, extra = {}) => {
  const value = {
    name,
    position: [0, 0, 0],
    rotation: [0, 0, 0],
    scale: [1, 1, 1],
    children: [],
    ...extra,
  };
  value.updateMatrixWorld = function updateMatrixWorld() {
    refreshWorld(value, null);
    return value;
  };
  return value;
};

const identity = () => [
  [1, 0, 0, 0],
  [0, 1, 0, 0],
  [0, 0, 1, 0],
  [0, 0, 0, 1],
];

const multiply = (a, b) => a.map((row, i) =>
  row.map((_, j) => [0, 1, 2, 3].reduce((sum, k) => sum + a[i][k] * b[k][j], 0)));

const localMatrix = (value) => {
  const [rx, ry, rz] = value.rotation.map(Number);
  const [sx, sy, sz] = value.scale.map(Number);
  const [tx, ty, tz] = value.position.map(Number);
  const [cx, sxr] = [Math.cos(rx), Math.sin(rx)];
  const [cy, syr] = [Math.cos(ry), Math.sin(ry)];
  const [cz, szr] = [Math.cos(rz), Math.sin(rz)];
  const rxM = [[1, 0, 0, 0], [0, cx, -sxr, 0], [0, sxr, cx, 0], [0, 0, 0, 1]];
  const ryM = [[cy, 0, syr, 0], [0, 1, 0, 0], [-syr, 0, cy, 0], [0, 0, 0, 1]];
  const rzM = [[cz, -szr, 0, 0], [szr, cz, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]];
  const scale = [[sx, 0, 0, 0], [0, sy, 0, 0], [0, 0, sz, 0], [0, 0, 0, 1]];
  const rotation = multiply(multiply(rxM, ryM), rzM);
  const local = multiply(rotation, scale);
  local[0][3] = tx;
  local[1][3] = ty;
  local[2][3] = tz;
  return local;
};

const toElements = (m) => [
  m[0][0], m[1][0], m[2][0], 0,
  m[0][1], m[1][1], m[2][1], 0,
  m[0][2], m[1][2], m[2][2], 0,
  m[0][3], m[1][3], m[2][3], 1,
];

const refreshWorld = (value, parentWorld) => {
  const world = parentWorld ? multiply(parentWorld, localMatrix(value))
    : localMatrix(value);
  value.matrixWorld = { elements: toElements(world) };
  for (const child of value.children || []) {
    refreshWorld(child, world);
  }
};

export function createScene() {
  const panel = node("panel", {
    geometry: geometry(
      [
        0.1 + 0.2, Math.PI / 7, -1 / 3,
        1.0000000000000002, 0.5, 2.25,
        -0.1234567890123456, 3.5, 0.75,
        4.25, -2.125, 0.3333333333333333,
      ],
      [0, 1, 2, 2, 1, 3],
    ),
  });
  const brace = node("brace", {
    geometry: geometry(
      [
        0.7, -0.2, 1.1,
        1.4, 0.25, -0.6,
        -0.35, 0.8, 0.05,
      ],
    ),
  });
  return node("root", {
    children: [
      node("shell", {
        position: [0.5, -1.25, 2],
        rotation: [0.25, -0.5, 0.125],
        children: [panel, brace],
      }),
    ],
  });
}

// Native ES-module fixture: createScene() returns a Three.js-style object graph.
//
// Nodes are Object3D-compatible and geometries are BufferGeometry-compatible:
// the producer reads geometry.attributes.position, optional normal/uv
// attributes, and geometry.index directly.  The legacy type/parameters fields
// are retained only so inherited checkers can still identify the source
// primitive; the source-native producer and checker never consume them.
//
// outer_rim is indexed and support is non-indexed, so one fixture exercises
// both toNonIndexed() triangle expansion and direct non-indexed traversal.

function group(name, position, children, rotation = [0, 0, 0],
               scale = [1, 1, 1]) {
  return { name, type: "Group", position, rotation, scale, children };
}

function attribute(array, itemSize) {
  return {
    array: Float32Array.from(array),
    itemSize,
    count: array.length / itemSize,
  };
}

function bufferGeometry(position, normal, uv, index, parameters, type) {
  return {
    type,
    parameters,
    attributes: {
      position: attribute(position, 3),
      normal: attribute(normal, 3),
      uv: attribute(uv, 2),
    },
    index: index ? { array: Uint32Array.from(index), itemSize: 1, count: index.length } : null,
  };
}

function mesh(name, geometry, position, rotation = [0, 0, 0],
              scale = [1, 1, 1], material = { name: "native_material" }) {
  return {
    name,
    type: "Mesh",
    position,
    rotation,
    scale,
    material,
    children: [],
    geometry,
  };
}

function boxGeometry(width, height, depth) {
  const [x, y, z] = [width / 2, height / 2, depth / 2];
  const faces = [
    { n: [0, 0, 1], v: [[-x, -y, z], [x, -y, z], [x, y, z], [-x, y, z]] },
    { n: [0, 0, -1], v: [[x, -y, -z], [-x, -y, -z], [-x, y, -z], [x, y, -z]] },
    { n: [1, 0, 0], v: [[x, -y, z], [x, -y, -z], [x, y, -z], [x, y, z]] },
    { n: [-1, 0, 0], v: [[-x, -y, -z], [-x, -y, z], [-x, y, z], [-x, y, -z]] },
    { n: [0, 1, 0], v: [[-x, y, z], [x, y, z], [x, y, -z], [-x, y, -z]] },
    { n: [0, -1, 0], v: [[-x, -y, -z], [x, -y, -z], [x, -y, z], [-x, -y, z]] },
  ];
  const position = [];
  const normal = [];
  const uv = [];
  for (const face of faces) {
    for (const triangle of [[0, 1, 2], [0, 2, 3]]) {
      for (const i of triangle) {
        position.push(...face.v[i]);
        normal.push(...face.n);
        uv.push(...[[0, 0], [1, 0], [1, 1], [0, 1]][i]);
      }
    }
  }
  return bufferGeometry(position, normal, uv, null, { width, height, depth },
    "BoxGeometry");
}

function cylinderGeometry(radiusTop, radiusBottom, height, radialSegments) {
  const position = [];
  const normal = [];
  const uv = [];
  const index = [];
  const half = height / 2;
  for (let i = 0; i < radialSegments; i += 1) {
    const angle = 2 * Math.PI * i / radialSegments;
    const [s, c] = [Math.sin(angle), Math.cos(angle)];
    for (const [y, r] of [[-half, radiusBottom], [half, radiusTop]]) {
      position.push(r * c, y, r * s);
      const slope = (radiusBottom - radiusTop) / height;
      const length = Math.hypot(1, slope);
      normal.push(c / length, slope / length, s / length);
      uv.push(i / radialSegments, y < 0 ? 0 : 1);
    }
  }
  for (let i = 0; i < radialSegments; i += 1) {
    const a = 2 * i;
    const b = a + 1;
    const c = 2 * ((i + 1) % radialSegments);
    const d = c + 1;
    index.push(a, c, b, b, c, d);
  }
  for (const [y, ny] of [[-half, -1], [half, 1]]) {
    const center = position.length / 3;
    position.push(0, y, 0);
    normal.push(0, ny, 0);
    uv.push(0.5, 0.5);
    const first = position.length / 3;
    for (let i = 0; i < radialSegments; i += 1) {
      const angle = 2 * Math.PI * i / radialSegments;
      const r = y < 0 ? radiusBottom : radiusTop;
      position.push(r * Math.cos(angle), y, r * Math.sin(angle));
      normal.push(0, ny, 0);
      uv.push(0.5 + 0.5 * Math.cos(angle), 0.5 + 0.5 * Math.sin(angle));
    }
    for (let i = 0; i < radialSegments; i += 1) {
      const a = first + i;
      const b = first + (i + 1) % radialSegments;
      if (ny > 0) index.push(center, a, b);
      else index.push(center, b, a);
    }
  }
  return bufferGeometry(position, normal, uv, index, {
    radiusTop,
    radiusBottom,
    height,
    radialSegments,
  }, "CylinderGeometry");
}

function buildScene() {
  return group("Scene", [0.05, -0.02, 0.01], [
    group("assembly", [0.05, 0.02, -0.01], [
      group("wheel_structure", [0.0, 0.0, 0.0], [
        mesh("outer_rim",
          cylinderGeometry(0.35, 0.35, 0.18, 32),
          [0.4, 0.4, 0.0]),
      ]),
      mesh("support",
        boxGeometry(0.8, 0.12, 0.2),
        [-0.3, 0.05, 0.0], [0, 0, 0], [1, 1, 1],
        { name: "support_material" }),
    ]),
  ]);
}

export function createScene() {
  return buildScene();
}

// The same native graph with one part translated.  The producer reads the
// displaced live position buffer; the checker keeps the clean module as its
// expectation and reports a placement violation.
export function createDisplacedScene() {
  const scene = buildScene();
  const rim = scene.children[0].children[0].children[0];
  rim.position = [rim.position[0] + 1.46, rim.position[1], rim.position[2]];
  return scene;
}

// A variant that displaces only the support link.
export function createDisplacedLinkScene() {
  const scene = buildScene();
  const support = scene.children[0].children[1];
  support.position = [support.position[0], support.position[1] + 0.075,
                      support.position[2]];
  return scene;
}

// A variant that displaces both an outer-rim part and a support link.
export function createDisplacedPairScene() {
  const scene = buildScene();
  const rim = scene.children[0].children[0].children[0];
  rim.position = [rim.position[0] + 1.46, rim.position[1], rim.position[2]];
  const support = scene.children[0].children[1];
  support.position = [support.position[0], support.position[1] + 0.075,
                      support.position[2]];
  return scene;
}

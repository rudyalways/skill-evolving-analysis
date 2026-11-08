// Native ES-module fixture for part-level decomposition.
//
// createScene() returns a Three.js-style hierarchy with several sibling part
// Groups.  Every part Group owns primitive Mesh leaves; the assembly Group is
// only a container.  A producer must not collapse the sibling part Groups into
// a coarser material or top-level grouping.

function group(name, position, children) {
  return { name, type: "Group", position, rotation: [0, 0, 0],
           scale: [1, 1, 1], children };
}

function mesh(name, geometryType, parameters, position, rotation = [0, 0, 0]) {
  return { name, type: "Mesh", position, rotation, scale: [1, 1, 1],
           children: [], geometry: { type: geometryType, parameters } };
}

function rail(side, x) {
  return group(`${side}_rail`, [x, 0, 0], [
    mesh(`${side}_beam`, "BoxGeometry",
         { width: 0.8, height: 0.1, depth: 0.2 }, [0, 0, 0]),
    mesh(`${side}_mount`, "BoxGeometry",
         { width: 0.1, height: 0.2, depth: 0.2 }, [0.3, 0.1, 0]),
  ]);
}

function axle(side, z) {
  return group(`${side}_axle`, [0, 0, z], [
    mesh(`${side}_shaft`, "CylinderGeometry",
         { radiusTop: 0.04, radiusBottom: 0.04, height: 0.7,
           radialSegments: 16 }, [0, 0, 0], [0, 0, Math.PI / 2]),
    mesh(`${side}_hub`, "CylinderGeometry",
         { radiusTop: 0.12, radiusBottom: 0.12, height: 0.08,
           radialSegments: 24 }, [0, 0, 0], [0, 0, Math.PI / 2]),
  ]);
}

export function createScene() {
  return group("multipart_fixture", [0.02, -0.01, 0.03], [
    group("fixture_assembly", [0, 0.02, 0], [
      rail("left", -0.4),
      rail("right", 0.4),
      axle("front", 0.4),
      axle("rear", -0.4),
    ]),
  ]);
}

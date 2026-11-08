// Rejection fixture: the module never exports createScene().
export function buildScene() {
  return { name: "root", children: [] };
}

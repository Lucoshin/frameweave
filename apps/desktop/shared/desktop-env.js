export function desktopEnvironment(environment) {
  const result = { ...environment }
  delete result.ELECTRON_RUN_AS_NODE
  return result
}

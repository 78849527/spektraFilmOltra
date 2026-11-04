// Installs the dev mock bridge as window.spektra when running in a plain
// browser (no Electron preload). Imported dynamically from main.tsx only
// under import.meta.env.DEV, so it never ships in production builds.
import * as engine from './engine'

export function installMockBridge(): void {
  window.spektra = {
    request: async (method, endpoint, body) =>
      engine.handle(method, endpoint, body as Record<string, unknown> | undefined),
    logError: async () => {},
    mediaUrl: engine.mediaUrl,
    pickFolder: engine.pickFolder,
    pickImages: engine.pickImages,
    pickLut: engine.pickLut,
    pickJson: engine.pickJson,
    pickSavePath: engine.pickSavePath,
    reveal: engine.reveal,
  }
  console.info('[mock] SpektraOltra dev mock bridge installed (browser preview)')
}
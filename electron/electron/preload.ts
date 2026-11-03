import { contextBridge, ipcRenderer } from 'electron'

type JsonValue = Record<string, unknown> | unknown[] | null

const api = {
  request: (method: 'GET' | 'POST', endpoint: string, body?: JsonValue) =>
    ipcRenderer.invoke('api:request', { method, endpoint, body }) as Promise<unknown>,

  mediaUrl: (filePath: string) =>
    `spektra-media://local/${encodeURIComponent(filePath)}`,

  pickFolder: () => ipcRenderer.invoke('dialog:folder') as Promise<string | null>,
  pickImages: () => ipcRenderer.invoke('dialog:images') as Promise<string[]>,
  pickLut: () => ipcRenderer.invoke('dialog:lut') as Promise<string | null>,
  pickJson: () => ipcRenderer.invoke('dialog:json') as Promise<string | null>,
  pickSavePath: (defaultName: string, extension: string) =>
    ipcRenderer.invoke('dialog:save', { defaultName, extension }) as Promise<string | null>,
  reveal: (filePath: string) => ipcRenderer.invoke('shell:reveal', filePath) as Promise<void>,
  logError: (message: string) => ipcRenderer.invoke('app:log-error', message) as Promise<void>,
}

contextBridge.exposeInMainWorld('spektra', api)

export type SpektraApi = typeof api

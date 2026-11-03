import {
  app,
  BrowserWindow,
  Menu,
  dialog,
  ipcMain,
  protocol,
  shell,
  type MenuItemConstructorOptions,
} from 'electron'
import { createReadStream, existsSync } from 'node:fs'
import path from 'node:path'
import { Readable } from 'node:stream'

import { startSidecar, type SidecarHandle } from './sidecar'

protocol.registerSchemesAsPrivileged([
  {
    scheme: 'spektra-media',
    privileges: { standard: true, secure: true, supportFetchAPI: true, stream: true, bypassCSP: true },
  },
])

let sidecar: SidecarHandle | null = null
let mainWindow: BrowserWindow | null = null

const RAW_EXTENSIONS = [
  'cr2', 'cr3', 'nef', 'arw', 'dng', 'raf', 'orf', 'rw2', 'pef', 'srw',
  '3fr', 'iiq', 'x3f', 'erf', 'mef', 'mos', 'mrw', 'nrw', 'rwl', 'srf', 'sr2',
]
const IMAGE_EXTENSIONS = ['tif', 'tiff', 'png', 'jpg', 'jpeg', 'bmp', 'webp', 'exr', 'hdr', ...RAW_EXTENSIONS]

function mediaRoot(): string {
  return path.join(app.getPath('appData'), 'Spektrafilm')
}

function isAllowedMedia(filePath: string): boolean {
  const root = path.resolve(mediaRoot())
  const resolved = path.resolve(filePath)
  return resolved === root || resolved.startsWith(root + path.sep)
}

function mimeFor(filePath: string): string {
  const suffix = path.extname(filePath).toLowerCase()
  if (suffix === '.png') return 'image/png'
  if (suffix === '.jpg' || suffix === '.jpeg') return 'image/jpeg'
  if (suffix === '.webp') return 'image/webp'
  if (suffix === '.tif' || suffix === '.tiff') return 'image/tiff'
  return 'application/octet-stream'
}

function registerMediaProtocol(): void {
  protocol.handle('spektra-media', async (request) => {
    const url = new URL(request.url)
    const raw = decodeURIComponent(url.pathname.replace(/^\//, ''))
    if (!raw || !isAllowedMedia(raw) || !existsSync(raw)) {
      return new Response('not found', { status: 404 })
    }
    const stream = Readable.toWeb(createReadStream(raw)) as ReadableStream
    return new Response(stream, {
      headers: {
        'Content-Type': mimeFor(raw),
        'Access-Control-Allow-Origin': '*',
        'Cache-Control': 'no-store',
      },
    })
  })
}

function buildMenu(): void {
  const template: MenuItemConstructorOptions[] = [
    { role: 'appMenu' },
    {
      label: '编辑',
      submenu: [
        { role: 'undo', label: '撤销' },
        { role: 'redo', label: '重做' },
        { type: 'separator' },
        { role: 'cut', label: '剪切' },
        { role: 'copy', label: '复制' },
        { role: 'paste', label: '粘贴' },
        { role: 'selectAll', label: '全选' },
      ],
    },
    {
      label: '视图',
      submenu: [
        { role: 'reload', label: '重新载入' },
        { role: 'toggleDevTools', label: '开发者工具' },
        { type: 'separator' },
        { role: 'togglefullscreen', label: '全屏' },
      ],
    },
    { role: 'windowMenu' },
  ]
  Menu.setApplicationMenu(Menu.buildFromTemplate(template))
}

async function loadRenderer(window: BrowserWindow): Promise<void> {
  const devUrl = process.env.SPEKTRA_DEV_URL
  if (devUrl) {
    for (let attempt = 0; attempt < 60; attempt += 1) {
      try {
        await window.loadURL(devUrl)
        return
      } catch {
        await new Promise((resolve) => setTimeout(resolve, 250))
      }
    }
  }
  await window.loadFile(path.join(__dirname, '..', 'dist', 'index.html'))
}

async function createWindow(): Promise<void> {
  mainWindow = new BrowserWindow({
    width: 1460,
    height: 940,
    minWidth: 1180,
    minHeight: 760,
    show: false,
    backgroundColor: '#141311',
    titleBarStyle: 'hiddenInset',
    trafficLightPosition: { x: 14, y: 9 },
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  })

  mainWindow.once('ready-to-show', () => mainWindow?.show())
  mainWindow.on('closed', () => {
    mainWindow = null
  })
  await loadRenderer(mainWindow)
}

function registerIpc(): void {
  ipcMain.handle('api:request', async (_event, payload: { method: 'GET' | 'POST'; endpoint: string; body?: unknown }) => {
    if (!sidecar) throw new Error('引擎未启动')
    const response = await fetch(`http://127.0.0.1:${sidecar.port}${payload.endpoint}`, {
      method: payload.method,
      headers: {
        'Content-Type': 'application/json',
        'X-Spektra-Token': sidecar.token,
      },
      body: payload.body === undefined ? undefined : JSON.stringify(payload.body),
    })
    const text = await response.text()
    let parsed: { error?: string } = {}
    try {
      parsed = text ? JSON.parse(text) : {}
    } catch {
      throw new Error(`引擎返回了非 JSON 响应：${text.slice(0, 200)}`)
    }
    if (!response.ok) {
      throw new Error(parsed.error || `请求失败：${response.status}`)
    }
    return parsed
  })

  ipcMain.handle('dialog:folder', async () => {
    if (!mainWindow) return null
    const result = await dialog.showOpenDialog(mainWindow, {
      title: '导入文件夹',
      properties: ['openDirectory', 'createDirectory'],
      buttonLabel: '导入',
    })
    return result.canceled ? null : result.filePaths[0] ?? null
  })

  ipcMain.handle('dialog:images', async () => {
    if (!mainWindow) return []
    const result = await dialog.showOpenDialog(mainWindow, {
      title: '导入照片',
      properties: ['openFile', 'multiSelections'],
      buttonLabel: '导入',
      filters: [{ name: '照片', extensions: IMAGE_EXTENSIONS }],
    })
    return result.canceled ? [] : result.filePaths
  })

  ipcMain.handle('dialog:lut', async () => {
    if (!mainWindow) return null
    const result = await dialog.showOpenDialog(mainWindow, {
      title: '导入 LUT',
      properties: ['openFile'],
      buttonLabel: '导入',
      filters: [{ name: 'Cube LUT', extensions: ['cube'] }],
    })
    return result.canceled ? null : result.filePaths[0] ?? null
  })

  ipcMain.handle('dialog:json', async () => {
    if (!mainWindow) return null
    const result = await dialog.showOpenDialog(mainWindow, {
      title: '导入调色预设',
      properties: ['openFile'],
      buttonLabel: '导入',
      filters: [{ name: '预设', extensions: ['json'] }],
    })
    return result.canceled ? null : result.filePaths[0] ?? null
  })

  ipcMain.handle('dialog:save', async (_event, payload: { defaultName: string; extension: string }) => {
    if (!mainWindow) return null
    const result = await dialog.showSaveDialog(mainWindow, {
      title: '导出',
      defaultPath: payload.defaultName,
      filters: [{ name: payload.extension.toUpperCase(), extensions: [payload.extension] }],
    })
    return result.canceled ? null : result.filePath ?? null
  })

  ipcMain.handle('shell:reveal', async (_event, filePath: string) => {
    shell.showItemInFolder(filePath)
  })
}

app.whenReady().then(async () => {
  try {
    sidecar = await startSidecar()
  } catch (error) {
    dialog.showErrorBox('引擎启动失败', error instanceof Error ? error.message : String(error))
    app.quit()
    return
  }
  registerMediaProtocol()
  registerIpc()
  buildMenu()
  await createWindow()

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      void createWindow()
    }
  })
})

app.on('before-quit', () => {
  sidecar?.stop()
  sidecar = null
})

app.on('window-all-closed', () => {
  app.quit()
})

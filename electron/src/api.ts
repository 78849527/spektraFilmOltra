import type { JobStatus } from './types'

interface RequestPayload {
  method: 'GET' | 'POST'
  endpoint: string
  body?: unknown
}

interface SpektraBridge {
  request: (method: 'GET' | 'POST', endpoint: string, body?: unknown) => Promise<unknown>
  mediaUrl: (filePath: string) => string
  pickFolder: () => Promise<string | null>
  pickImages: () => Promise<string[]>
  pickLut: () => Promise<string | null>
  pickJson: () => Promise<string | null>
  pickSavePath: (defaultName: string, extension: string) => Promise<string | null>
  reveal: (filePath: string) => Promise<void>
}

declare global {
  interface Window {
    spektra: SpektraBridge
  }
}

export async function request<T>(method: 'GET' | 'POST', endpoint: string, body?: unknown): Promise<T> {
  const payload: RequestPayload = { method, endpoint, body }
  return (await window.spektra.request(payload.method, payload.endpoint, payload.body)) as T
}

export function mediaUrl(filePath: string): string {
  if (!filePath) return ''
  return window.spektra.mediaUrl(filePath)
    .replaceAll('%2F', '/')
}

export function pickFolder(): Promise<string | null> {
  return window.spektra.pickFolder()
}

export function pickImages(): Promise<string[]> {
  return window.spektra.pickImages()
}

export function pickSavePath(defaultName: string, extension: string): Promise<string | null> {
  return window.spektra.pickSavePath(defaultName, extension)
}

export function pickLut(): Promise<string | null> {
  return window.spektra.pickLut()
}

export function reveal(filePath: string): Promise<void> {
  return window.spektra.reveal(filePath)
}

export async function waitForJob(
  jobId: string,
  onProgress?: (status: JobStatus) => void,
  timeoutMs = 600_000,
): Promise<JobStatus> {
  const deadline = Date.now() + timeoutMs
  while (Date.now() < deadline) {
    const status = await request<JobStatus>('GET', `/v1/jobs/${jobId}`)
    onProgress?.(status)
    if (status.state === 'done') return status
    if (status.state === 'failed') throw new Error(status.error || '渲染失败')
    if (status.state === 'cancelled') throw new Error('任务已取消')
    await new Promise((resolve) => setTimeout(resolve, 280))
  }
  throw new Error('渲染超时')
}

export function errorMessage(error: unknown): string {
  if (error instanceof Error) {
    return error.message.replace(/^Error invoking remote method '[^']+': /, '')
  }
  return String(error)
}

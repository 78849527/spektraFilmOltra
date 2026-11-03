import { spawn } from 'node:child_process'
import { existsSync } from 'node:fs'
import path from 'node:path'

export interface SidecarHandle {
  port: number
  token: string
  stop: () => void
}

interface ReadyLine {
  event: string
  port: number
  token: string
}

function resolvePython(): string {
  if (process.env.SPEKTRA_PYTHON) {
    return process.env.SPEKTRA_PYTHON
  }
  const repoRoot = path.resolve(__dirname, '..', '..')
  const candidate = path.join(repoRoot, '.venv', 'bin', 'python')
  if (existsSync(candidate)) {
    return candidate
  }
  return 'python3'
}

function resolveRepoRoot(): string {
  return process.env.SPEKTRA_SERVICE_ROOT || path.resolve(__dirname, '..', '..')
}

export async function startSidecar(): Promise<SidecarHandle> {
  const repoRoot = resolveRepoRoot()
  const python = resolvePython()
  const child = spawn(
    python,
    ['-m', 'spektrafilm_service', '--port', '0'],
    {
      cwd: repoRoot,
      env: {
        ...process.env,
        PYTHONPATH: path.join(repoRoot, 'src'),
        PYTHONUNBUFFERED: '1',
      },
      stdio: ['ignore', 'pipe', 'pipe'],
    },
  )

  let buffer = ''
  let stderrTail = ''
  child.stderr.on('data', (chunk: Buffer) => {
    stderrTail = (stderrTail + chunk.toString('utf-8')).slice(-2000)
  })

  const ready = await new Promise<ReadyLine>((resolve, reject) => {
    const timer = setTimeout(() => {
      reject(new Error(`引擎启动超时\n${stderrTail}`))
    }, 60_000)

    child.once('exit', (code) => {
      clearTimeout(timer)
      reject(new Error(`引擎进程退出（${code}）\n${stderrTail}`))
    })

    child.stdout.on('data', (chunk: Buffer) => {
      buffer += chunk.toString('utf-8')
      const lines = buffer.split('\n')
      buffer = lines.pop() || ''
      for (const line of lines) {
        const text = line.trim()
        if (!text.startsWith('{')) continue
        try {
          const payload = JSON.parse(text) as ReadyLine
          if (payload.event === 'ready' && payload.port) {
            clearTimeout(timer)
            resolve(payload)
            return
          }
        } catch {
          // 非协议行忽略
        }
      }
    })

    child.once('error', (error) => {
      clearTimeout(timer)
      reject(error)
    })
  })

  let stopped = false
  const stop = () => {
    if (stopped) return
    stopped = true
    child.kill('SIGTERM')
    setTimeout(() => {
      if (!child.killed) child.kill('SIGKILL')
    }, 2_000).unref()
  }

  return { port: ready.port, token: ready.token, stop }
}

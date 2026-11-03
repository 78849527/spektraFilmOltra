import { defineConfig, type Plugin, type ViteDevServer } from 'vite'
import react from '@vitejs/plugin-react'

// Dev-only mock image service. The browser preview has no real engine, so
// every media path the mock bridge hands out is rendered here as a
// deterministic fake "photo" (an SVG scene seeded by the path string).
function hashSeed(value: string): number {
  let h = 2166136261
  for (let index = 0; index < value.length; index += 1) {
    h ^= value.charCodeAt(index)
    h = Math.imul(h, 16777619)
  }
  return h >>> 0
}

function sceneSvg(seedKey: string): string {
  const seed = hashSeed(seedKey)
  const style =
    seedKey.includes('@original') || seedKey.includes('@display')
      ? 'neutral'
      : seedKey.includes('@grade')
        ? 'grade'
        : 'developed'
  const portrait = seedKey.includes('@portrait')
  const hue = seed % 360
  const sunX = portrait ? 520 + (seed % 560) : 300 + (seed % 1000)
  const sunY = 180 + ((seed >> 3) % 220)
  const ridge = 620 + ((seed >> 5) % 160)
  const ridge2 = 760 + ((seed >> 7) % 120)
  const grainSeed = seed % 100

  const sat = style === 'neutral' ? 18 : style === 'grade' ? 52 : 40
  const skyTop = style === 'grade' ? `hsl(${(hue + 190) % 360} ${sat + 10}% 30%)` : `hsl(${hue} ${sat}% 58%)`
  const skyMid = style === 'grade' ? `hsl(${(hue + 200) % 360} ${sat}% 52%)` : `hsl(${(hue + 18) % 360} ${sat - 8}% 74%)`
  const skyLow = style === 'neutral' ? `hsl(${hue} 8% 80%)` : `hsl(${(hue + 30) % 360} ${sat - 16}% 84%)`
  const hillFar = style === 'grade' ? `hsl(${(hue + 24) % 360} 46% 38%)` : `hsl(${(hue + 8) % 360} ${sat - 14}% 42%)`
  const hillNear = style === 'grade' ? `hsl(${(hue + 18) % 360} 38% 22%)` : `hsl(${(hue + 4) % 360} ${sat - 20}% 28%)`
  const ground = `hsl(${(hue + 2) % 360} ${Math.max(sat - 24, 6)}% 16%)`
  const sunTint = style === 'neutral' ? 'hsl(40 20% 92%)' : `hsl(${(hue + 40) % 360} 82% 86%)`
  const halation =
    style === 'developed' || style === 'grade'
      ? `<circle cx="${sunX}" cy="${sunY}" r="150" fill="${sunTint}" opacity="0.28" filter="url(#soft)"/>`
      : ''
  const wash =
    style === 'developed'
      ? '<rect width="1600" height="1067" fill="hsl(38 60% 55%)" opacity="0.07"/>'
      : style === 'grade'
        ? '<rect width="1600" height="1067" fill="hsl(200 70% 40%)" opacity="0.06"/>'
        : ''

  const frame = portrait
    ? 'width="600" height="1067" viewBox="500 0 600 1067" preserveAspectRatio="xMidYMid slice"'
    : 'width="1600" height="1067" viewBox="0 0 1600 1067"'

  return `<svg xmlns="http://www.w3.org/2000/svg" ${frame}>
  <defs>
    <linearGradient id="sky" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="${skyTop}"/>
      <stop offset="0.55" stop-color="${skyMid}"/>
      <stop offset="1" stop-color="${skyLow}"/>
    </linearGradient>
    <radialGradient id="vig" cx="0.5" cy="0.45" r="0.78">
      <stop offset="0.6" stop-color="rgba(0,0,0,0)"/>
      <stop offset="1" stop-color="rgba(18,12,8,${style === 'neutral' ? 0.25 : 0.5})"/>
    </radialGradient>
    <filter id="soft" x="-60%" y="-60%" width="220%" height="220%">
      <feGaussianBlur stdDeviation="42"/>
    </filter>
    <filter id="grain" x="0" y="0" width="100%" height="100%">
      <feTurbulence type="fractalNoise" baseFrequency="0.85" numOctaves="2" seed="${grainSeed}" stitchTiles="stitch" result="noise"/>
      <feColorMatrix in="noise" type="matrix" values="0 0 0 0 0  0 0 0 0 0  0 0 0 0 0  0.07 0.07 0.07 0 0"/>
    </filter>
  </defs>
  <rect width="1600" height="1067" fill="url(#sky)"/>
  <circle cx="${sunX}" cy="${sunY}" r="46" fill="${sunTint}" opacity="0.95"/>
  ${halation}
  <path d="M0 ${ridge} Q 320 ${ridge - 90} 640 ${ridge} T 1280 ${ridge - 40} L 1600 ${ridge - 70} V1067 H0 Z" fill="${hillFar}"/>
  <path d="M0 ${ridge2} Q 400 ${ridge2 - 70} 900 ${ridge2 + 20} T 1600 ${ridge2 - 30} V1067 H0 Z" fill="${hillNear}"/>
  <rect y="980" width="1600" height="87" fill="${ground}"/>
  ${wash}
  <rect width="1600" height="1067" fill="url(#vig)"/>
  <rect width="1600" height="1067" filter="url(#grain)"/>
</svg>`
}

function mockMedia(): Plugin {
  return {
    name: 'spektra-mock-media',
    apply: 'serve',
    configureServer(server: ViteDevServer) {
      server.middlewares.use('/mock-media', (req, res) => {
        const raw = decodeURIComponent((req.url ?? '/').split('?')[0].replace(/^\//, ''))
        res.setHeader('Content-Type', 'image/svg+xml; charset=utf-8')
        res.setHeader('Access-Control-Allow-Origin', '*')
        res.setHeader('Cache-Control', 'no-store')
        res.end(sceneSvg(raw))
      })
    },
  }
}

export default defineConfig({
  base: './',
  plugins: [react(), mockMedia()],
  server: { port: 5173, strictPort: true },
  build: { outDir: 'dist', emptyOutDir: true },
})
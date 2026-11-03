import { readdirSync, readFileSync, statSync } from 'node:fs'
import { gzipSync } from 'node:zlib'
import { join } from 'node:path'

const dist = new URL('../frontend/dist/assets/', import.meta.url)
let gzipTotal = 0
for (const name of readdirSync(dist)) {
  if (!name.endsWith('.js')) continue
  const buf = readFileSync(join(dist.pathname, name))
  gzipTotal += gzipSync(buf).length
}
const limit = 350 * 1024
console.log(`JS gzip total: ${gzipTotal} bytes (budget ${limit})`)
if (gzipTotal > limit) {
  console.error('Frontend bundle is over the performance budget.')
  process.exit(1)
}

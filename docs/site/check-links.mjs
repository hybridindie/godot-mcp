// Post-build guard: every sidebar/nav link in config.mts must resolve to a file
// in dist/ (or an external URL). VitePress dead-links only cover markdown body
// links — config links (nav/sidebar) silently ship 404s otherwise.
import { readFileSync, existsSync } from 'node:fs'
import { join, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'

const SITE = dirname(fileURLToPath(import.meta.url))
const DIST = join(SITE, 'dist')
const BASE = '/godot-mcp/'

const config = readFileSync(join(SITE, '.vitepress/config.mts'), 'utf8')
const links = [...config.matchAll(/link: '([^']+)'/g)].map((m) => m[1])

const dead = []
for (const link of links) {
  if (/^https?:/.test(link)) continue
  let path
  if (link === '/') path = '/index.html'
  else if (link.endsWith('/')) path = link + 'index.html'
  else path = link + '.html'
  const rel = path.replace(BASE, '')
  if (!existsSync(join(DIST, rel))) {
    dead.push(`${link} -> dist/${rel} missing`)
  }
}
if (dead.length) {
  console.error('DEAD NAV/SIDEBAR LINKS:\n' + dead.join('\n'))
  process.exit(1)
}
console.log(`checked ${links.length} nav/sidebar links: all resolve`)

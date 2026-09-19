// Generate llms.txt + llms-full.txt into the site output (llmstxt.org convention).
//
// VitePress renders HTML, so this post-build script reads the *source* markdown
// from the site root (the same pages VitePress compiled) and:
//   - llms.txt      — the page index with stable raw-HTML URLs (agents can
//                     fetch any page; the HTML contains the rendered content)
//   - llms-full.txt — every page's raw markdown concatenated, so one fetch
//                     returns the whole site
// Section order mirrors the sidebar in .vitepress/config.mts.
import { readFileSync, writeFileSync, existsSync } from 'node:fs'
import { join, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'

const SITE_DIR = dirname(fileURLToPath(import.meta.url))
const DIST = join(SITE_DIR, 'dist')
const REPO_URL = 'https://github.com/hybridindie/godot-mcp/blob/main/docs/site/'
const SITE_URL = 'https://hybridindie.github.io/godot-mcp/'

const TITLE = 'godot-mcp'
const DESC =
  'Bridge an AI agent and a live Godot editor over MCP — inspect, mutate, run, verify. ' +
  'Architecture, reasoning, and the full tool surface.'

// section -> ordered source paths (relative to docs/site/)
const SECTIONS = {
  Home: ['index.md', 'what-why.md', 'concepts.md'],
  Architecture: [
    'architecture/index.md',
    'architecture/bridge.md',
    'architecture/envelope.md',
    'architecture/gating.md',
    'architecture/safety.md',
    'architecture/persistence.md',
    'architecture/readiness.md',
  ],
  'Getting started': [
    'getting-started.md',
    'getting-started-install.md',
    'getting-started-addon.md',
    'getting-started-clients.md',
    'getting-started-first-session.md',
    'getting-started-openwebui.md',
  ],
  Reference: [
    'reference.md',
    'reference-toolsets.md',
    'reference-safety-classes.md',
    'reference-value-shapes.md',
    'reference-errors.md',
    'reference-env-vars.md',
  ],
  Guides: [
    'guides.md',
    'guides-build-scene.md',
    'guides-playtest-debug.md',
    'guides-verify.md',
  ],
  Changelog: ['changelog.md'],
}

// Source path -> the site URL VitePress actually serves. VitePress's default
// (cleanUrls not enabled) renders foo.md -> foo.html and subdir/index.md ->
// subdir/ — trailing-slash URLs 404, so the index must use the .html form.
function htmlPath(srcRel) {
  const noExt = srcRel.replace(/\.md$/, '')
  if (noExt === 'index') return SITE_URL
  if (noExt.endsWith('/index')) return SITE_URL + noExt.slice(0, -'/index'.length) + '/'
  return SITE_URL + noExt + '.html'
}

const indexLines = [`# ${TITLE}`, '', `> ${DESC}`, '']
const full = [
  `# ${TITLE}`,
  '',
  `> ${DESC}`,
  '',
  'Markdown sources: ' + REPO_URL.replace('/main//', '/main/'),
  '',
]

for (const [section, pages] of Object.entries(SECTIONS)) {
  indexLines.push(`## ${section}`)
  full.push(`## ${section}`, '')
  for (const src of pages) {
    const abs = join(SITE_DIR, src)
    if (!existsSync(abs)) continue
    const raw = readFileSync(abs, 'utf8')
    // strip frontmatter for the full doc; the title line follows
    const body = raw.replace(/^---\n.*?\n---\n/s, '')
    const titleMatch = body.match(/^# (.+)$/m)
    const pageTitle = titleMatch ? titleMatch[1] : src.replace(/\.md$/, '')
    // URL as VitePress renders it: subdir index.md -> dir/ ; flat foo.md -> foo/
    const pageUrl = htmlPath(src)
    indexLines.push(`- [${pageTitle}](${htmlPath(src)})`)
    full.push(body.trim(), '')
  }
  indexLines.push('')
  full.push('')
}

writeFileSync(join(DIST, 'llms.txt'), indexLines.join('\n') + '\n')
writeFileSync(join(DIST, 'llms-full.txt'), full.join('\n') + '\n')
console.log('generated llms.txt + llms-full.txt')
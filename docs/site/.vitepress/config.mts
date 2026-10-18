import { defineConfig } from 'vitepress'
import { withMermaid } from 'vitepress-plugin-mermaid'

const BASE = '/godot-mcp/'

export default withMermaid(defineConfig({
  lang: 'en-US',
  title: 'Godot Editor MCP',
  description:
    'Godot Editor MCP bridges an AI agent and a live Godot editor over MCP — inspect, mutate, run, verify. 194 tools across 29 categories (28 toggleable toolsets plus always-on core); the server owns safety, the addon owns Godot.',
  base: BASE,
  outDir: 'dist',
  ignoreDeadLinks: false,
  vite: {
    optimizeDeps: {
      include: ['debug'],
    },
  },
  head: [
    ['link', { rel: 'icon', type: 'image/svg+xml', href: BASE + 'logo.svg' }],
    // llmstxt.org v2 discovery: the index describing this site, and the
    // markdown variant of the rendered page (injected per-page via
    // transformHead below — page.html.md is the spec's page.html.md form).
  ],
  transformHead: ({ pageData }) => {
    const base = BASE.replace(/\/$/, '')
    const describedby = base + '/llms.txt'
    // Per-page markdown variant URL (spec v2 page.html.md form), matching the
    // file llms-gen.mjs writes: 'architecture/bridge.md' ->
    // 'architecture/bridge.html.md'; 'index.md' -> 'index.html.md'.
    const rel = (pageData.relativePath ?? 'index.md').replace(/\.md$/, '')
    const variant = base + '/' + rel + '.html.md'
    return [
      ['link', { rel: 'describedby', type: 'text/markdown', href: describedby }],
      ['link', { rel: 'alternate', type: 'text/markdown', href: variant }],
    ]
  },
  mermaid: {
    // plugin auto-switches to theme 'dark' when VitePress dark mode is active
    securityLevel: 'loose',
    startOnLoad: false,
  },
  mermaidPlugin: {
    class: 'mermaid-blocks',
  },
  themeConfig: {
    siteTitle: 'Godot Editor MCP',
    nav: [
      { text: 'Start here', link: '/getting-started' },
      { text: 'For creators', link: '/for-creators' },
      { text: 'For developers', link: '/for-developers' },
      { text: 'Reference', link: '/reference' },
      { text: 'Under the hood', link: '/architecture/' },
      {
        text: 'LLM',
        items: [
          { text: 'llms.txt (index)', link: BASE + 'llms.txt' },
          { text: 'llms-full.txt (one doc)', link: BASE + 'llms-full.txt' },
        ],
      },
      {
        text: 'GitHub',
        link: 'https://github.com/hybridindie/godot-mcp'
      }
    ],
    sidebar: [
      {
        text: 'Start here',
        items: [
          { text: 'Overview', link: '/getting-started' },
          { text: 'For creators', link: '/for-creators' },
          { text: 'For developers', link: '/for-developers' }
        ]
      },
      {
        text: 'For creators',
        items: [
          { text: 'Set up with your AI agent', link: '/getting-started-with-an-agent' },
          { text: 'Your first session', link: '/getting-started-first-session' },
          { text: 'Guides overview', link: '/guides' },
          { text: 'Build a scene', link: '/guides-build-scene' },
          { text: 'Play-test & debug', link: '/guides-playtest-debug' },
          { text: 'Verify your work', link: '/guides-verify' },
          { text: 'Ship: export, tests & CI', link: '/guides-ship' },
          { text: 'Examples', link: '/guides-examples' }
        ]
      },
      {
        text: 'For developers',
        items: [
          { text: 'Install the MCP server', link: '/getting-started-install' },
          { text: 'Install the Godot addon', link: '/getting-started-addon' },
          { text: 'Configure your MCP client', link: '/getting-started-clients' },
          { text: 'Remote & multi-client', link: '/getting-started-openwebui' },
          { text: 'Concepts', link: '/concepts' },
          { text: 'Reference overview', link: '/reference' },
          { text: 'Toolsets & tools', link: '/reference-toolsets' },
          { text: 'Safety classes', link: '/reference-safety-classes' },
          { text: 'Value shapes', link: '/reference-value-shapes' },
          { text: 'Errors & recovery', link: '/reference-errors' },
          { text: 'Prompts & resources', link: '/reference-prompts' },
          { text: 'Skills', link: '/reference-skills' },
          { text: 'Consumer integration', link: '/reference-consumers' },
          { text: 'Environment variables', link: '/reference-env-vars' },
          { text: 'Under the hood', link: '/architecture/' },
          { text: 'The Godot addon', link: '/architecture/addon' },
          { text: 'Bridge & transport', link: '/architecture/bridge' },
          { text: 'The JSON envelope', link: '/architecture/envelope' },
          { text: 'Toolset gating', link: '/architecture/gating' },
          { text: 'The safety model', link: '/architecture/safety' },
          { text: 'Persistence truth', link: '/architecture/persistence' },
          { text: 'The readiness envelope', link: '/architecture/readiness' }
        ]
      },
      {
        text: 'Project',
        items: [
          { text: 'Contributing', link: 'https://github.com/hybridindie/godot-mcp/blob/main/CONTRIBUTING.md' },
          { text: 'Changelog', link: '/changelog' },
          { text: 'GitHub', link: 'https://github.com/hybridindie/godot-mcp' }
        ]
      }
    ],
    search: {
      provider: 'local',
      options: {
        translations: {
          button: { buttonText: 'Search docs' }
        }
      }
    },
    socialLinks: [
      { icon: 'github', link: 'https://github.com/hybridindie/godot-mcp' }
    ],
    editLink: {
      pattern:
        'https://github.com/hybridindie/godot-mcp/edit/main/docs/site/:path',
      text: 'Edit this page on GitHub'
    },
    footer: {
      message: '194 tools · 29 categories · contract version 1',
      copyright: 'MIT Licensed. Copyright © 2026 hybridindie'
    }
  },
}))
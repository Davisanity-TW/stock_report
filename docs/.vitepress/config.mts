import { defineConfig } from 'vitepress'
import { readdirSync, existsSync } from 'node:fs'
import { join } from 'node:path'

function listDirNames(dirFromDocsRoot: string) {
  const abs = join(process.cwd(), 'docs', dirFromDocsRoot)
  if (!existsSync(abs)) return []
  return readdirSync(abs, { withFileTypes: true })
    .filter((d) => d.isDirectory())
    .map((d) => d.name)
}

function listMdBasenames(dirFromDocsRoot: string) {
  const abs = join(process.cwd(), 'docs', dirFromDocsRoot)
  if (!existsSync(abs)) return []
  return readdirSync(abs)
    .filter((f) => f.endsWith('.md'))
    .map((f) => f.replace(/\.md$/, ''))
}

function makeItems(prefix: string, dirFromDocsRoot: string, limit = 20) {
  // newest first (filenames like 2026-W05 / 2026-02-01)
  const names = listMdBasenames(dirFromDocsRoot).sort().reverse().slice(0, limit)
  return names.map((name) => ({ text: name, link: `/${prefix}/${name}` }))
}

function makeMoltbookSidebarGroups(limitMonths = 24, limitItemsPerMonth = 31) {
  const root = 'reports/moltbook/reports'
  const months = listDirNames(root).sort().reverse().slice(0, limitMonths)

  return months.map((m) => {
    const items = makeItems(`reports/moltbook/reports/${m}`, `${root}/${m}`, limitItemsPerMonth)
    return {
      text: m,
      collapsed: true,
      items
    }
  })
}

export default defineConfig({
  lang: 'zh-Hant',
  title: 'Stock Report（研究日誌）',
  description: '台股 / 美股 / YT / Moltbook 的研究摘要與週報彙整',
  base: '/stock_report/',
  themeConfig: {
    nav: [
      { text: '首頁', link: '/' },
      { text: '台股（TW）', link: '/reports/tw/' },
      { text: '美股（US）', link: '/reports/us/' },
      { text: 'YT-澔哥', link: '/reports/youtube/' },
      { text: 'Moltbook', link: '/reports/moltbook/reports/' }
    ],
    sidebar: [
      {
        text: '導覽',
        items: [{ text: '首頁', link: '/' }]
      },
      {
        text: '台股（TW）',
        items: makeItems('reports/tw', 'reports/tw', 30)
      },
      {
        text: '美股（US）',
        items: makeItems('reports/us', 'reports/us', 30)
      },
      {
        text: 'YT-澔哥',
        items: makeItems('reports/youtube', 'reports/youtube', 30)
      },
      {
        text: 'Moltbook',
        items: [
          { text: 'Index', link: '/reports/moltbook/' },
          { text: 'Reports', link: '/reports/moltbook/reports/' },
          ...makeMoltbookSidebarGroups(24, 62)
        ]
      }
    ]
  }
})

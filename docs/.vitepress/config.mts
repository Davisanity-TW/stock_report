import { defineConfig } from 'vitepress'
import { readdirSync, existsSync } from 'node:fs'
import { join } from 'node:path'

function listMdBasenames(dirFromDocsRoot: string) {
  const abs = join(process.cwd(), 'docs', dirFromDocsRoot)
  if (!existsSync(abs)) return []
  return readdirSync(abs)
    .filter((f) => f.endsWith('.md'))
    .map((f) => f.replace(/\.md$/, ''))
    .filter((name) => name !== 'index')
}

function makeItems(prefix: string, dirFromDocsRoot: string, limit = 30) {
  const names = listMdBasenames(dirFromDocsRoot).sort().reverse().slice(0, limit)
  return names.map((name) => ({ text: name, link: `/${prefix}/${name}` }))
}

export default defineConfig({
  lang: 'zh-Hant',
  title: 'Stock Report（研究日誌）',
  description: '台股 / 美股 / YT 的研究摘要與週報彙整',
  base: '/stock_report/',
  themeConfig: {
    nav: [
      { text: '首頁', link: '/' },
      { text: '台股（TW）', link: '/reports/tw/' },
      { text: '美股（US）', link: '/reports/us/' },
      { text: 'YT-澔哥', link: '/reports/youtube/' }
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
      }
    ]
  }
})

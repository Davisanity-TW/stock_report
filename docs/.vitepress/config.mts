import { defineConfig } from 'vitepress'

export default defineConfig({
  lang: 'zh-Hant',
  title: 'Stock Report（研究日誌）',
  description: '台股 / 美股 / YouTube / Moltbook 的研究摘要與週報彙整',
  base: '/stock_report/',
  themeConfig: {
    nav: [
      { text: '首頁', link: '/' },
      { text: '台股（TW）', link: '/reports/tw/2026-W05' },
      { text: '美股（US）', link: '/reports/us/2026-W05' },
      { text: 'YouTube', link: '/reports/youtube/2026-W05' },
      { text: 'Moltbook', link: '/reports/moltbook/2026-02-01' }
    ],
    sidebar: [
      {
        text: '導覽',
        items: [
          { text: '首頁', link: '/' }
        ]
      },
      {
        text: 'Reports',
        items: [
          { text: '台股（TW）', link: '/reports/tw/2026-W05' },
          { text: '美股（US）', link: '/reports/us/2026-W05' },
          { text: 'YouTube', link: '/reports/youtube/2026-W05' },
          { text: 'Moltbook', link: '/reports/moltbook/2026-02-01' }
        ]
      }
    ]
  }
})

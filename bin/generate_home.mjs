import { readdirSync, existsSync, writeFileSync } from 'node:fs'
import { join } from 'node:path'

function latestMdName(dir) {
  if (!existsSync(dir)) return null
  const names = readdirSync(dir)
    .filter((f) => f.endsWith('.md'))
    .map((f) => f.replace(/\.md$/, ''))
    .sort()
    .reverse()
  return names[0] ?? null
}

function latestMoltbook(dir) {
  // dir: docs/reports/moltbook/reports
  if (!existsSync(dir)) return null
  const months = readdirSync(dir, { withFileTypes: true })
    .filter((d) => d.isDirectory())
    .map((d) => d.name)
    .sort()
    .reverse()

  const month = months[0]
  if (!month) return null

  const day = latestMdName(join(dir, month))
  if (!day) return null

  return { month, day }
}

const root = process.cwd()
const docsDir = join(root, 'docs')

const targets = {
  tw: join(docsDir, 'reports', 'tw'),
  us: join(docsDir, 'reports', 'us'),
  youtube: join(docsDir, 'reports', 'youtube'),
  finance_news: join(docsDir, 'reports', 'finance_news'),
  moltbook: join(docsDir, 'reports', 'moltbook', 'reports')
}

const latest = {
  tw: latestMdName(targets.tw),
  us: latestMdName(targets.us),
  youtube: latestMdName(targets.youtube),
  finance_news: latestMdName(targets.finance_news),
  moltbook: latestMoltbook(targets.moltbook)
}

const lines = []
lines.push('# Stock Report（研究日誌）')
lines.push('')
lines.push('最新入口（自動更新）：')
lines.push('')
lines.push(`- 台股（TW）：${latest.tw ? `[./reports/tw/${latest.tw}](./reports/tw/${latest.tw})` : '（尚無資料）'}`)
lines.push(`- 美股（US）：${latest.us ? `[./reports/us/${latest.us}](./reports/us/${latest.us})` : '（尚無資料）'}`)
lines.push(`- YT-澔哥：${latest.youtube ? `[./reports/youtube/${latest.youtube}](./reports/youtube/${latest.youtube})` : '（尚無資料）'}`)
lines.push(`- 財經新聞快報：${latest.finance_news ? `[./reports/finance_news/${latest.finance_news}](./reports/finance_news/${latest.finance_news})` : '（尚無資料）'}`)
lines.push(
  `- Moltbook：${
    latest.moltbook
      ? `[./reports/moltbook/reports/${latest.moltbook.month}/${latest.moltbook.day}](./reports/moltbook/reports/${latest.moltbook.month}/${latest.moltbook.day})`
      : '（尚無資料）'
  }`
)
lines.push('')
lines.push('列表：')
lines.push('')
lines.push('- 台股（TW）列表：`/reports/tw/`')
lines.push('- 美股（US）列表：`/reports/us/`')
lines.push('- YT-澔哥 列表：`/reports/youtube/`')
lines.push('- 財經新聞快報 列表：`/reports/finance_news/`')
lines.push('- Moltbook 列表：`/reports/moltbook/reports/`')
lines.push('')
lines.push('')
lines.push('排程（自動更新）：')
lines.push('')
lines.push('- 財經新聞快報：每日 08:00 / 16:00 / 21:00（Asia/Taipei，近 5 小時｜台灣+國際；台灣最多 8、國際最多 8；主軸 3 點／追蹤 3 點）')
lines.push('')
lines.push('> 這頁由 `bin/generate_home.mjs` 在 build/dev 前自動產生。')
lines.push('')

writeFileSync(join(docsDir, 'index.md'), lines.join('\n'), 'utf8')

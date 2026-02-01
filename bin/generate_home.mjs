import { readdirSync, writeFileSync, existsSync } from 'node:fs'
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

const root = process.cwd()
const docsDir = join(root, 'docs')

const targets = {
  tw: join(docsDir, 'reports', 'tw'),
  us: join(docsDir, 'reports', 'us'),
  youtube: join(docsDir, 'reports', 'youtube')
}

const latest = {
  tw: latestMdName(targets.tw),
  us: latestMdName(targets.us),
  youtube: latestMdName(targets.youtube)
}

const lines = []
lines.push('# Stock Report（研究日誌）')
lines.push('')
lines.push('最新入口（自動更新）：')
lines.push('')
lines.push(`- 台股（TW）：${latest.tw ? `[/reports/tw/${latest.tw}](/reports/tw/${latest.tw})` : '（尚無資料）'}`)
lines.push(`- 美股（US）：${latest.us ? `[/reports/us/${latest.us}](/reports/us/${latest.us})` : '（尚無資料）'}`)
lines.push(`- YouTube：${latest.youtube ? `[/reports/youtube/${latest.youtube}](/reports/youtube/${latest.youtube})` : '（尚無資料）'}`)
lines.push('')
lines.push('其他：')
lines.push('')
lines.push('- 台股（TW）列表：`/reports/tw/`')
lines.push('- 美股（US）列表：`/reports/us/`')
lines.push('- YouTube 列表：`/reports/youtube/`')
lines.push('- Moltbook 列表：`/reports/moltbook/`')
lines.push('')
lines.push('> 這頁由 `bin/generate_home.mjs` 在 build/dev 前自動產生。')
lines.push('')

writeFileSync(join(docsDir, 'index.md'), lines.join('\n'), 'utf8')

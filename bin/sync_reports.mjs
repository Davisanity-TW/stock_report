import { existsSync, mkdirSync, readdirSync, rmSync, copyFileSync, statSync, writeFileSync } from 'node:fs'
import { join } from 'node:path'

function ensureDir(p) {
  mkdirSync(p, { recursive: true })
}

function copyMdTree(srcDir, dstDir) {
  if (!existsSync(srcDir)) return { copied: 0 }
  ensureDir(dstDir)

  // clean destination markdown files (keep folder)
  for (const f of readdirSync(dstDir)) {
    const p = join(dstDir, f)
    if (statSync(p).isFile() && f.endsWith('.md')) rmSync(p)
  }

  let copied = 0
  for (const f of readdirSync(srcDir)) {
    if (!f.endsWith('.md')) continue
    copyFileSync(join(srcDir, f), join(dstDir, f))
    copied++
  }
  return { copied }
}

function writeIndex(dir, title) {
  ensureDir(dir)
  writeFileSync(
    join(dir, 'index.md'),
    `# ${title}\n\n請從左側 sidebar 選擇檔案。\n`,
    'utf8'
  )
}

const root = process.cwd()
const reportsRoot = join(root, 'reports')
const docsReportsRoot = join(root, 'docs', 'reports')

ensureDir(docsReportsRoot)

const sections = [
  { key: 'tw', title: '台股（TW）' },
  { key: 'us', title: '美股（US）' },
  { key: 'youtube', title: 'YT-澔哥' },
  { key: 'moltbook', title: 'Moltbook' }
]

for (const s of sections) {
  const src = join(reportsRoot, s.key)
  const dst = join(docsReportsRoot, s.key)
  ensureDir(dst)
  copyMdTree(src, dst)
  writeIndex(dst, `${s.title} Reports`)
}

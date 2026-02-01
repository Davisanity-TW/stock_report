import { existsSync, mkdirSync, readdirSync, rmSync, copyFileSync, statSync, writeFileSync } from 'node:fs'
import { join } from 'node:path'

function ensureDir(p) { mkdirSync(p, { recursive: true }) }

function removeMdFilesInDir(dir) {
  if (!existsSync(dir)) return
  for (const f of readdirSync(dir)) {
    const p = join(dir, f)
    if (statSync(p).isFile() && f.endsWith('.md')) rmSync(p)
  }
}

function copyMdFlat(srcDir, dstDir) {
  if (!existsSync(srcDir)) return
  ensureDir(dstDir)
  removeMdFilesInDir(dstDir)
  for (const f of readdirSync(srcDir)) {
    if (!f.endsWith('.md')) continue
    copyFileSync(join(srcDir, f), join(dstDir, f))
  }
}

function writeIndex(dir, title) {
  ensureDir(dir)
  writeFileSync(join(dir, 'index.md'), `# ${title}\n\n請從左側 sidebar 選擇檔案。\n`, 'utf8')
}

const root = process.cwd()
const reportsRoot = join(root, 'reports')
const docsReportsRoot = join(root, 'docs', 'reports')
ensureDir(docsReportsRoot)

const sections = [
  { key: 'tw', title: '台股（TW）' },
  { key: 'us', title: '美股（US）' },
  { key: 'youtube', title: 'YT-澔哥' }
]

for (const s of sections) {
  const src = join(reportsRoot, s.key)
  const dst = join(docsReportsRoot, s.key)
  copyMdFlat(src, dst)
  writeIndex(dst, `${s.title} Reports`)
}

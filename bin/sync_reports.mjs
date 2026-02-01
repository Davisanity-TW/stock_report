import {
  existsSync,
  mkdirSync,
  readdirSync,
  rmSync,
  copyFileSync,
  statSync,
  writeFileSync
} from 'node:fs'
import { join } from 'node:path'

function ensureDir(p) {
  mkdirSync(p, { recursive: true })
}

function removeMdFilesInDir(dir) {
  if (!existsSync(dir)) return
  for (const f of readdirSync(dir)) {
    const p = join(dir, f)
    if (statSync(p).isFile() && f.endsWith('.md')) rmSync(p)
  }
}

function copyMdFlat(srcDir, dstDir) {
  if (!existsSync(srcDir)) return { copied: 0 }
  ensureDir(dstDir)
  removeMdFilesInDir(dstDir)

  let copied = 0
  for (const f of readdirSync(srcDir)) {
    if (!f.endsWith('.md')) continue
    copyFileSync(join(srcDir, f), join(dstDir, f))
    copied++
  }
  return { copied }
}

function copyMdTree(srcDir, dstDir) {
  // Copy markdown files recursively, preserving folders.
  if (!existsSync(srcDir)) return { copied: 0 }
  ensureDir(dstDir)

  let copied = 0
  for (const f of readdirSync(srcDir)) {
    const sp = join(srcDir, f)
    const dp = join(dstDir, f)
    const st = statSync(sp)

    if (st.isDirectory()) {
      const r = copyMdTree(sp, dp)
      copied += r.copied
      continue
    }

    if (st.isFile() && f.endsWith('.md')) {
      ensureDir(dstDir)
      copyFileSync(sp, dp)
      copied++
    }
  }

  return { copied }
}

function writeIndex(dir, title) {
  ensureDir(dir)
  writeFileSync(join(dir, 'index.md'), `# ${title}\n\n請從左側 sidebar 選擇檔案。\n`, 'utf8')
}

const root = process.cwd()
const reportsRoot = join(root, 'reports')
const docsReportsRoot = join(root, 'docs', 'reports')

ensureDir(docsReportsRoot)

// Stock report sections (flat weekly markdown)
const weeklySections = [
  { key: 'tw', title: '台股（TW）' },
  { key: 'us', title: '美股（US）' },
  { key: 'youtube', title: 'YT-澔哥' }
]

for (const s of weeklySections) {
  const src = join(reportsRoot, s.key)
  const dst = join(docsReportsRoot, s.key)
  copyMdFlat(src, dst)
  writeIndex(dst, `${s.title} Reports`)
}

// Moltbook: source from external repo submodule (recursive, preserve YYYYMM folders)
const moltbookSrc = join(root, 'external', 'moltbook', 'reports')
const moltbookDst = join(docsReportsRoot, 'moltbook', 'reports')

if (existsSync(moltbookSrc)) {
  // clean old md files in root and month folders
  ensureDir(moltbookDst)
  // remove any md files under dst recursively (lightweight)
  const stack = [moltbookDst]
  while (stack.length) {
    const dir = stack.pop()
    for (const f of existsSync(dir) ? readdirSync(dir) : []) {
      const p = join(dir, f)
      const st = statSync(p)
      if (st.isDirectory()) stack.push(p)
      else if (st.isFile() && f.endsWith('.md')) rmSync(p)
    }
  }

  copyMdTree(moltbookSrc, moltbookDst)
}

writeIndex(join(docsReportsRoot, 'moltbook'), 'Moltbook')
writeIndex(moltbookDst, 'Moltbook Reports')

# AGENTS.md — stock_report

This repo builds **Stock Report（研究日誌）**: 台股 / 美股收盤摘要與週檔彙整（VitePress + GitHub Pages）。

## 目標（What this repo is for）
- 將每日產出的研究摘要整理成**週檔**並上網：
  - 台股：`reports/tw/YYYY-Www.md`
  - 美股：`reports/us/YYYY-Www.md`
- 提供網站閱讀介面（最新週檔、分類導覽、首頁索引）。
- 支援每日 pipeline（cache → Telegram 發送 → 寫入週檔 → push）。

## 重要路徑（Key paths）
- `reports/`：資料來源（週檔 markdown）
  - `reports/tw/YYYY-Www.md`
  - `reports/us/YYYY-Www.md`
- `docs/`：VitePress 站點內容
  - `docs/index.md`：網站首頁
  - `docs/reports/**`：由 `bin/sync_reports.mjs` 同步產生/更新（請不要手動硬改生成區）
  - `docs/.vitepress/config.mts`：導覽/側邊欄（會掃資料夾生成列表）
- `bin/`：產製與同步腳本
  - `bin/sync_reports.mjs`：把 `reports/` 同步到 `docs/reports/`
  - `bin/generate_home.mjs`：生成首頁所需的索引內容
  - `bin/tw_report_data.py`、`bin/tw_make_table.py`、`bin/ingest_youtube_summary.py`：資料整理/格式化工具
- `.github/workflows/deploy.yml`：GitHub Pages 部署

## 常用命令（Commands）
```bash
cd /home/ubuntu/clawd/stock_report

# 本機開發（會先同步 reports → docs，再開 dev server）
npm run docs

# 建置（同樣會先同步/生成）
npm run build

# 預覽
npm run serve
```

## 產出規範（Output conventions）
- 時區：內容中涉及「收盤/日期」一律以 **Asia/Taipei** 為準。
- `reports/tw/`、`reports/us/` 的週檔：
  - 請維持一致的標題/段落結構（同週內 append 新的一天）
  - 優先追加（append），不要重排舊內容（避免歷史對照/連結變動）
- `docs/reports/**` 主要由腳本同步生成：
  - **不要**直接把大量內容只改在 `docs/`，否則下次 sync 可能被覆蓋。

## 禁止事項（Do not）
- 不要把 Telegram / GitHub token、cookies、API keys 進 repo。
- 不要在公開報告中貼出任何私密資訊（帳號、內網、log 原文含敏感欄位）。
- 不要改動 `docs/.vitepress/config.mts` 的路徑規則，除非同時更新 `bin/sync_reports.mjs` 的輸出結構並驗證 build。

## 常見操作指引（Practical rules）
- 要更新網站內容：通常只需要改 `reports/**`，再跑 `npm run build`。
- 若是 cron 產線寫入週檔：建議只修改 `reports/**`，避免碰到 VitePress 設定。

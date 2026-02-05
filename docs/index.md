# Stock Report（研究日誌）

最新入口（自動更新）：

- 台股（TW）：[./reports/tw/index](./reports/tw/index)
- 美股（US）：[./reports/us/index](./reports/us/index)
- YT-澔哥：[./reports/youtube/index](./reports/youtube/index)
- 財經新聞快報：[./reports/finance_news/index](./reports/finance_news/index)
- Moltbook：[./reports/moltbook/reports/202602/02-01](./reports/moltbook/reports/202602/02-01)

列表：

- 台股（TW）列表：`/reports/tw/`
- 美股（US）列表：`/reports/us/`
- YT-澔哥 列表：`/reports/youtube/`
- 財經新聞快報 列表：`/reports/finance_news/`
- Moltbook 列表：`/reports/moltbook/reports/`


排程（自動更新）：

- 台股收盤：14:55 產生快取 → 15:00 Telegram 發送（<3500 字）→ 15:05 寫入週檔並 push → 17:00 法人更新（insti refresh，更新週檔並發送 Telegram）
- 美股收盤：06:28 產生快取 → 06:35 Telegram 發送 → 06:40 寫入週檔並 push
- YT-澔哥：每日 11:10 摘要＋發送 Telegram＋寫入週檔並 push
- 財經新聞快報：每日 08:00 / 16:00 / 21:00（Asia/Taipei，近 5 小時｜台灣+國際；RSS 去重；台灣最多 8、國際最多 8；主軸 3 點／追蹤 3 點；國際英文會翻譯為繁中）

> 這頁由 `bin/generate_home.mjs` 在 build/dev 前自動產生。

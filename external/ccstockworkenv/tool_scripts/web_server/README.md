# CCStockWorkEnv Web Server

CCStockWorkEnv 報告瀏覽網站。將研究報告以 RWD 響應式網頁呈現,方便在手機上閱讀。

報告產生後,自動發送連結到 Telegram,點擊即可在手機瀏覽器開啟。

---

## 快速開始

### 1. 安裝依賴

```bash
cd tool_scripts/web_server
uv sync
```

### 2. 設定 config.json

在專案根目錄的 `config.json` 中新增 `web_server` 區塊：

```json
{
  "web_server": {
    "fixed_ip": "你的固定 IP",
    "port": 8800,
    "enable_auto_start": true
  }
}
```

查詢本機 IP：

```bash
ifconfig | grep "inet " | grep -v 127.0.0.1
```

### 3. 註冊為系統服務 (開機自動啟動)

plist 檔案位於：

```
~/Library/LaunchAgents/com.ccstockworkenv.webserver.plist
```

**首次啟用** — 在 Terminal.app 中執行：

```bash
launchctl load ~/Library/LaunchAgents/com.ccstockworkenv.webserver.plist
```

完成後，web server 會：
- 立即啟動
- 開機時自動啟動
- 意外停止時自動重啟

### 4. 確認服務運行

```bash
# 檢查服務狀態
launchctl list | grep ccstockworkenv

# 測試網頁
curl http://localhost:8800

# 或直接開啟瀏覽器
open http://localhost:8800
```

---

## 服務管理

### 停止服務

```bash
launchctl unload ~/Library/LaunchAgents/com.ccstockworkenv.webserver.plist
```

### 重新啟動服務

```bash
launchctl unload ~/Library/LaunchAgents/com.ccstockworkenv.webserver.plist
launchctl load ~/Library/LaunchAgents/com.ccstockworkenv.webserver.plist
```

### 查看日誌

```bash
# 標準輸出
tail -f data/webserver.log

# 錯誤日誌
tail -f data/webserver.error.log
```

### 手動啟動 (不透過 launchd)

```bash
cd tool_scripts/web_server
bash start_server.sh
```

---

## Router Port Forwarding 設定

要讓手機從外網 (行動網路) 或區網存取報告，需要在 Router 上設定 Port Forwarding。

### 名詞說明

| 名詞 | 說明 |
|------|------|
| **外部 Port (Outer Port)** | 從外網連入時使用的 port。建議設為 `8800` |
| **內部 Port (Inner Port)** | 本機 web server 監聽的 port。設為 `8800` |
| **內部 IP** | 運行 web server 的本機區網 IP |
| **公網 IP (固定 IP)** | ISP 提供的固定 IP 位址 |

### 設定步驟

#### Step 1: 確認本機區網 IP

```bash
ifconfig | grep "inet " | grep -v 127.0.0.1
```

找到 `192.168.x.x` 開頭的 IP (例如 `192.168.0.188`)。

#### Step 2: 登入 Router 管理介面

在瀏覽器輸入 Router 的管理 IP (通常是以下其中之一)：

```
http://192.168.0.1
http://192.168.1.1
```

用 Router 的管理帳號密碼登入 (通常貼在 Router 機身上)。

#### Step 3: 找到 Port Forwarding 設定

不同品牌的路徑不同：

| 品牌 | 設定路徑 |
|------|---------|
| **ASUS** | 進階設定 → WAN → 虛擬伺服器 / Port Forwarding |
| **TP-Link** | 進階 → NAT 轉發 → 虛擬伺服器 |
| **Netgear** | 進階 → 進階設定 → Port Forwarding |
| **中華電信 (Zyxel)** | 網路設定 → NAT → Port Forwarding |
| **D-Link** | 進階 → 虛擬伺服器 |

#### Step 4: 新增規則

填入以下欄位：

```
服務名稱:    CCStockWorkEnv
協定:        TCP
外部 Port:   8800
內部 IP:     192.168.0.188    (改成你的本機 IP)
內部 Port:   8800
```

**設定範例 (以 ASUS Router 為例):**

```
+------------------+------------------------------+
| 服務名稱         | CCStockWorkEnv                     |
| 通訊協定         | TCP                           |
| 外部埠           | 8800                          |
| 內部 IP 位址     | 192.168.0.188                 |
| 內部埠           | 8800                          |
| 來源 IP          | (留空 = 不限制)               |
+------------------+------------------------------+
```

#### Step 5: 儲存並測試

1. 儲存 Router 設定

2. 測試區網存取：
   ```bash
   curl http://192.168.0.188:8800
   ```

3. 測試外網存取 (用手機行動網路)：
   ```
   http://你的固定IP:8800
   ```

#### Step 6: 更新 config.json

將 `fixed_ip` 設為你的公網固定 IP：

```json
{
  "web_server": {
    "fixed_ip": "你的固定IP",
    "port": 8800,
    "enable_auto_start": true
  }
}
```

### 安全性建議

- 只開放需要的 port (8800)，不要開放範圍 port
- 考慮使用非標準 port (例如 18800) 減少被掃描的機率
- Router 端可設定「來源 IP」限制，只允許特定 IP 連入

---

## 使用流程

### 透過 Telegram Bot 產生報告

```
/gen_report cn_3yr_low
```

系統會自動：
1. 產生 HTML 報告
2. 確認 web server 運行中
3. 產生報告連結
4. 發送連結到 Telegram

Telegram 收到的訊息：

```
📊 報告已產生

類型: 中國A股三年低點研究
時間: 2026-02-28 23:49

🔗 點此瀏覽報告

✅ Telegram 已收到連結
💡 點擊連結在手機瀏覽器開啟效果最佳
```

### 手動瀏覽所有報告

開啟瀏覽器訪問：

```
http://你的固定IP:8800
```

會看到所有報告的列表，點擊即可查看。

---

## 故障排除

### Web server 沒有啟動

```bash
# 檢查服務狀態
launchctl list | grep ccstockworkenv

# 如果沒有輸出，重新載入
launchctl load ~/Library/LaunchAgents/com.ccstockworkenv.webserver.plist

# 查看錯誤日誌
cat data/webserver.error.log
```

### Port 被占用

```bash
# 查看誰在用 8800
lsof -i :8800

# 終止該程序
kill <PID>

# 重新啟動服務
launchctl unload ~/Library/LaunchAgents/com.ccstockworkenv.webserver.plist
launchctl load ~/Library/LaunchAgents/com.ccstockworkenv.webserver.plist
```

### 外網無法連線

檢查順序：
1. web server 是否運行? `curl http://localhost:8800`
2. 區網是否能連? `curl http://192.168.0.188:8800`
3. Router Port Forwarding 是否正確?
4. macOS 防火牆是否阻擋?

macOS 防火牆設定：
- 系統設定 → 網路 → 防火牆
- 確認 Python 已加入允許清單

### 報告列表是空的

- 確認 `output/` 目錄有 `.html` 或 `.md` 檔案
- 確認檔名格式：`YYYYMMDD_HHMM_<type>.html`
- 查看日誌：`tail data/webserver.log`

---

## 檔案結構

```
tool_scripts/web_server/
├── pyproject.toml              # Python 依賴 (Django 5.1)
├── manage.py                   # Django 管理入口
├── start_server.sh             # 手動啟動腳本
├── README.md                   # 本文件
├── config/                     # Django 設定
│   ├── settings.py             #   核心設定
│   ├── urls.py                 #   根路由
│   └── wsgi.py                 #   WSGI 入口
└── reports/                    # 報告瀏覽 App
    ├── views.py                #   頁面邏輯
    ├── urls.py                 #   路由
    ├── report_scanner.py       #   報告掃描器
    ├── templates/reports/      #   HTML 模板
    │   ├── base.html           #     基礎版面
    │   ├── list.html           #     報告列表
    │   └── detail.html         #     報告內容
    └── static/reports/css/     #   樣式
        └── mobile.css          #     RWD 響應式樣式

系統服務:
~/Library/LaunchAgents/com.ccstockworkenv.webserver.plist

日誌:
data/webserver.log              # 標準輸出
data/webserver.error.log        # 錯誤輸出
```

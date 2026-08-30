# 0050 成分股均線篩選器

對 0050（元大台灣50）成分股跑一次「最近一日收盤價站上幾條均線（5MA/10MA/20MA/60MA）」
的篩選，依站上的均線數量分成四個等級，產出一頁 HTML 網頁報告：

| 等級 | 名稱 | 條件 |
|---|---|---|
| 4 | 四海遊龍 | 收盤價同時站上 5MA、10MA、20MA、60MA |
| 3 | 三陽開泰 | 站上 5MA、10MA、20MA |
| 2 | 短線翻多訊號 | 站上 5MA、10MA |
| 1 | 準備短線翻多 | 站上 5MA |

分級是巢狀判定：例如「三陽開泰」代表同時站上 5/10/20MA，但**不代表**跌破 60MA——
若也站上 60MA 會被歸類到更高一級的「四海遊龍」。每檔股票只會落在其中一級。

這個專案是從「[公司基本面分析](../公司基本面分析/)」（台股投資分析 PDF 報告產生器）
專案中獨立拆分出來的均線篩選功能，兩者互相獨立、互不依賴，各自可以單獨開發、部署。

## 安裝

```powershell
py -m venv .venv
.venv\Scripts\pip install -r requirements.txt
```

## 使用方式

### 命令列 (CLI)

```powershell
.venv\Scripts\python -m etf_screener.cli
```

結果會存到 `reports/0050均線篩選_日期.html`，並在終端機印出各等級檔數摘要。

### 網頁介面 (Streamlit)

```powershell
.venv\Scripts\python -m streamlit run etf_screener/app_streamlit.py
```

也可以直接雙擊 `啟動網頁介面.bat`，會自動啟動服務並開啟瀏覽器。

**雲端部署**：跟公司基本面分析專案一樣，可直接部署到
[Streamlit Community Cloud](https://share.streamlit.io)（免費），Main file path 填
`etf_screener/app_streamlit.py`；要開啟密碼保護，在 Secrets 填入
`APP_PASSWORD = "你的密碼"`。

## 資料來源

- **股價**：[FinMind](https://finmind.github.io/) 公開 API（免登入）為主，失敗時改用
  證交所 STOCK_DAY 官方備援。
- **0050 成分股清單**：手動維護的靜態清單（見 `etf_screener/etf0050_constituents.py`），
  因為沒有免費、免登入的官方 API 可以直接查詢 ETF 成分股。0050 每年 3/6/9/12 月審核
  一次成分股，**清單需要每季人工核對更新**，檔案開頭已註明查核來源與方式。

## 已知限制

- 成分股清單是靜態資料，若剛好碰到季度換股生效後、尚未手動更新清單的空窗期，
  可能會出現一兩檔已被替換的股票。
- 只驗證過上市股票的官方備援（證交所 STOCK_DAY），0050 成分股皆為上市大型股，
  不受影響。
- 均線分級（5/10/20/60 日、四個等級的巢狀判定）是常見的技術分析框架，非官方
  統一標準。

## 重要聲明

所有投資相關內容僅供參考，不構成任何投資建議，使用者應自行評估風險。

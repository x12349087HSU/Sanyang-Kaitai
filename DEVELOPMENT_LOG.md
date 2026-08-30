# 開發紀錄

這份文件記錄「均線篩選器」（Sanyang-Kaitai）專案從 0 到目前狀態的關鍵決策、
考量過的取捨、以及已知限制。目的是讓之後不管是你自己還是協助開發的人（包含
未來的 Claude 對話），不用重新想一次已經想過的問題。

一般的「怎麼安裝、怎麼用」請看 [README.md](README.md)；這份文件是給
「要改程式碼或接續開發的人」看的。

---

## 1. 這個專案跟「公司基本面分析」的關係

「均線篩選器」最初是在「[公司基本面分析](../公司基本面分析/)」（台股投資分析
PDF 報告產生器）專案裡，以「0050 成分股均線篩選」功能的形式開發出來的。後來
使用者要求把這個功能**完全獨立拆分出來**，成為一個自己的資料夾、自己的
git repo（`https://github.com/x12349087HSU/Sanyang-Kaitai`）、自己的 `.venv`，
兩邊互不依賴、各自可以單獨開發部署。

拆分時的做法：不是共用匯入，而是把需要的最小子集（config/cache/http_client/
finmind_client/providers/price、models 精簡版、moving_average）**複製一份**
到這個專案裡自己維護。好處是這個專案完全不需要 pandas/matplotlib——原本公司
基本面分析專案的依賴，這裡都用不到，只需要 `requests` + `streamlit` +
`reportlab`，是刻意的精簡，不是漏掉。

**已知的權衡**：兩邊的股價 provider 邏輯（FinMind + 證交所備援、資料品質過濾）
是分開維護的兩份複本。如果之後在其中一邊修到 bug（例如未來又發現 FinMind
哪個資料集有累計數/單季數搞混之類的問題），**要記得檢查另一邊是否也要同步修**，
不會自動同步。

「公司基本面分析」專案裡原本也留著一份較舊、較簡化版本的 0050 均線篩選（只有
多頭四級、只能掃 0050、沒有 PDF），是使用者明確要求「兩邊都保留」時留下的
snapshot，**沒有跟著這個專案之後的功能（反向篩選、top150、PDF）一起更新**。

---

## 2. 為什麼股票池是「0050 + 0051」而不是全部上市公司

使用者一開始要求「直接在上市公司中尋找標的」，也就是想掃描全部約 1000 檔上市
公司。但 FinMind 免費 API 有每小時請求次數上限（無 token 約 300 次/小時，
免費註冊 token 約 600 次/小時），全市場掃描一次可能要 1~3 小時，不適合塞進
Streamlit 網頁裡等待（尤其部署到 Streamlit Community Cloud 之後，雲端環境
通常有請求逾時限制，長時間運算容易被中斷）。

跟使用者討論後的折衷方案：改成「上市市值前 150 大」。這剛好可以用兩檔 ETF
的成分股湊出來，不需要另外算市值排名：
- 0050（元大台灣50）追蹤「臺灣50指數」＝ 市值前 50 大
- 0051（元大中型100）追蹤「臺灣中型100指數」＝ 市值第 51～150 名

兩者官方定義上互補不重疊，加總剛好是前 150 大，且 150 檔遠低於免費 API 額度，
一次掃描只需要幾秒到十幾秒。

## 3. 為什麼成分股清單是手動維護的靜態清單

FinMind 的 ETF 成分股資料集（`TaiwanStockActiveETFHolding`）需要付費 Sponsor
方案；證交所 OpenAPI 也查不到對應的免費端點；元大投信官方網站（yuantaetfs.com）
雖然有「申購買回清單」頁面會每日公布完整成分股，但是用 Nuxt.js 前端動態載入，
實際資料是透過內部 API（`/api/bridge`、`/api/trans` 之類，未進一步逆向）拉的，
沒有找到穩定、文件化的公開 JSON 端點可以直接串接。

因此比照公司基本面分析專案 `aliases_seed.py` 的做法，改用手動維護的靜態清單
（`etf0050_constituents.py` / `etf0051_constituents.py`）。查核方式：先用
WebFetch 讀玩股網（wantgoo.com，robots.txt 允許）的成分股頁面拿到完整名單，
再用該股票代號逐一比對是否出現在元大投信官方 PCF 頁面的原始 HTML（用 curl 抓
下來直接 grep 股票代號字串，不解析頁面結構，因為那是 client-side render 的
Nuxt payload，格式不穩定不適合寫程式解析）裡，兩邊都對得上才收錄，算是一種
「兩個獨立來源交叉驗證」的土法煉鋼查核法。

**這份清單需要每季（3/6/9/12 月）人工重新查核更新**，兩個檔案開頭都已經寫了
查核來源網址與方法，照著重跑一次就可以。

## 4. 均線分級邏輯：從 4 級到 8 級

最初版本只有多頭四級（四海遊龍／三陽開泰／短線翻多訊號／準備短線翻多）。
使用者後續要求加上對稱的空頭四級（四面楚歌／三聲無奈／短線翻空／注意停損），
邏輯是完全鏡像：多頭看「站上」幾條均線，空頭看「跌破」幾條均線，兩者都是
**巢狀判定**（例如「三陽開泰」代表站上 5/10/20MA，但不代表跌破 60MA——如果
也站上 60MA 會被歸類到更高一級的「四海遊龍」），每檔股票只會落在其中一級，
多空訊號不一致（例如站上 5MA 但跌破 10MA）的股票不列入這八個等級（`tier=0`）。

分級判斷寫在 `ma_screener.py` 的 `_classify_tier()`，先判多頭鏈（4→3→2→1），
四種都不成立才判空頭鏈（-4→-3→-2→-1），最後都不成立回傳 0。均線本身用
`moving_average.py` 的簡單移動平均（SMA），抓 6 個月股價資料當暖身（約可
涵蓋 100+ 交易日），確保 60MA 在最近一日一定算得出來（除非該股票掛牌不到
60 個交易日，這種情況目前沒有特別防呆，`ma60` 會是 `None`，該股票就無法進入
多頭 4 級或空頭 -4 級，但仍可能落入其他等級）。

## 5. PDF + HTML 雙輸出，以及 PC/iPhone 開啟方式

一開始只有 HTML 網頁版（`screen_page.py`），後來使用者要求要能在 PC 用瀏覽器
開啟並下載、iPhone 上也要能開啟/下載/分享，於是新增了 `pdf_report.py`
（ReportLab Platypus）產出 PDF，兩種格式內容一致，只是呈現形式不同：HTML
適合網頁上直接瀏覽（尤其 Streamlit 內嵌預覽），PDF 適合下載、分享、列印保存。

PC/iPhone 的開啟/下載/分享，直接照搬公司基本面分析專案已經驗證過的解法
（`app_streamlit.py` 裡的 `components.html` 區塊），沒有重新踩坑：
- **不要用 `data:` URI 做「開新分頁導覽」**：會被瀏覽器防釣魚機制擋下，結果
  是空白頁。改用 Blob URL（`URL.createObjectURL`）。
- **不要依賴 `<a download>`**：iPhone Safari 常常改觸發系統層級的 Quick Look
  預覽，把畫面整個蓋掉。改用 Blob URL + `window.open()`。
- 額外提供 Web Share API（`navigator.share`）當作「選擇開啟方式」按鈕，讓
  iPhone 使用者可以分享到其他 App（例如存到「檔案」）。

CJK 字型（`fonts.py`）也是照搬同一套跨平台偵測邏輯：本機優先用 Windows 內建
微軟正黑體，找不到時（雲端 Linux 主機）退回專案內建的 Noto Sans TC
（`assets/fonts/`，OFL 授權，這是為什麼這個「輕量」專案的 repo 裡也有一個
12MB 字型檔的原因——雲端部署一定要有，不能只靠本機系統字型）。

## 5.1 結果呈現：從「8 個區塊全部一起顯示」改成「下拉篩選只顯示一個等級」

最初版本（第 5 節）是 8 個等級的表格全部堆疊在同一頁，使用者要自己往下捲動找
想看的等級。使用者要求改成用下拉選單（`<select>`）一次只篩選顯示一個等級的
資料，選項順序照多頭到空頭排列（四海遊龍→三陽開泰→...→四面楚歌，即
`TIER_ORDER` 原本的順序，不需要改）。

做法是**純前端 JavaScript**，不是後端重新查詢：`screen_page.py` 產生 HTML 時
8 個 `<section class="tier" data-tier="...">` 全部都在，只是預設除了第一個
（四海遊龍）以外都有 `hidden` 屬性；下拉選單的 `change` 事件監聽器切換各
section 的 `hidden` 屬性，藉此做到「篩選成功後只剩該分類資料顯示」的效果，
不用重新產生 HTML 或重新整理頁面。這個實作直接寫在 `screen_page.py`（純
vanilla JS，沒有外部套件），好處是**同一份邏輯同時用在兩個地方**：獨立下載
開啟的 HTML 檔，以及 Streamlit 用 `components.html` 內嵌的那份——不用分開
實作一次 Streamlit 原生版本、一次靜態 HTML 版本。

連帶把 `app_streamlit.py` 原本「篩選完成後另外用 `st.metric` 顯示 8 個等級
檔數」的區塊拿掉了（下拉選單的每個選項文字裡已經有檔數，例如「四海遊龍
（26 檔）」，不需要在頁面上重複兩份）；也把內嵌 HTML 的 `components.html`
高度從 1400 降到 850，並在 `screen_page.py` 的表格加上 `max-height: 55vh` +
內部捲動（`overflow: auto`），因為現在畫面上一次只會有一個等級的表格，
不需要再預留「8 個表格全部展開」那麼多高度，但不同等級的檔數差異很大
（可能 1 檔到 60 幾檔），表格內部自己捲動比固定 iframe 高度更穩定。

## 6. iPhone「加入主畫面」：只做了 PWA meta 標籤，沒有做自訂圖示

使用者問過「怎麼做成 iPhone App」，說明過兩條路：
1. PWA 方式（Safari 分享 → 加入主畫面）：不需要 Apple 開發者帳號、不用審核，
   現在就能用。
2. 真正上架 App Store：要重寫 Swift/SwiftUI 前端、要 Apple Developer Program
   年費、要送審，工程量完全不同等級，個人工具不划算。

使用者選了方式一，並且明確說「LOGO 目前先不需要」。因此目前只加了
`apple-mobile-web-app-capable`、`apple-mobile-web-app-title`、`theme-color`
這幾個 meta 標籤（讓加入主畫面後開啟是全螢幕獨立模式，沒有 Safari 網址列），
**沒有**做自訂的 favicon/apple-touch-icon，圖示維持 Streamlit 預設的 📈 emoji。

如果之後要做自訂圖示，公司基本面分析專案已經踩過這個坑：iOS 讀取圖示的時機
可能比 `st.markdown(unsafe_allow_html=True)` 注入 `<link>` 標籤的 JS 執行
時機更早，導致圖示不保證每次都套用成功；更徹底的做法（直接覆寫 Streamlit
套件內建的 `static/index.html`）在 Streamlit Community Cloud 上會因為
`site-packages` 唯讀而失敗（`PermissionError`）。這是 Streamlit 平台本身的
限制，不是這個專案獨有的問題。

## 7. 部署

Repo 一開始建立時是 private，後來為了能在 Streamlit Community Cloud 部署
（跟公司基本面分析專案一樣的教訓：private repo 在 Streamlit Cloud 的
「選擇 repo」選單裡選不到），改成了 **public**（已確認程式碼裡沒有任何密碼
/token 等敏感資訊——密碼保護是透過 Streamlit Cloud 的 Secrets 功能設定
`APP_PASSWORD`，不會出現在程式碼或 git 歷史裡）。

部署步驟見 [README.md](README.md) 的「使用方式」段落。Main file path 是
`etf_screener/app_streamlit.py`。

---

## 8. 已知限制（目前沒有解法，非 bug）

- 成分股清單（0050+0051）是靜態資料，每季換股後有空窗期需要人工更新，見第 3 節。
- 「上市市值前 150 大」是用兩檔 ETF 成分股近似，不是每日重新計算真實市值排名，
  剛好卡在第 150 名附近、還沒反映在 ETF 換股上的股票可能有落差。
- 只驗證過上市股票的官方股價備援（證交所 STOCK_DAY），0050/0051 成分股皆為
  上市股票，不受影響，但如果之後把股票池換成含上櫃股票的清單，備援會不可用
  （這點跟公司基本面分析專案的已知限制一樣）。
- iPhone「加入主畫面」的自訂圖示還沒做（見第 6 節），目前用預設 emoji 圖示。
- 均線分級（5/10/20/60 日、八個等級的巢狀判定）是常見技術分析框架，非官方
  統一標準，也不構成任何買賣建議。

## 9. 如果要繼續開發，建議先看這幾個檔案

- `ma_screener.py` — 均線分級邏輯核心，加新的分級規則或新股票池大概率要碰這裡
- `etf0050_constituents.py` / `etf0051_constituents.py` — 股票池清單，每季要
  手動查核更新
- `providers/price.py` — 股價來源（FinMind + 證交所備援），跟公司基本面分析
  專案是分開維護的複本，修 bug 記得檢查另一邊
- `screen_page.py` / `pdf_report.py` — 兩種輸出格式，改呈現內容通常要兩邊一起改
- `app_streamlit.py` — 網頁介面，PC/iPhone 開啟方式的細節都在這裡

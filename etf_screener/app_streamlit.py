"""Streamlit 網頁介面：對 0050 成分股跑均線篩選。

執行方式：py -m streamlit run etf_screener/app_streamlit.py

密碼保護：部署到公開網路（如 Streamlit Community Cloud）時，在該平台的 Secrets
設定中加入 APP_PASSWORD = "你的密碼"，即會啟用簡易密碼保護；本機開發若未設定
APP_PASSWORD（環境變數或 .streamlit/secrets.toml 皆可），則不會要求輸入密碼。
"""
from __future__ import annotations

import base64
import json
import os
import sys
from pathlib import Path

# Streamlit Community Cloud 執行時不會像本機 `python -m streamlit run` 一樣把
# 專案根目錄放進 sys.path，導致 `import etf_screener.*` 失敗（ModuleNotFoundError）。
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import streamlit as st
import streamlit.components.v1 as components

from etf_screener.ma_screener import screen_0050, screen_top150
from etf_screener.pdf_report import render_screen_pdf
from etf_screener.screen_page import render_screen_html

_UNIVERSES = {
    "0050 成分股（約 50 檔，快）": ("0050 成分股", screen_0050),
    "上市市值前 150 大（0050+0051，約 150 檔，較久）": ("上市市值前150大", screen_top150),
}

# 側欄（PDF／HTML 下載動作）預設收合，不要一進站就自動彈出——選篩選範圍
# 的動作現在是主畫面上的「選單」按鈕（見下方 st.popover），側欄只在有篩選
# 結果、需要下載 PDF／HTML 時才需要，使用者要用再自己點左上角圖示打開。
st.set_page_config(
    page_title="均線篩選器",
    page_icon="📈",
    initial_sidebar_state="collapsed",
)

# 讓 iPhone Safari「分享 → 加入主畫面」後，開啟時是全螢幕獨立模式（沒有網址列，
# 更像原生 App），並在主畫面圖示下方顯示簡短的名稱，而不是完整網址。跟原本
# 「公司基本面分析」專案的 apple-touch-icon 做法一樣，用 st.markdown 把 <meta>
# 標籤插進主頁面 DOM（不是圖示，不需要另外準備圖檔）。已知限制：這是頁面 JS
# 執行後才生效，不是伺服器最原始送出的 HTML 就有，如果 iOS 讀取時機更早，
# 效果可能不會每次都套用，這是 Streamlit 平台本身的限制。
st.markdown(
    """
    <meta name="apple-mobile-web-app-capable" content="yes">
    <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
    <meta name="apple-mobile-web-app-title" content="均線篩選器">
    <meta name="theme-color" content="#7a1414">
    """,
    unsafe_allow_html=True,
)

# 縮減 Streamlit 主內容區預設的左右/上下留白，讓內嵌的篩選結果表格盡量貼齊
# 螢幕邊緣（「滿版顯示」），手機窄螢幕上尤其明顯；只套用在 `.main`，刻意不動
# 側欄（sidebar）本身的留白，避免側欄選單跟著被擠壓。
st.markdown(
    """
    <style>
    /* 手機上兩指在技術分析圖表上縮放時，如果手指有一點點超出圖表畫布範圍
       （碰到標題列/圖例），瀏覽器會把手勢當成整個網頁的原生縮放，而不是
       圖表自己那組用 JS 寫的「只放大圖表數據」手勢——網頁一旦被原生縮放，
       版面跑掉、又因為圖表畫布本身會攔截滑動事件（做查價/平移用），會
       連帶擋掉使用者想滑動網頁去找「返回」按鈕的動作，變成整個卡住滑不
       動、也回不去上一頁。這裡直接關掉整個網頁的原生縮放手勢（pan-x/
       pan-y 還是保留，一般上下捲動不受影響），圖表自己的縮放邏輯是另外
       寫在 canvas 元素自己的 JS 事件裡，不受影響，兩者不會互相干擾。 */
    html, body {
        touch-action: pan-x pan-y;
    }
    .main .block-container {
        padding-top: 1.2rem;
        padding-bottom: 1rem;
        padding-left: 1rem;
        padding-right: 1rem;
        max-width: 100%;
    }
    @media (max-width: 640px) {
        /* 手機寬度下，主內容區左右留白幾乎收到 0，讓下方內嵌的篩選結果
           表格可以貼齊螢幕邊緣（真正「滿版」），不是只留一點點窄邊而已。 */
        .main .block-container { padding-left: 0.3rem; padding-right: 0.3rem; }
    }
    /* Streamlit 原生的側欄開關按鈕（收合時是左上角一個很小的箭頭圖示）預設
       不太顯眼，使用者反映找不到。這裡直接放大圖示、加上品牌色圓形底色跟
       陰影，讓它看起來更像一個「按鈕」而不是隨便一個小箭頭。這個
       data-testid 是側欄開/關共用同一顆按鈕（在側欄展開時位於側欄頂端、
       收合時浮動在主畫面左上角），兩種狀態套用同一套樣式即可。 */
    [data-testid="stSidebarCollapseButton"] button {
        background: #7a1414 !important;
        border-radius: 999px !important;
        box-shadow: 0 2px 8px rgba(0,0,0,0.3) !important;
        padding: 0.4rem !important;
    }
    [data-testid="stSidebarCollapseButton"] button:hover {
        background: #9a1c1c !important;
    }
    [data-testid="stSidebarCollapseButton"] svg {
        color: #fff !important;
        fill: #fff !important;
        width: 1.5em !important;
        height: 1.5em !important;
    }
    /* 首頁「下拉選擇篩選內容」選單按鈕：原本用 use_container_width=True 撐滿
       整個欄寬，字沒幾個卻框一大格，改成不撐滿（寬度貼合文字本身），字級
       加大、置中顯示。stPopover 是整顆按鈕的外層容器（預設跟其他元件一樣
       是撐滿欄寬的區塊），對它套 flex + justify-content:center 讓裡面貼合
       文字寬度的按鈕整個置中；這個 CSS 選到的是元件外層容器本身，不會連帶
       把按鈕自己撐滿寬度。 */
    [data-testid="stPopover"] {
        display: flex;
        justify-content: center;
    }
    [data-testid="stPopoverButton"] button {
        font-size: 1.5rem !important;
        padding: 1rem 2.2rem !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


def _get_configured_password() -> str | None:
    try:
        secret_pwd = st.secrets.get("APP_PASSWORD")
    except Exception:
        secret_pwd = None
    return secret_pwd or os.environ.get("APP_PASSWORD") or None


def _require_password() -> bool:
    """回傳是否已通過密碼驗證（或本來就不需要密碼）。"""
    correct_password = _get_configured_password()
    if not correct_password:
        return True
    if st.session_state.get("authenticated"):
        return True

    st.title("均線篩選器")
    st.info("此服務已啟用密碼保護，請輸入密碼後繼續。")
    entered = st.text_input("密碼", type="password")
    if st.button("登入"):
        if entered == correct_password:
            st.session_state["authenticated"] = True
            st.rerun()
        else:
            st.error("密碼錯誤，請再試一次。")
    return False


if not _require_password():
    st.stop()

if st.session_state.pop("_collapse_sidebar_next", False):
    # 側欄沒有官方 API 可以在腳本裡強制收合，瀏覽器又會用 localStorage 記住
    # 使用者上次手動展開/收合側欄的選擇，`initial_sidebar_state` 只在完全沒有
    # 記憶時才有效——所以剛在側欄裡點按鈕重新篩選完後，側欄仍然會維持在
    # 「使用者剛剛手動點開」的展開狀態，不會自動收回去。這裡用一小段注入的
    # JS 檢查側欄目前是不是展開（`[data-testid="stSidebar"]` 的
    # `aria-expanded` 屬性），是的話就模擬點擊側欄自己的收合按鈕，效果等同
    # 使用者自己再點一次收合。依賴的是 Streamlit 內部沒有公開文件的
    # data-testid，屬於盡力而為的做法，Streamlit 版本更新如果改了這些內部
    # 標記，頂多是側欄不會自動收合，不會因此噴錯。
    components.html(
        """
        <script>
        (function () {
          function tryCollapse(attempt) {
            try {
              var doc = window.parent.document;
              var sidebar = doc.querySelector('[data-testid="stSidebar"]');
              if (sidebar && sidebar.getAttribute('aria-expanded') === 'true') {
                var btn = sidebar.querySelector('[data-testid="stSidebarCollapseButton"] button');
                if (btn) { btn.click(); return; }
              }
            } catch (e) {}
            if (attempt < 5) { setTimeout(function () { tryCollapse(attempt + 1); }, 150); }
          }
          tryCollapse(0);
        })();
        </script>
        """,
        height=0,
    )

if "etf_screen_result" not in st.session_state:
    st.session_state["etf_screen_result"] = None
if "etf_screen_universe_label" not in st.session_state:
    st.session_state["etf_screen_universe_label"] = None

screen_result = st.session_state["etf_screen_result"]
clicked_universe = None

if screen_result is None:
    # 還沒有篩選結果：選單留在主畫面，用 st.popover 平常收合成一顆按鈕，點開
    # 才彈出兩個選項；選項本身就是「直接開始篩選」的按鈕，不用先選範圍、
    # 再另外按一次「開始篩選」——點哪個範圍就直接跑那個範圍。
    with st.popover("下拉選擇篩選內容"):
        st.caption("點選要篩選的範圍，點下就會直接開始篩選：")
        for label, (universe_label_option, screen_fn_option) in _UNIVERSES.items():
            if st.button(label, use_container_width=True, key=f"start_{universe_label_option}"):
                clicked_universe = (universe_label_option, screen_fn_option)
else:
    # 已經有篩選結果：選單整合進左側側欄（跟 PDF／HTML 下載放在一起），主畫面
    # 只留「均線篩選器」的報告內容本身；要重新篩選再自己點開側欄選就好。
    with st.sidebar:
        for label, (universe_label_option, screen_fn_option) in _UNIVERSES.items():
            if st.button(label, use_container_width=True, key=f"start_{universe_label_option}"):
                clicked_universe = (universe_label_option, screen_fn_option)

if clicked_universe is not None:
    universe_label, screen_fn = clicked_universe
    with st.spinner(f"正在逐檔查詢「{universe_label}」股價並計算均線，請稍候..."):
        st.session_state["etf_screen_result"] = screen_fn()
        st.session_state["etf_screen_universe_label"] = universe_label
    # 「選單要放主畫面還是側欄」是在這次執行最前面（screen_result 還沒更新前）
    # 就決定好的，如果不強制重新整理，剛篩選完的這一次畫面選單還是會停留在
    # 原本判斷出來的位置（主畫面），要等使用者下一次跟頁面互動才會重新判斷、
    # 跳到側欄。加一次 st.rerun() 讓整個腳本用最新的結果重跑一次，這個判斷才會
    # 立刻用篩選完成後的狀態重新算。
    st.session_state["_collapse_sidebar_next"] = True
    st.rerun()

if screen_result is not None:
    result_universe_label = st.session_state["etf_screen_universe_label"]

    stem = f"{result_universe_label}均線篩選_{screen_result.generated_at.isoformat()}"
    screen_html = render_screen_html(screen_result, universe_label=result_universe_label)

    with st.spinner("正在產生 PDF..."):
        pdf_bytes = render_screen_pdf(screen_result, universe_label=result_universe_label)
    pdf_filename = f"{stem}.pdf"
    pdf_base64 = base64.b64encode(pdf_bytes).decode("ascii")

    # PDF 開啟/分享/下載，以及篩選結果網頁（HTML）下載，都是「產出後的動作」，
    # 不是主畫面要瀏覽的內容本身，所以整組放進側欄（st.sidebar），主畫面只留
    # 下面「網頁預覽」這個真正要滑動瀏覽的表格——原本這些按鈕跟預覽表格擠在
    # 同一欄，PDF 產生完成後按鈕會插進表格中間，擋住原本正在看的內容，移進
    # 側欄後就不會再發生。
    with st.sidebar:
        st.divider()
        st.subheader("PDF 報告")

        # 跟公司基本面分析專案同一套已驗證過的做法：用 Blob URL 而不是
        # data: URI 做「開新分頁瀏覽」，因為 data: URI 拿去做頁面導覽會被
        # 瀏覽器的防釣魚機制擋下（結果是開新分頁後空白）；<a download> 在
        # iPhone Safari 上也常常不會真的觸發下載，而是改用系統層級的 Quick
        # Look 把畫面整個蓋掉，關閉後有時甚至回不去原本頁面。Blob URL +
        # window.open() 兩邊都不會有這些問題。按鈕改成直向堆疊（原本是左右
        # 並排），因為側欄寬度比主畫面窄很多，並排容易被擠到換行。
        components.html(
            f"""
            <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
              display:flex; flex-direction:column; gap:0.5em;">
              <button id="openBtn" style="padding:0.5em 1em; font-size:1em;
                border-radius:8px; border:none; background:#ff4b4b; color:#fff;
                cursor:pointer;">📄 用瀏覽器開啟 PDF</button>
              <button id="shareBtn" style="padding:0.5em 1em; font-size:1em;
                border-radius:8px; border:1px solid rgba(49,51,63,0.2); background:#fff;
                cursor:pointer;">📤 選擇開啟方式（分享）</button>
            </div>
            <div id="actionMsg" style="margin-top:0.4em; font-size:0.85em; color:#666;"></div>
            <script>
            const b64Data = {json.dumps(pdf_base64)};
            const fileName = {json.dumps(pdf_filename)};

            function b64ToBlob(b64, contentType) {{
              const byteChars = atob(b64);
              const byteNumbers = new Array(byteChars.length);
              for (let i = 0; i < byteChars.length; i++) {{
                byteNumbers[i] = byteChars.charCodeAt(i);
              }}
              return new Blob([new Uint8Array(byteNumbers)], {{type: contentType}});
            }}

            const msg = document.getElementById('actionMsg');

            document.getElementById('openBtn').addEventListener('click', () => {{
              msg.innerText = '';
              try {{
                const blob = b64ToBlob(b64Data, 'application/pdf');
                const blobUrl = URL.createObjectURL(blob);
                const opened = window.open(blobUrl, '_blank');
                if (!opened) {{
                  msg.innerText = '瀏覽器擋下了開啟視窗，請改用下方「下載 PDF」按鈕。';
                }}
              }} catch (err) {{
                msg.innerText = '開啟失敗，請改用下方「下載 PDF」按鈕。';
              }}
            }});

            document.getElementById('shareBtn').addEventListener('click', async () => {{
              msg.innerText = '';
              try {{
                const blob = b64ToBlob(b64Data, 'application/pdf');
                const file = new File([blob], fileName, {{type: 'application/pdf'}});
                if (navigator.canShare && navigator.canShare({{files: [file]}})) {{
                  await navigator.share({{files: [file], title: fileName}});
                }} else {{
                  msg.innerText = '此瀏覽器不支援分享功能，請改用「用瀏覽器開啟」或「下載」。';
                }}
              }} catch (err) {{
                if (err && err.name !== 'AbortError') {{
                  msg.innerText = '分享失敗，請改用「用瀏覽器開啟」或「下載」。';
                }}
              }}
            }});
            </script>
            """,
            height=140,
        )

        st.download_button(
            "📥 下載 PDF 到裝置",
            data=pdf_bytes,
            file_name=pdf_filename,
            mime="application/pdf",
            use_container_width=True,
        )
        st.caption(
            "建議先用「用瀏覽器開啟 PDF」查看：會在新分頁用瀏覽器內建的 PDF 檢視器開啟，"
            "裡面本身就有下載／列印功能；也可以用「選擇開啟方式」叫出系統分享選單，"
            "存到「檔案」App 或分享給其他 App（iPhone／PC 皆適用）。"
        )

        st.divider()
        st.subheader("網頁下載")
        st.caption("下載這次篩選結果的網頁版（HTML），可離線開啟、分享。")
        st.download_button(
            "📥 下載此篩選結果網頁（HTML）",
            data=screen_html.encode("utf-8"),
            file_name=f"{stem}.html",
            mime="text/html",
            use_container_width=True,
        )

        # 篩選範圍／資料日期／產生時間／資料來源這行說明額外在側欄「網頁下載」
        # 下方也顯示一次，方便瀏覽時不用捲到表格最下面才看得到；表格本身
        # （screen_page.py 產生的 HTML，含獨立下載的檔案）跟 PDF 也都保留了
        # 自己的版本（緊接在免責聲明上方），因為那是給下載/分享出去的檔案
        # 自己要能單獨看懂內容的必要資訊，兩邊各自獨立顯示，不是同一份文字。
        st.divider()
        _as_of = screen_result.as_of_date
        _as_of_text = _as_of.isoformat() if _as_of else "無可用資料"
        st.caption(
            f"篩選範圍：{result_universe_label}"
            f"（共 {len(screen_result.rows) + len(screen_result.skipped)} 檔）　"
            f"資料日期：{_as_of_text}　"
            f"產生時間：{screen_result.generated_at.isoformat()}　"
            f"資料來源：FinMind（+ 證交所官方備援）"
        )

    # 拿掉「網頁預覽」標題與說明文字：選單、PDF、下載都已經移進側欄，主畫面
    # 現在只剩這張表格本身，不需要額外標題說明「這是預覽」，表格自己就是
    # 篩選器要呈現的內容。
    # 高度不再由 Python 端猜一個固定像素數（不同裝置螢幕高度、字級都不同，猜的
    # 值不是太高留白、就是太矮還要內部捲動）：screen_page.py 內嵌的 JS 會在載入
    # 後用 window.frameElement 把這個 iframe 的高度改成剛好貼合實際內容高度
    # （表格本身仍有自己的 max-height 上限＋內部捲動，所以貼合後的總高度是有界
    # 的，不會因為篩到的檔數暴增而跟著暴增）。這裡的 height 只是 JS 生效前的
    # 起始值，scrolling=False 是因為外層不再需要自己的捲軸。
    components.html(screen_html, height=480, scrolling=False)

    if screen_result.skipped:
        st.caption(f"{len(screen_result.skipped)} 檔查詢失敗，未列入篩選結果（詳見上方內容或下載檔案）。")

# 免責聲明不在這裡重複顯示一次：下方「網頁預覽」的表格（screen_page.py 產生
# 的 HTML）自己的頁尾、以及 PDF 報告內都已經各自帶有這段文字，是真正要交付
# 出去（下載/分享）的內容本身該有的免責聲明；這裡只是選單跟操作介面，重複
# 印一次沒有意義，之前的版本因為兩邊都印才會在同一頁面裡看到重複的文字。

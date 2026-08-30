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

st.set_page_config(page_title="均線篩選器", page_icon="📈")

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

st.title("均線篩選器")
st.caption(
    "跑一次「最近一日收盤價站上或跌破幾條均線（5/10/20/60 日）」的篩選，"
    "依訊號強弱分成八個等級：多頭四級（四海遊龍／三陽開泰／短線翻多訊號／準備短線翻多）、"
    "空頭四級（注意停損／短線翻空／三聲無奈／四面楚歌）。"
)

universe_choice = st.radio("篩選範圍", list(_UNIVERSES.keys()))
universe_label, screen_fn = _UNIVERSES[universe_choice]

if "etf_screen_result" not in st.session_state:
    st.session_state["etf_screen_result"] = None
if "etf_screen_universe_label" not in st.session_state:
    st.session_state["etf_screen_universe_label"] = None

if st.button(f"開始篩選：{universe_label}", type="primary"):
    with st.spinner(f"正在逐檔查詢「{universe_label}」股價並計算均線，請稍候..."):
        st.session_state["etf_screen_result"] = screen_fn()
        st.session_state["etf_screen_universe_label"] = universe_label

screen_result = st.session_state["etf_screen_result"]
if screen_result is not None:
    result_universe_label = st.session_state["etf_screen_universe_label"]
    as_of = screen_result.as_of_date
    st.success(f"「{result_universe_label}」篩選完成，資料日期：{as_of.isoformat() if as_of else '無可用資料'}")

    stem = f"{result_universe_label}均線篩選_{screen_result.generated_at.isoformat()}"

    st.subheader("PDF 報告")
    with st.spinner("正在產生 PDF..."):
        pdf_bytes = render_screen_pdf(screen_result, universe_label=result_universe_label)
    pdf_filename = f"{stem}.pdf"
    pdf_base64 = base64.b64encode(pdf_bytes).decode("ascii")

    # 跟公司基本面分析專案同一套已驗證過的做法：用 Blob URL 而不是 data: URI 做
    # 「開新分頁瀏覽」，因為 data: URI 拿去做頁面導覽會被瀏覽器的防釣魚機制擋下
    # （結果是開新分頁後空白）；<a download> 在 iPhone Safari 上也常常不會真的
    # 觸發下載，而是改用系統層級的 Quick Look 把畫面整個蓋掉，關閉後有時甚至
    # 回不去原本頁面。Blob URL + window.open() 兩邊都不會有這些問題。
    components.html(
        f"""
        <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
          display:flex; gap:0.5em; flex-wrap:wrap;">
          <button id="openBtn" style="flex:1; min-width:140px; padding:0.5em 1em; font-size:1em;
            border-radius:8px; border:none; background:#ff4b4b; color:#fff;
            cursor:pointer;">📄 用瀏覽器開啟 PDF</button>
          <button id="shareBtn" style="flex:1; min-width:140px; padding:0.5em 1em; font-size:1em;
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
        height=90,
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

    st.subheader("網頁預覽")
    st.caption("下方為篩選結果的網頁版內嵌預覽，上方可以用「篩選分類」下拉選單切換要看哪一個等級。")
    screen_html = render_screen_html(screen_result, universe_label=result_universe_label)
    components.html(screen_html, height=850, scrolling=True)

    st.download_button(
        "📥 下載此篩選結果網頁（HTML）",
        data=screen_html.encode("utf-8"),
        file_name=f"{stem}.html",
        mime="text/html",
        use_container_width=True,
    )

    if screen_result.skipped:
        st.caption(f"{len(screen_result.skipped)} 檔查詢失敗，未列入篩選結果（詳見上方內容或下載檔案）。")

st.divider()
st.caption("所有投資相關內容僅供參考，不構成任何投資建議，使用者應自行評估風險。")

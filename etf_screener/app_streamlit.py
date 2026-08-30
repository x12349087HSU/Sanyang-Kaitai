"""Streamlit 網頁介面：對 0050 成分股跑均線篩選。

執行方式：py -m streamlit run etf_screener/app_streamlit.py

密碼保護：部署到公開網路（如 Streamlit Community Cloud）時，在該平台的 Secrets
設定中加入 APP_PASSWORD = "你的密碼"，即會啟用簡易密碼保護；本機開發若未設定
APP_PASSWORD（環境變數或 .streamlit/secrets.toml 皆可），則不會要求輸入密碼。
"""
from __future__ import annotations

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

from etf_screener.ma_screener import TIER_LABELS, TIER_ORDER, screen_0050, screen_top150
from etf_screener.screen_page import render_screen_html

_UNIVERSES = {
    "0050 成分股（約 50 檔，快）": ("0050 成分股", screen_0050),
    "上市市值前 150 大（0050+0051，約 150 檔，較久）": ("上市市值前150大", screen_top150),
}

st.set_page_config(page_title="均線篩選器", page_icon="📈")


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

    tier_cols_bull = st.columns(4)
    for col, tier in zip(tier_cols_bull, TIER_ORDER[:4]):
        col.metric(TIER_LABELS[tier], f"{len(screen_result.rows_by_tier(tier))} 檔")
    tier_cols_bear = st.columns(4)
    for col, tier in zip(tier_cols_bear, TIER_ORDER[4:]):
        col.metric(TIER_LABELS[tier], f"{len(screen_result.rows_by_tier(tier))} 檔")

    screen_html = render_screen_html(screen_result, universe_label=result_universe_label)
    components.html(screen_html, height=1400, scrolling=True)

    st.download_button(
        "📥 下載此篩選結果網頁（HTML）",
        data=screen_html.encode("utf-8"),
        file_name=f"{result_universe_label}均線篩選_{screen_result.generated_at.isoformat()}.html",
        mime="text/html",
        use_container_width=True,
    )

    if screen_result.skipped:
        st.caption(f"{len(screen_result.skipped)} 檔查詢失敗，未列入篩選結果（詳見上方網頁內容或下載檔案）。")

st.divider()
st.caption("所有投資相關內容僅供參考，不構成任何投資建議，使用者應自行評估風險。")

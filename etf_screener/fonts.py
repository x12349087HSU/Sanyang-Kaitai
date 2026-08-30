"""CJK 字型偵測與 ReportLab 註冊。

優先使用本機 Windows 內建「微軟正黑體」；找不到的環境（例如雲端 Linux 主機）
則退回專案內建的 Noto Sans TC 字型檔，確保本機開發與雲端部署（如 Streamlit
Community Cloud）都能正常顯示中文，不會因平台不同而產出亂碼/方框 PDF。
"""
from __future__ import annotations

from pathlib import Path

from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

FONT_NAME_REGULAR = "ScreenerCJK"
FONT_NAME_BOLD = "ScreenerCJK-Bold"

_BUNDLED_FONT = str(Path(__file__).resolve().parent / "assets" / "fonts" / "NotoSansTC-Regular.ttf")

_CANDIDATE_FONTS = [
    # (regular, bold, subfont_index)
    (r"C:\Windows\Fonts\msjh.ttc", r"C:\Windows\Fonts\msjhbd.ttc", 0),
    (r"C:\Windows\Fonts\mingliu.ttc", r"C:\Windows\Fonts\mingliu.ttc", 0),
    (r"C:\Windows\Fonts\kaiu.ttf", r"C:\Windows\Fonts\kaiu.ttf", None),
    # 跨平台備援：專案內建字型（Noto Sans TC，OFL 授權，隨程式一起部署）
    (_BUNDLED_FONT, _BUNDLED_FONT, None),
]

_registered = False


class NoCjkFontFoundError(Exception):
    pass


def register_cjk_fonts() -> tuple[str, str]:
    """向 ReportLab 註冊中文字型，回傳 (regular_name, bold_name)。找不到任何候選字型會拋出例外。"""
    global _registered
    if _registered:
        return FONT_NAME_REGULAR, FONT_NAME_BOLD

    for regular, bold, subfont_index in _CANDIDATE_FONTS:
        if not Path(regular).exists():
            continue
        try:
            if subfont_index is not None:
                pdfmetrics.registerFont(TTFont(FONT_NAME_REGULAR, regular, subfontIndex=subfont_index))
            else:
                pdfmetrics.registerFont(TTFont(FONT_NAME_REGULAR, regular))
            if Path(bold).exists() and bold != regular:
                pdfmetrics.registerFont(TTFont(FONT_NAME_BOLD, bold, subfontIndex=subfont_index or 0))
            else:
                # 沒有獨立粗體檔就用同一份字型頂替，仍可正常顯示（只是不會真的變粗）
                pdfmetrics.registerFont(TTFont(FONT_NAME_BOLD, regular, subfontIndex=subfont_index or 0))
            _registered = True
            return FONT_NAME_REGULAR, FONT_NAME_BOLD
        except Exception:
            continue

    raise NoCjkFontFoundError(
        "找不到可用的中文字型（已嘗試微軟正黑體/細明體/標楷體，以及專案內建的 Noto Sans TC）。"
        "請確認字型檔是否存在於 etf_screener/assets/fonts/ 目錄下。"
    )

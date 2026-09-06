"""把基本面摘要（etf_screener/api.py 的 GET /fundamentals/{stock_id} 回傳的
dict）組成一份 PDF，**即時產生、不預先產生也不儲存**。

這份摘要資料本身已經是排程預抓、從 GitHub 讀來的現成資料（見
scripts/prefetch_fundamentals.py），組成 PDF 這一步純粹是本地排版，不需要
再打任何外部資料源（FinMind/證交所），現場組一份的成本很低（不用等外部
API 回應）。這是刻意的取捨：如果改成比照均線篩選 PDF「每天排程幫 150 檔
都預先產生好」，實測光是中文字型嵌入的固定成本每份就要 100KB+（150 檔
會膨脹到 17MB+，而且大部分是重複的字型資料），即時產生換來零額外儲存
空間，代價只是使用者下載當下要等 Render 花 1-2 秒現場組版。
"""
from __future__ import annotations

import io

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, StyleSheet1
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

from .fonts import register_cjk_fonts

_ICON = {True: "✓", False: "✗", None: "？"}


def _build_stylesheet() -> tuple[StyleSheet1, str, str]:
    regular, bold = register_cjk_fonts()
    styles = StyleSheet1()
    styles.add(ParagraphStyle("Title", fontName=bold, fontSize=16, leading=22, spaceAfter=4))
    styles.add(ParagraphStyle(
        "Meta", fontName=regular, fontSize=9, leading=13,
        textColor=colors.HexColor("#666666"), spaceAfter=10,
    ))
    styles.add(ParagraphStyle(
        "H2", fontName=bold, fontSize=11, leading=15,
        textColor=colors.HexColor("#7a1414"), spaceBefore=8, spaceAfter=4,
    ))
    styles.add(ParagraphStyle("Body", fontName=regular, fontSize=9.5, leading=14, spaceAfter=6))
    styles.add(ParagraphStyle(
        "Detail", fontName=regular, fontSize=8, leading=11.5,
        textColor=colors.HexColor("#777777"), spaceAfter=4,
    ))
    styles.add(ParagraphStyle(
        "Footer", fontName=regular, fontSize=7.5, leading=11,
        textColor=colors.HexColor("#888888"),
    ))
    return styles, regular, bold


def render_fundamentals_pdf(summary: dict) -> bytes:
    styles, _regular, _bold = _build_stylesheet()
    story = []
    story.append(Paragraph(
        f"{summary['company_name']}（{summary['stock_id']}）基本面摘要", styles["Title"]
    ))
    story.append(Paragraph(
        f"產業：{summary.get('industry_name') or '未知產業'}　"
        f"資料日期：{summary.get('generated_at', '')}",
        styles["Meta"],
    ))

    story.append(Paragraph("營收趨勢", styles["H2"]))
    story.append(Paragraph(summary.get("revenue_summary_text") or "查無月營收資料。", styles["Body"]))

    story.append(Paragraph("EPS 趨勢", styles["H2"]))
    story.append(Paragraph(summary.get("eps_summary_text") or "查無 EPS 資料。", styles["Body"]))

    story.append(Paragraph("基本面自檢表", styles["H2"]))
    checklist_items = summary.get("checklist_items") or []
    if not checklist_items:
        story.append(Paragraph("無自檢表資料。", styles["Body"]))
    last_tier = None
    for item in checklist_items:
        if item["tier"] != last_tier:
            story.append(Paragraph(item["tier_name"], styles["Meta"]))
            last_tier = item["tier"]
        story.append(Paragraph(f"{_ICON[item['passed']]} {item['name']}", styles["Body"]))
        story.append(Paragraph(item["detail"], styles["Detail"]))

    story.append(Paragraph("目標價／評等", styles["H2"]))
    ratings = summary.get("ratings") or []
    if not ratings:
        story.append(Paragraph("查無一致公開資料，僅整理公開可得資訊。", styles["Body"]))
    else:
        for r in ratings:
            parts = [p for p in (r.get("institution"), r.get("rating")) if p]
            if r.get("target_price") is not None:
                parts.append(f"目標價 {r['target_price']} 元")
            story.append(Paragraph("・".join(parts) or "（無法辨識評等內容）", styles["Body"]))
            story.append(Paragraph(r.get("source_title") or "", styles["Detail"]))

    story.append(Spacer(1, 8))
    story.append(Paragraph(
        "所有投資相關內容僅供參考，不構成任何投資建議，使用者應自行評估風險。",
        styles["Footer"],
    ))

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=1.6 * cm, rightMargin=1.6 * cm, topMargin=1.4 * cm, bottomMargin=1.4 * cm,
        title=f"{summary['company_name']}基本面摘要",
    )
    doc.build(story)
    return buf.getvalue()

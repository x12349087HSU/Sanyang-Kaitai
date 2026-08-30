"""把均線篩選結果組成一份 PDF 報告（ReportLab Platypus）。

跟 screen_page.py（HTML 網頁版）呈現同樣的內容，只是輸出格式不同：HTML 版適合
在網頁上直接瀏覽，PDF 版適合下載、分享、列印保存。
"""
from __future__ import annotations

import io

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, StyleSheet1
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from . import config
from .fonts import register_cjk_fonts
from .ma_screener import TIER_DESCRIPTIONS, TIER_LABELS, TIER_ORDER, MaScreenResult

_TIER_COLOR = {
    4: colors.HexColor("#7a1414"),
    3: colors.HexColor("#b5321b"),
    2: colors.HexColor("#d6672c"),
    1: colors.HexColor("#e2a13a"),
    -1: colors.HexColor("#8fae6e"),
    -2: colors.HexColor("#6f9650"),
    -3: colors.HexColor("#4f7a37"),
    -4: colors.HexColor("#2f5a1f"),
}

_COL_WIDTHS = [1.7 * cm, 2.8 * cm, 2.0 * cm, 2.0 * cm, 2.0 * cm, 2.0 * cm, 2.0 * cm, 2.3 * cm]


def _build_stylesheet() -> tuple[StyleSheet1, str, str]:
    regular, bold = register_cjk_fonts()
    styles = StyleSheet1()
    styles.add(ParagraphStyle(
        "Title", fontName=bold, fontSize=18, leading=24,
        textColor=colors.HexColor("#1a1a1a"), spaceAfter=4,
    ))
    styles.add(ParagraphStyle(
        "Meta", fontName=regular, fontSize=9, leading=13,
        textColor=colors.HexColor("#666666"), spaceAfter=14,
    ))
    styles.add(ParagraphStyle(
        "TierHeading", fontName=bold, fontSize=12, leading=16,
        textColor=colors.white, spaceBefore=10, spaceAfter=8, borderPadding=6,
    ))
    styles.add(ParagraphStyle(
        "TierDesc", fontName=regular, fontSize=8.5, leading=12,
        textColor=colors.HexColor("#555555"), spaceAfter=6,
    ))
    styles.add(ParagraphStyle(
        "Empty", fontName=regular, fontSize=9, leading=13,
        textColor=colors.HexColor("#888888"), spaceAfter=10,
    ))
    styles.add(ParagraphStyle(
        "Footer", fontName=regular, fontSize=7.5, leading=11.5,
        textColor=colors.HexColor("#888888"),
    ))
    return styles, regular, bold


def _tier_table(rows: list, regular: str) -> Table:
    header = ["代號", "名稱", "收盤價", "5MA", "10MA", "20MA", "60MA", "資料日期"]
    data = [header]
    for r in rows:
        data.append([
            r.stock_id,
            r.company_name,
            f"{r.close:,.2f}",
            f"{r.ma5:,.2f}" if r.ma5 is not None else "—",
            f"{r.ma10:,.2f}" if r.ma10 is not None else "—",
            f"{r.ma20:,.2f}" if r.ma20 is not None else "—",
            f"{r.ma60:,.2f}" if r.ma60 is not None else "—",
            r.trade_date.isoformat(),
        ])
    table = Table(data, repeatRows=1, colWidths=_COL_WIDTHS)
    table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), regular),
        ("FONTSIZE", (0, 0), (-1, -1), 7.5),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2a2a2a")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f7f5f2")]),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#dddddd")),
        ("ALIGN", (2, 0), (-1, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    return table


def render_screen_pdf(result: MaScreenResult, *, universe_label: str = "0050 成分股") -> bytes:
    styles, regular, _bold = _build_stylesheet()
    as_of = result.as_of_date
    as_of_text = as_of.isoformat() if as_of else "無可用資料"

    story = [
        Paragraph(f"{universe_label}均線篩選", styles["Title"]),
        Paragraph(
            f"篩選範圍：{universe_label}（共 {len(result.rows) + len(result.skipped)} 檔）　"
            f"資料日期：{as_of_text}　產生時間：{result.generated_at.isoformat()}　"
            f"資料來源：FinMind（+ 證交所官方備援）",
            styles["Meta"],
        ),
    ]

    for tier in TIER_ORDER:
        rows = result.rows_by_tier(tier)
        heading_style = ParagraphStyle(
            f"TierHeading{tier}", parent=styles["TierHeading"], backColor=_TIER_COLOR[tier],
        )
        story.append(Paragraph(f"{TIER_LABELS[tier]}（{len(rows)} 檔）", heading_style))
        story.append(Paragraph(TIER_DESCRIPTIONS[tier], styles["TierDesc"]))
        if rows:
            story.append(_tier_table(rows, regular))
        else:
            story.append(Paragraph("本次篩選查無符合條件的個股。", styles["Empty"]))
        story.append(Spacer(1, 6))

    if result.skipped:
        story.append(Paragraph(f"{len(result.skipped)} 檔查詢失敗，未列入篩選結果：", styles["TierDesc"]))
        skip_text = "；".join(f"{sid} {name}（{reason}）" for sid, name, reason in result.skipped)
        story.append(Paragraph(skip_text, styles["Footer"]))
        story.append(Spacer(1, 6))

    story.append(Spacer(1, 8))
    story.append(Paragraph(
        "均線分級為巢狀判定：多頭與空頭各四級，例如「三陽開泰」代表同時站上 "
        "5MA/10MA/20MA，不代表站上或跌破 60MA——若也站上 60MA，會被歸類到更高一級的 "
        "「四海遊龍」；空頭四級是鏡像邏輯，條件改成「跌破」對應數量的均線。多空訊號 "
        "不一致（例如站上 5MA 但跌破 10MA）的股票不列入這八個等級。5MA/10MA/20MA/60MA "
        "皆為收盤價簡單移動平均（SMA），非官方統一標準。<br/>" + config.DISCLAIMER_TEXT,
        styles["Footer"],
    ))

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=1.6 * cm,
        rightMargin=1.6 * cm,
        topMargin=1.4 * cm,
        bottomMargin=1.4 * cm,
        title=f"{universe_label}均線篩選",
    )
    doc.build(story)
    return buf.getvalue()

"""把均線篩選結果組成一頁獨立、自成一體（沒有外部依賴）的 HTML 網頁。

呈現方式是單一張表格（分類／代號／名稱／收盤價／資料日期），每個欄位的
表頭都有一個類似 Excel 表單「自動篩選」的下拉選單（可勾選要顯示哪些值、
可在清單裡搜尋），各欄位篩選彼此獨立、可以疊加使用。要加新的可篩選欄位，
在 `_COLUMNS` 加一筆定義、在 `_row_attrs()` 補對應的 data-* 屬性即可，
JS 端的篩選邏輯是資料驅動、不用每加一欄就多寫一段程式。
"""
from __future__ import annotations

import html as html_lib
import json

from . import config
from .ma_screener import TIER_DESCRIPTIONS, TIER_LABELS, TIER_ORDER, MaScreenResult

# 多頭用紅色（台股慣例紅漲），空頭用綠色（台股慣例綠跌）；數值絕對值愈大
# （站上/跌破愈多條均線，訊號愈強）顏色愈深。
_TIER_ACCENT = {
    4: "#7a1414",
    3: "#b5321b",
    2: "#d6672c",
    1: "#e2a13a",
    -1: "#8fae6e",
    -2: "#6f9650",
    -3: "#4f7a37",
    -4: "#2f5a1f",
}

# (欄位 key, 表頭文字)。key 要跟 _row_attrs() 回傳的 dict key 一致，且必須是
# 純小寫（加連字號沒關係），因為會直接拿去組 data-{key} 屬性名稱。
_COLUMNS = [
    ("tier", "訊號"),
    ("stock-id", "代號"),
    ("name", "名稱"),
    ("close", "收盤價"),
    ("date", "資料日期"),
]


def _fmt_price(value: float | None) -> str:
    return f"{value:,.2f}" if value is not None else "—"


def _row_attrs(tier: int, r) -> dict[str, str]:
    """回傳這一列在每個可篩選欄位上的「篩選用字串值」，同時也是儲存格顯示文字
    （分類跟收盤價會另外包一層顯示用的 HTML，但篩選比對用的還是這裡的原始字串）。"""
    return {
        "tier": TIER_LABELS[tier],
        "stock-id": r.stock_id,
        "name": r.company_name,
        "close": _fmt_price(r.close),
        "date": r.trade_date.isoformat(),
    }


def _unique_options(col: str, ordered_rows: list[tuple[int, object]]) -> list[str]:
    """依照有意義的順序（分類依多頭到空頭、收盤價由小到大、日期由舊到新，
    其餘照出現順序）取得某欄位的所有不重複篩選值，給表頭的核取方塊清單用。"""
    if col == "tier":
        seen_tiers = {tier for tier, _ in ordered_rows}
        return [TIER_LABELS[t] for t in TIER_ORDER if t in seen_tiers]

    seen: list[str] = []
    seen_set: set[str] = set()
    for tier, r in ordered_rows:
        value = _row_attrs(tier, r)[col]
        if value not in seen_set:
            seen_set.add(value)
            seen.append(value)
    if col == "close":
        return sorted(seen, key=lambda v: float(v.replace(",", "")))
    if col in ("date", "stock-id"):
        return sorted(seen)
    return seen


def _table_header_html(ordered_rows: list[tuple[int, object]]) -> str:
    ths = []
    for col, label in _COLUMNS:
        options = _unique_options(col, ordered_rows)
        option_items = "\n".join(
            f'<label><input type="checkbox" value="{html_lib.escape(v)}" checked> '
            f'{html_lib.escape(v)}</label>'
            for v in options
        )
        ths.append(f"""<th data-col="{col}">
          <div class="th-head">
            <span>{label}</span>
            <button type="button" class="filter-btn" data-col="{col}" aria-label="篩選 {label}">▾</button>
          </div>
          <div class="filter-panel" data-col="{col}" hidden>
            <input type="text" class="filter-search" placeholder="搜尋..." />
            <div class="filter-actions">
              <button type="button" class="select-all-btn">全選</button>
              <button type="button" class="select-none-btn">全部不選</button>
            </div>
            <div class="filter-options">{option_items}</div>
          </div>
        </th>""")
    return "<tr>" + "".join(ths) + "</tr>"


def _table_body_html(ordered_rows: list[tuple[int, object]]) -> str:
    if not ordered_rows:
        return '<tr><td colspan="5" class="empty">本次篩選查無符合條件的個股。</td></tr>'
    rows_html = []
    for tier, r in ordered_rows:
        attrs = _row_attrs(tier, r)
        data_attrs = " ".join(f'data-{k}="{html_lib.escape(v)}"' for k, v in attrs.items())
        rows_html.append(f"""<tr {data_attrs}>
          <td><span class="tier-badge" style="--accent:{_TIER_ACCENT[tier]}">{attrs['tier']}</span></td>
          <td>{html_lib.escape(attrs['stock-id'])}</td>
          <td>{html_lib.escape(attrs['name'])}</td>
          <td class="num"><button type="button" class="price-link"
            data-stock-id="{html_lib.escape(r.stock_id)}"
            data-name="{html_lib.escape(r.company_name)}">{html_lib.escape(attrs['close'])}</button></td>
          <td>{attrs['date']}</td>
        </tr>""")
    rows_html.append('<tr class="no-match-row" hidden><td colspan="5">篩選條件無符合的個股</td></tr>')
    return "\n".join(rows_html)


def _legend_html() -> str:
    items = "\n".join(
        f'<li><span class="tier-badge" style="--accent:{_TIER_ACCENT[tier]}">{TIER_LABELS[tier]}</span>'
        f"　{TIER_DESCRIPTIONS[tier]}</li>"
        for tier in TIER_ORDER
    )
    return f"""
    <details class="legend">
      <summary>訊號意義</summary>
      <ul>{items}</ul>
    </details>"""


def _skipped_html(skipped: list[tuple[str, str, str]]) -> str:
    if not skipped:
        return ""
    items = "\n".join(
        f"<li>{html_lib.escape(sid)} {html_lib.escape(name)}：{html_lib.escape(reason)}</li>"
        for sid, name, reason in skipped
    )
    return f"""
    <details class="skipped">
      <summary>{len(skipped)} 檔成分股查詢失敗，未列入篩選結果（點擊展開查看原因）</summary>
      <ul>{items}</ul>
    </details>"""


def render_screen_html(result: MaScreenResult, *, universe_label: str = "0050 成分股") -> str:
    title = f"{universe_label}均線篩選"

    ordered_rows: list[tuple[int, object]] = [
        (tier, r) for tier in TIER_ORDER for r in result.rows_by_tier(tier)
    ]
    col_keys = [col for col, _ in _COLUMNS]

    def _round_series(values: list[float | None]) -> list[float | None]:
        return [None if v is None else round(v, 2) for v in values]

    # 給「點收盤價看技術分析圖表」用的每日序列，只需要涵蓋目前有列在表格裡的
    # 股票（tier=0、多空訊號不一致的已經被 ordered_rows 排除掉了）。用
    # separators=(",", ":") 去掉多餘空白，這份資料量隨股票池變大（0050+0051
    # 約 150 檔 × 每檔 6 個月序列）還是要盡量精簡，畢竟整份 HTML 是要內嵌進
    # Streamlit 的 iframe、也是使用者會下載的獨立檔案。
    price_history = {
        r.stock_id: {
            "dates": [d.isoformat() for d in r.history_dates],
            "close": _round_series(r.history_close),
            "open": _round_series(r.history_open),
            "high": _round_series(r.history_high),
            "low": _round_series(r.history_low),
            "ma5": _round_series(r.history_ma5),
            "ma10": _round_series(r.history_ma10),
            "ma20": _round_series(r.history_ma20),
            "ma60": _round_series(r.history_ma60),
            "k": _round_series(r.history_k),
            "d": _round_series(r.history_d),
        }
        for _tier, r in ordered_rows
    }
    price_history_json = json.dumps(price_history, separators=(",", ":"))

    return f"""<!doctype html>
<html lang="zh-Hant">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>{html_lib.escape(title)}</title>
<style>
  :root {{ color-scheme: light; }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0; padding: 1.5rem; background: #f7f5f2; color: #1a1a1a;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Noto Sans TC", "Microsoft JhengHei", sans-serif;
  }}
  /* 這個按鈕移到表格下方之後改成置中顯示：details.legend 本身是區塊元素，
     summary 是 inline-flex（行內層級的盒子），對容器套 text-align:center
     就能讓 summary 這顆按鈕整個置中；展開後的 <ul> 說明清單則另外蓋回
     text-align:left，維持清單內文左對齊、只有按鈕本身置中。 */
  details.legend {{ margin: 1.4rem 0 0; text-align: center; }}
  details.legend summary {{
    cursor: pointer; list-style: none; user-select: none;
    display: inline-flex; align-items: center; gap: 0.5rem;
    font-size: 1rem; font-weight: 700; color: #1a1a1a;
    background: #fff; padding: 0.65rem 1.2rem; border-radius: 999px;
    box-shadow: 0 1px 4px rgba(0,0,0,0.12);
  }}
  details.legend summary::-webkit-details-marker {{ display: none; }}
  details.legend summary:hover {{ background: #f0eeea; }}
  details.legend summary::after {{
    content: '▾'; font-size: 0.85rem; color: #888; transition: transform 0.15s ease;
  }}
  details.legend[open] summary::after {{ transform: rotate(180deg); }}
  details.legend ul {{
    text-align: left;
    font-size: 0.85rem; color: #555; line-height: 1.9; margin: 0.6rem 0 0;
    background: #fff; border-radius: 10px; padding: 0.9rem 1rem 0.9rem 2.2rem;
    box-shadow: 0 1px 3px rgba(0,0,0,0.06);
  }}
  .tier-badge {{
    display: inline-block; padding: 0.1rem 0.5rem; border-radius: 999px;
    font-size: 0.78rem; font-weight: 700; color: #fff; background: var(--accent);
    white-space: nowrap;
  }}
  .table-wrap {{
    background: #fff; border-radius: 10px; box-shadow: 0 1px 3px rgba(0,0,0,0.06);
    overflow: auto; max-height: var(--table-max-h, 65vh);
  }}
  table {{ width: 100%; border-collapse: collapse; font-size: 0.85rem; }}
  thead {{ position: sticky; top: 0; z-index: 2; background: #2a2a2a; }}
  th {{
    text-align: left; padding: 0; border-bottom: 1px solid #444; color: #fff;
    position: relative; vertical-align: top;
  }}
  .th-head {{
    display: flex; align-items: center; justify-content: space-between; gap: 0.4rem;
    padding: 0.5rem 0.6rem; white-space: nowrap;
  }}
  .filter-btn {{
    background: none; border: none; color: #fff; cursor: pointer; font-size: 0.85rem;
    padding: 0 0.2rem; line-height: 1;
  }}
  .filter-btn.active {{ color: #ffd479; }}
  .filter-panel {{
    /* position: fixed（不是 absolute）+ JS 動態算 top/left，這樣面板永遠是相對
       瀏覽器視窗定位，不會被 .table-wrap 的 overflow:auto 裁切——之前的版本用
       absolute 定位在 <th> 底下，當篩選結果變少、.table-wrap 高度跟著縮小時，
       面板就會被裁掉一部分，看起來像「視窗過小看不到選項」。 */
    position: fixed; z-index: 50; width: 14rem;
    background: #fff; color: #1a1a1a; border: 1px solid #ccc; border-radius: 8px;
    box-shadow: 0 4px 12px rgba(0,0,0,0.18); padding: 0.5rem; font-weight: normal;
  }}
  .filter-search {{
    width: 100%; font-size: 0.85rem; padding: 0.3rem 0.5rem; margin-bottom: 0.4rem;
    border: 1px solid #ccc; border-radius: 5px;
  }}
  .filter-actions {{
    display: flex; gap: 0.5rem; padding-bottom: 0.4rem; margin-bottom: 0.4rem;
    border-bottom: 1px solid #eee;
  }}
  .filter-actions button {{
    flex: 1; font-size: 0.78rem; padding: 0.25rem 0.4rem; border-radius: 5px;
    border: 1px solid #ccc; background: #f5f5f5; color: #444; cursor: pointer;
  }}
  .filter-options {{ max-height: 12rem; overflow-y: auto; }}
  .filter-options label {{
    display: block; font-size: 0.82rem; padding: 0.15rem 0; white-space: nowrap;
    overflow: hidden; text-overflow: ellipsis;
  }}
  /* 這條規則的優先權要蓋過上面那條 .filter-options label 的 display:block，
     不然搜尋框把不符合的 label 設成 hidden 時，畫面上其實不會真的消失
     （被上面那條規則的 display:block 蓋掉了），看起來就像搜尋沒有生效。 */
  .filter-options label[hidden] {{ display: none; }}
  td {{ padding: 0.4rem 0.6rem; border-bottom: 1px solid #eee; white-space: nowrap; }}
  td.num {{ text-align: right; }}
  tbody tr:hover {{ background: #faf8f5; }}
  td.empty {{ color: #888; text-align: center; white-space: normal; }}
  tr.no-match-row td {{ color: #888; text-align: center; white-space: normal; }}
  details.skipped {{ font-size: 0.8rem; color: #777; margin-top: 1rem; }}
  footer {{ margin-top: 1.2rem; font-size: 0.78rem; color: #888; line-height: 1.7; text-align: center; }}
  /* 收盤價點下去可以看技術分析圖表，用 <button> 而不是 <span> 是為了保留
     鍵盤可操作性（跟篩選面板的按鈕一致），這裡把 button 預設外觀重置掉，
     讓它看起來像表格裡的一個可點的連結文字。 */
  .price-link {{
    cursor: pointer; color: #1a54c4; text-decoration: underline dotted;
    text-underline-offset: 2px; background: none; border: none; padding: 0;
    font: inherit; font-size: inherit;
  }}
  .price-link:hover {{ color: #0d3a91; }}
  .chart-view {{
    background: #fff; border-radius: 10px; box-shadow: 0 1px 3px rgba(0,0,0,0.06);
    padding: 0.9rem;
  }}
  .chart-header {{
    display: flex; align-items: center; justify-content: space-between;
    flex-wrap: wrap; gap: 0.5rem; margin-bottom: 0.6rem;
  }}
  .chart-back-btn {{
    cursor: pointer; border: none; border-radius: 8px; padding: 0.5rem 1rem;
    font-size: 0.9rem; font-weight: 700; background: #7a1414; color: #fff;
  }}
  .chart-back-btn:hover {{ background: #9a1c1c; }}
  .chart-title {{ font-weight: 700; font-size: 1.05rem; }}
  .chart-reset-btn {{
    cursor: pointer; border: 1px solid #ccc; border-radius: 999px; padding: 0.3rem 0.8rem;
    font-size: 0.78rem; background: #fff; color: #555;
  }}
  .chart-reset-btn:hover {{ background: #f0eeea; }}
  .chart-mode-btn {{
    cursor: pointer; border: 1px solid #7a1414; border-radius: 999px; padding: 0.3rem 0.8rem;
    font-size: 0.78rem; background: #fff; color: #7a1414;
  }}
  .chart-mode-btn:hover {{ background: #fbeaea; }}
  /* KD 指標畫在價格圖下方一個較矮的子圖，兩者共用同一個 x 軸（日期），
     用 flex 直向排列、價格圖分到的高度權重是 KD 圖的 3 倍，兩者加總維持
     跟原本單一價格圖同樣的總高度（var(--table-max-h)），不會讓整個圖表區
     突然變得比之前高出一大截。 */
  .chart-canvas-wrap {{
    display: flex; flex-direction: column; gap: 0.5rem;
    width: 100%; height: var(--table-max-h, 60vh);
  }}
  .price-canvas {{ display: block; width: 100%; flex: 3 1 0; min-height: 0; touch-action: none; }}
  .kd-canvas {{
    display: block; width: 100%; flex: 1 1 0; min-height: 70px; touch-action: none;
    border-top: 1px solid #eee;
  }}
  /* K、D 兩條線都關掉時，乾脆把 KD 子圖整塊藏起來、讓價格圖長高補滿，
     不要留一塊空空的灰底畫布在那裡。 */
  .chart-canvas-wrap.kd-hidden .kd-canvas {{ display: none; }}
  .chart-canvas-wrap.kd-hidden .price-canvas {{ flex: 1 1 0; }}
  .chart-info {{
    margin-top: 0.5rem; font-size: 0.82rem; color: #555; text-align: center;
    min-height: 1.2em;
  }}
  .chart-legend {{
    display: flex; flex-wrap: wrap; gap: 0.7rem; font-size: 0.78rem; color: #555;
    margin-top: 0.4rem; justify-content: center;
  }}
  /* 圖例本身改成可以點的按鈕，點一下切換該條線顯示/隱藏；用 opacity 降低
     + 加刪除線表示「目前關閉」，不是單純拿掉顏色說明，避免看起來像是壞掉。 */
  .legend-item {{
    cursor: pointer; border: none; background: none; padding: 0.15rem 0.35rem;
    border-radius: 999px; font: inherit; font-size: inherit; color: #555;
  }}
  .legend-item:hover {{ background: #f0eeea; }}
  .legend-item.off {{ opacity: 0.4; text-decoration: line-through; }}
  /* 「KD 全部」是一次關掉/開啟 K、D 兩條線的捷徑按鈕，跟個別的 K／D
     開關是兩件事，用邊框跟粗體字區隔開，不要跟一般圖例長得一模一樣、
     讓人誤以為它也是某一條「顏色是這樣」的線。 */
  .legend-kd-toggle {{ border: 1px solid #ccc; font-weight: 700; }}
  .legend-kd-toggle.off {{ border-color: #ddd; }}
  .legend-note {{ color: #555; }}
  .chart-legend .swatch {{
    display: inline-block; width: 0.8rem; height: 0.2rem; margin-right: 0.3rem;
    vertical-align: middle;
  }}
  @media (max-width: 480px) {{
    /* 手機窄螢幕：body 保留一點點留白（0.4rem），讓「訊號意義」跟免責聲明
       這類純文字內容不會整個貼死螢幕邊緣、不好讀；但表格本身用負邊界
       「跳出」body 的留白，兩側直接貼齊螢幕邊緣，拿掉圓角/陰影的卡片感，
       這樣真正吃到滿版的是使用者最主要在看的表格資料，而不是連文字說明
       都硬貼邊緣、反而不好讀。 */
    body {{ padding: 0.5rem 0.4rem; }}
    .table-wrap, .chart-view {{
      border-radius: 0; box-shadow: none;
      margin-left: -0.4rem; margin-right: -0.4rem;
      width: calc(100% + 0.8rem);
    }}
    table {{ font-size: 0.78rem; }}
    td {{ padding: 0.3rem 0.4rem; }}
  }}
</style>
</head>
<body>
  <div id="tableView">
    <div class="table-wrap">
      <table id="dataTable">
        <thead>
          {_table_header_html(ordered_rows)}
        </thead>
        <tbody>
          {_table_body_html(ordered_rows)}
        </tbody>
      </table>
    </div>
    {_skipped_html(result.skipped)}
    {_legend_html()}
    <footer>
      {html_lib.escape(config.DISCLAIMER_TEXT)}
    </footer>
  </div>
  <div id="chartView" class="chart-view" hidden>
    <div class="chart-header">
      <button type="button" class="chart-back-btn">← 返回篩選結果</button>
      <span class="chart-title" id="chartStockLabel"></span>
      <button type="button" class="chart-mode-btn" id="chartModeBtn">查價模式：多點</button>
      <button type="button" class="chart-reset-btn" id="chartJumpLatestBtn" hidden>回到最新</button>
      <button type="button" class="chart-reset-btn" id="chartResetBtn" hidden>顯示全部區間</button>
    </div>
    <div class="chart-canvas-wrap">
      <canvas id="priceChart" class="price-canvas"></canvas>
      <canvas id="kdChart" class="kd-canvas"></canvas>
    </div>
    <div class="chart-info" id="chartInfo"></div>
    <div class="chart-legend" id="chartLegend">
      <span class="legend-note"><span class="swatch" style="background:#c0392b"></span>收盤（漲）
        <span class="swatch" style="background:#1e8449"></span>收盤（跌）</span>
      <button type="button" class="legend-item" data-series="ma5"><span class="swatch" style="background:#e2a13a"></span>5MA</button>
      <button type="button" class="legend-item" data-series="ma10"><span class="swatch" style="background:#d6672c"></span>10MA</button>
      <button type="button" class="legend-item" data-series="ma20"><span class="swatch" style="background:#b5321b"></span>20MA</button>
      <button type="button" class="legend-item" data-series="ma60"><span class="swatch" style="background:#4f7a37"></span>60MA</button>
      <button type="button" class="legend-item" data-series="k"><span class="swatch" style="background:#1a54c4"></span>K</button>
      <button type="button" class="legend-item" data-series="d"><span class="swatch" style="background:#c4471a"></span>D</button>
      <button type="button" class="legend-item legend-kd-toggle" id="kdGroupToggle">KD 全部</button>
    </div>
    <p style="font-size:0.75rem; color:#999; text-align:center; margin-top:0.6rem;">
      K 棒紅漲綠跌；點下方圖例可以開關該條線／整組 KD；拖曳／滑動可查看
      該日各數值；兩指縮放（手機）或滾輪（滑鼠）可以放大/縮小時間區間，
      非投資建議。
    </p>
  </div>
  <script>
    // 每個欄位維護一組「目前勾選中的值」集合，加上一個「目前搜尋框內容」
    // 字串；一列要顯示，該欄位的值必須同時（1）在勾選集合裡、（2）符合該
    // 欄位目前的搜尋字（沒有輸入搜尋字就不做這項限制），每個欄位都要通過
    // 才算通過（等同 Excel 自動篩選：欄位之間是 AND，同一欄位內的多個勾選值
    // 之間是 OR）。搜尋框原本只會縮小面板裡的核取方塊清單、沒有連動套用到
    // 表格本身，是先前回報「搜尋生效但表格沒反應」的原因；這裡把 searchQuery
    // 一起納入判斷，並在輸入時呼叫 applyFilters() 修正。要加新的可篩選欄位，
    // 只要 Python 端在 _COLUMNS 加一筆、_row_attrs() 補對應 data-* 屬性，這裡的
    // 邏輯完全不用改（COLS 是從 Python 端序列化過來的，資料驅動）。
    var COLS = {json.dumps(col_keys)};
    var PRICE_HISTORY = {price_history_json};
    var selected = {{}};
    var searchQuery = {{}};
    COLS.forEach(function (col) {{
      var values = [];
      document.querySelectorAll('.filter-panel[data-col="' + col + '"] .filter-options input[type=checkbox]')
        .forEach(function (cb) {{ values.push(cb.value); }});
      selected[col] = new Set(values);
      searchQuery[col] = '';
    }});

    function applyFilters() {{
      var rows = document.querySelectorAll('#dataTable tbody tr[data-tier]');
      var visibleCount = 0;
      rows.forEach(function (row) {{
        var match = COLS.every(function (col) {{
          var value = row.getAttribute('data-' + col);
          if (!selected[col].has(value)) return false;
          var q = searchQuery[col];
          if (q && value.toLowerCase().indexOf(q) === -1) return false;
          return true;
        }});
        row.hidden = !match;
        if (match) visibleCount++;
      }});
      var noMatchRow = document.querySelector('.no-match-row');
      if (noMatchRow) noMatchRow.hidden = visibleCount > 0;
    }}

    function closeAllPanels(except) {{
      document.querySelectorAll('.filter-panel').forEach(function (panel) {{
        if (panel !== except) panel.hidden = true;
      }});
      document.querySelectorAll('.filter-btn').forEach(function (btn) {{
        if (btn.getAttribute('data-col') !== (except && except.getAttribute('data-col'))) {{
          btn.classList.remove('active');
        }}
      }});
    }}

    // 面板固定用 position:fixed，開啟時才用按鈕的實際位置（getBoundingClientRect）
    // 動態算 top/left，並在空間不夠時自動往上/往左翻，確保不管表格目前縮多小、
    // 或面板本身開在畫面邊緣，選項清單都不會被裁掉或跑出畫面。
    function positionPanel(btn, panel) {{
      var btnRect = btn.getBoundingClientRect();
      var panelRect = panel.getBoundingClientRect();
      var top = btnRect.bottom + 4;
      if (top + panelRect.height > window.innerHeight) {{
        top = Math.max(4, btnRect.top - panelRect.height - 4);
      }}
      var left = btnRect.left;
      if (left + panelRect.width > window.innerWidth) {{
        left = Math.max(4, window.innerWidth - panelRect.width - 4);
      }}
      panel.style.top = top + 'px';
      panel.style.left = left + 'px';
    }}

    document.querySelectorAll('.filter-btn').forEach(function (btn) {{
      btn.addEventListener('click', function (ev) {{
        ev.stopPropagation();
        var col = btn.getAttribute('data-col');
        var panel = document.querySelector('.filter-panel[data-col="' + col + '"]');
        var willOpen = panel.hidden;
        closeAllPanels(willOpen ? panel : null);
        panel.hidden = !willOpen;
        btn.classList.toggle('active', willOpen);
        if (willOpen) positionPanel(btn, panel);
      }});
    }});

    document.addEventListener('click', function () {{ closeAllPanels(null); }});
    document.querySelectorAll('.filter-panel').forEach(function (panel) {{
      panel.addEventListener('click', function (ev) {{ ev.stopPropagation(); }});
    }});

    document.querySelectorAll('.filter-panel').forEach(function (panel) {{
      var col = panel.getAttribute('data-col');
      var optionCbs = panel.querySelectorAll('.filter-options input[type=checkbox]');

      // 「全選」「全部不選」只作用在目前（搜尋後）看得到的選項上，跟真正 Excel
      // 篩選清單的行為一致：先搜尋縮小範圍，再一次全選/全不選那個子集合。
      panel.querySelector('.select-all-btn').addEventListener('click', function () {{
        optionCbs.forEach(function (cb) {{
          if (cb.closest('label').hidden) return;
          cb.checked = true;
          selected[col].add(cb.value);
        }});
        applyFilters();
      }});
      panel.querySelector('.select-none-btn').addEventListener('click', function () {{
        optionCbs.forEach(function (cb) {{
          if (cb.closest('label').hidden) return;
          cb.checked = false;
          selected[col].delete(cb.value);
        }});
        applyFilters();
      }});

      optionCbs.forEach(function (cb) {{
        cb.addEventListener('change', function () {{
          if (cb.checked) selected[col].add(cb.value);
          else selected[col].delete(cb.value);
          applyFilters();
        }});
      }});

      var search = panel.querySelector('.filter-search');
      search.addEventListener('input', function () {{
        var q = search.value.trim().toLowerCase();
        optionCbs.forEach(function (cb) {{
          var label = cb.closest('label');
          label.hidden = q !== '' && cb.value.toLowerCase().indexOf(q) === -1;
        }});
        // 搜尋框本身就是一個即時篩選條件，不是只縮小面板裡的核取方塊清單而已，
        // 打字的當下表格就要跟著動——不用另外再勾/取消勾選才會生效。
        searchQuery[col] = q;
        applyFilters();
      }});
    }});

    // 這份 HTML 目前只有兩種嵌入方式：獨立下載開啟（不在 iframe 裡，
    // window.frameElement 會是 null，以下整段都是 no-op），或者被 Streamlit
    // 的 components.html 包在一個 iframe 裡（srcdoc 內容繼承外層頁面的
    // origin，同源，window.frameElement 抓得到外層那個 <iframe> 元素本身）。
    //
    // .table-wrap 的高度上限（--table-max-h）跟外層 iframe 的高度，這兩者
    // 刻意分成「先算表格上限、再貼合 iframe」單向流程，不能反過來：如果表格
    // 上限用 65dvh 這種相對「iframe 自己目前高度」的單位，而 iframe 高度又是
    // 靠 JS 貼合表格內容算出來的，兩者會互相依賴、越滾越大（iframe 長高 →
    // dvh 上限跟著變大 → 表格因此顯示更多內容不用內部捲動 → 內容變高 → iframe
    // 又要跟著長高……），實際症狀就是 iframe 最後長到遠超過使用者看得到的
    // 範圍，畫面上其他元素（例如側欄按鈕、下方的頁尾說明）看起來像是被推到
    // 很奇怪的位置、或者篩選面板的 position:fixed 定位跑掉蓋住不該蓋的地方。
    // 修法：表格高度上限改成用「外層真正瀏覽器視窗」的高度（優先讀
    // window.parent.innerHeight，抓不到才退回自己的 window.innerHeight）算出
    // 一個固定像素數，這個值不受我們自己調整 iframe 高度的動作影響，才能
    // 真正只算一次就穩定下來；iframe 的高度則貼合「表格上限已經固定之後」的
    // 內容總高度（有界，不會因為篩到的檔數變多就跟著暴增）。
    function computeTableMaxHeightPx() {{
      var refWin = window;
      try {{
        if (window.parent && window.parent !== window && window.parent.innerHeight) {{
          refWin = window.parent;
        }}
      }} catch (e) {{}}
      // 從 0.6 調高到 0.8：原本表格只吃視窗高度的六成，下面留了一大截
      // 空白（圖例按鈕、免責聲明加起來遠用不到那麼多），改成八成，讓
      // 使用者一打開畫面表格本身就佔滿幾乎整個可視範圍，更有「滿版」的
      // 感覺，同時還是留一點空間讓圖例/免責聲明看得到、不會被表格擠到
      // 螢幕外面。
      var vh = refWin.innerHeight || window.innerHeight || 800;
      return Math.max(280, Math.round(vh * 0.8));
    }}

    function applyTableMaxHeight() {{
      document.documentElement.style.setProperty('--table-max-h', computeTableMaxHeightPx() + 'px');
    }}

    function resizeFrame() {{
      try {{
        if (window.frameElement) {{
          window.frameElement.style.height = document.documentElement.scrollHeight + 'px';
        }}
      }} catch (e) {{}}
    }}

    // 點收盤價看技術分析圖表：純前端切換 #tableView / #chartView 兩個區塊的
    // hidden 屬性，不需要連回 Python/後端重新產生頁面，這份 HTML 不管是內嵌
    // 在 Streamlit 裡還是使用者獨立下載開啟都能用（PRICE_HISTORY 已經整份
    // 內嵌在這個檔案裡）。圖表用原生 canvas 手畫折線圖，沒有另外載入圖表庫。
    var currentChartStockId = null;
    var priceChart = document.getElementById('priceChart');
    var kdChart = document.getElementById('kdChart');
    var canvasWrap = document.querySelector('.chart-canvas-wrap');
    var resetBtn = document.getElementById('chartResetBtn');
    var jumpLatestBtn = document.getElementById('chartJumpLatestBtn');
    var modeBtn = document.getElementById('chartModeBtn');
    var kdGroupToggle = document.getElementById('kdGroupToggle');

    // 收盤價改用 K 棒（蠟燭圖）表示，不再是可以個別開關的一條線，所以
    // PRICE_SERIES 只剩四條均線；K 棒本身一律顯示，是價格圖的主體。
    var PRICE_SERIES = [
      {{ key: 'ma5', label: '5MA', color: '#e2a13a', width: 1.2 }},
      {{ key: 'ma10', label: '10MA', color: '#d6672c', width: 1.2 }},
      {{ key: 'ma20', label: '20MA', color: '#b5321b', width: 1.2 }},
      {{ key: 'ma60', label: '60MA', color: '#4f7a37', width: 1.2 }},
    ];
    var KD_SERIES = [
      {{ key: 'k', label: 'K', color: '#1a54c4', width: 1.4 }},
      {{ key: 'd', label: 'D', color: '#c4471a', width: 1.4 }},
    ];
    // 哪些線目前顯示、查價模式是多點還是單點——都是使用者的操作偏好，不是
    // 單一股票的資料，所以刻意放在 openChart() 外面，換股票看圖也不會
    // 重置；縮放範圍 chartRange 則相反，換一檔股票就該重新看整段，所以
    // 放在 openChart() 裡面重置。
    var seriesVisible = {{ ma5: true, ma10: true, ma20: true, ma60: true, k: true, d: true }};
    var chartRange = {{ start: 0, end: 0 }};
    var crosshairMode = 'multi'; // 'multi'（原本的多點模式）或 'single'（單一十字線，只標收盤價）

    // 價格圖跟 KD 子圖畫法幾乎一樣（格線＋刻度＋折線＋十字查價線），只有
    // Y 軸範圍、要不要畫日期刻度不同，所以抽成同一個函式，兩個 canvas
    // 各呼叫一次。opts.range 是目前縮放後的可視資料區間 {{start, end}}
    // （索引，含頭尾），沒給就畫全部。回傳畫圖當下用的座標換算參數，給
    // 滑鼠/觸控算最近的資料 index 用（兩個 canvas 寬度相同，這組參數兩邊
    // 共用也不會錯）。
    function drawPanel(canvas, dates, seriesList, hoverIdx, opts) {{
      opts = opts || {{}};
      var dpr = window.devicePixelRatio || 1;
      var cssWidth = canvas.clientWidth;
      var cssHeight = canvas.clientHeight;
      if (cssWidth <= 0 || cssHeight <= 0) return null;
      canvas.width = Math.round(cssWidth * dpr);
      canvas.height = Math.round(cssHeight * dpr);
      var ctx = canvas.getContext('2d');
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, cssWidth, cssHeight);

      var range = opts.range || {{ start: 0, end: dates.length - 1 }};
      var start = range.start, end = range.end;
      var count = end - start + 1;
      if (count <= 0) return null;

      var minV, maxV;
      if (opts.fixedRange) {{
        minV = opts.fixedRange[0];
        maxV = opts.fixedRange[1];
      }} else {{
        var allValues = [];
        seriesList.forEach(function (s) {{
          for (var i = start; i <= end; i++) {{
            var v = s.values[i];
            if (v !== null && v !== undefined) allValues.push(v);
          }}
        }});
        // K 棒的最高/最低價也要算進 Y 軸範圍，不然影線可能會超出畫布上下緣。
        if (opts.ohlc) {{
          for (var oi = start; oi <= end; oi++) {{
            var oh = opts.ohlc.high[oi], ol = opts.ohlc.low[oi];
            if (oh !== null && oh !== undefined) allValues.push(oh);
            if (ol !== null && ol !== undefined) allValues.push(ol);
          }}
        }}
        if (!allValues.length) return null;
        minV = Math.min.apply(null, allValues);
        maxV = Math.max.apply(null, allValues);
        var pad = (maxV - minV) * 0.08 || Math.max(1, minV * 0.05);
        minV -= pad;
        maxV += pad;
      }}

      var padLeft = 46, padRight = 10;
      var padTop = opts.padTop !== undefined ? opts.padTop : 10;
      var padBottom = opts.padBottom !== undefined ? opts.padBottom : 22;
      var plotW = Math.max(1, cssWidth - padLeft - padRight);
      var plotH = Math.max(1, cssHeight - padTop - padBottom);
      function xAt(i) {{ return padLeft + (count <= 1 ? plotW / 2 : ((i - start) / (count - 1)) * plotW); }}
      function yAt(v) {{ return padTop + (1 - (v - minV) / (maxV - minV)) * plotH; }}

      ctx.strokeStyle = '#eee';
      ctx.fillStyle = '#888';
      ctx.font = '11px -apple-system, BlinkMacSystemFont, sans-serif';
      ctx.textBaseline = 'middle';
      var gridValues = opts.gridValues;
      if (!gridValues) {{
        gridValues = [];
        var GRID_STEPS = 4;
        for (var g = 0; g <= GRID_STEPS; g++) {{
          gridValues.push(minV + (maxV - minV) * (g / GRID_STEPS));
        }}
      }}
      gridValues.forEach(function (v) {{
        var y = yAt(v);
        ctx.beginPath();
        ctx.moveTo(padLeft, y);
        ctx.lineTo(cssWidth - padRight, y);
        ctx.stroke();
        ctx.fillText(v.toFixed(opts.decimals !== undefined ? opts.decimals : 1), 2, y);
      }});

      // 超買/超賣參考線（KD 常見的 20/80），用虛線跟一般格線區隔開。
      if (opts.refLines) {{
        ctx.save();
        ctx.strokeStyle = '#ccc';
        ctx.setLineDash([3, 3]);
        opts.refLines.forEach(function (v) {{
          var y = yAt(v);
          ctx.beginPath();
          ctx.moveTo(padLeft, y);
          ctx.lineTo(cssWidth - padRight, y);
          ctx.stroke();
        }});
        ctx.restore();
      }}

      if (opts.showDateLabels) {{
        ctx.textBaseline = 'top';
        var labelCount = Math.min(5, count);
        for (var li = 0; li < labelCount; li++) {{
          var idx = labelCount <= 1 ? start : start + Math.round((li / (labelCount - 1)) * (count - 1));
          var x = xAt(idx);
          ctx.fillText(dates[idx].slice(5), Math.max(padLeft, x - 16), cssHeight - padBottom + 4);
        }}
      }}

      // K 棒先畫（當底），均線之類的折線後畫、疊在 K 棒上面才看得清楚。
      if (opts.ohlc) {{
        var oc = opts.ohlc;
        var bodyW = Math.max(1, (plotW / count) * 0.62);
        for (var ci = start; ci <= end; ci++) {{
          var co = oc.open[ci], ch = oc.high[ci], cl = oc.low[ci], cc = oc.close[ci];
          if (co === null || co === undefined || ch === null || ch === undefined ||
              cl === null || cl === undefined || cc === null || cc === undefined) {{
            continue;
          }}
          var cx = xAt(ci);
          var up = cc >= co;
          var color = up ? '#c0392b' : '#1e8449';
          ctx.strokeStyle = color;
          ctx.fillStyle = color;
          ctx.lineWidth = 1;
          ctx.beginPath();
          ctx.moveTo(cx, yAt(ch));
          ctx.lineTo(cx, yAt(cl));
          ctx.stroke();
          var yOpen = yAt(co), yClose = yAt(cc);
          var bodyTop = Math.min(yOpen, yClose);
          var bodyH = Math.max(1, Math.abs(yClose - yOpen));
          ctx.fillRect(cx - bodyW / 2, bodyTop, bodyW, bodyH);
        }}
      }}

      seriesList.forEach(function (s) {{
        ctx.strokeStyle = s.color;
        ctx.lineWidth = s.width;
        ctx.beginPath();
        var started = false;
        for (var i = start; i <= end; i++) {{
          var v = s.values[i];
          if (v === null || v === undefined) {{ started = false; continue; }}
          var x = xAt(i), y = yAt(v);
          if (!started) {{ ctx.moveTo(x, y); started = true; }} else {{ ctx.lineTo(x, y); }}
        }}
        ctx.stroke();
      }});

      var clampedHover = Math.max(start, Math.min(end, hoverIdx));
      var hx = xAt(clampedHover);
      ctx.save();
      ctx.strokeStyle = '#999';
      ctx.setLineDash([4, 3]);
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(hx, padTop);
      ctx.lineTo(hx, cssHeight - padBottom);
      ctx.stroke();
      // 十字線的橫線：只有價格圖（有帶 opts.ohlc）才畫，標的是收盤價那個
      // Y 座標，橫向貫穿整個繪圖區，這樣才是完整的「十字」查價線，不是
      // 只有豎線而已。
      if (opts.ohlc) {{
        var hoverCloseY = opts.ohlc.close[clampedHover];
        if (hoverCloseY !== null && hoverCloseY !== undefined) {{
          var hy = yAt(hoverCloseY);
          ctx.beginPath();
          ctx.moveTo(padLeft, hy);
          ctx.lineTo(cssWidth - padRight, hy);
          ctx.stroke();
        }}
      }}
      ctx.restore();

      // dotSeries 沒給就沿用 seriesList（KD 子圖是這樣，K/D 顯示什麼線就
      // 點什麼點）；價格圖會另外傳 dotSeries 進來，因為「多點/單點查價
      // 模式」影響的是十字線上要標幾個點，跟「畫面上畫了哪些均線」是
      // 兩件事，不能直接共用 seriesList。
      var dotSeries = opts.dotSeries || seriesList;
      dotSeries.forEach(function (s) {{
        var v = s.values[clampedHover];
        if (v === null || v === undefined) return;
        ctx.beginPath();
        ctx.arc(hx, yAt(v), 3, 0, Math.PI * 2);
        ctx.fillStyle = s.color;
        ctx.fill();
      }});

      // 在十字線附近標一個小標籤，直接告訴使用者現在看的是哪一天、
      // 收盤多少，不用低頭去看圖表下方那排文字才知道。
      if (opts.showHoverLabel && opts.ohlc) {{
        var hoverClose = opts.ohlc.close[clampedHover];
        if (hoverClose !== null && hoverClose !== undefined) {{
          var labelText = dates[clampedHover].slice(5) + ' 收盤 ' + hoverClose.toFixed(2);
          ctx.font = '11px -apple-system, BlinkMacSystemFont, sans-serif';
          var textW = ctx.measureText(labelText).width;
          var boxW = textW + 12, boxH = 18;
          var boxX = Math.min(Math.max(hx - boxW / 2, padLeft), cssWidth - padRight - boxW);
          var boxY = padTop;
          ctx.fillStyle = 'rgba(30,30,30,0.82)';
          ctx.beginPath();
          if (ctx.roundRect) {{
            ctx.roundRect(boxX, boxY, boxW, boxH, 4);
          }} else {{
            ctx.rect(boxX, boxY, boxW, boxH);
          }}
          ctx.fill();
          ctx.fillStyle = '#fff';
          ctx.textAlign = 'left';
          ctx.textBaseline = 'middle';
          ctx.fillText(labelText, boxX + 6, boxY + boxH / 2);
        }}
      }}

      return {{ start: start, end: end, padLeft: padLeft, plotW: plotW }};
    }}

    // hoverIdx 省略時預設顯示最新一天（游標離開圖表、剛打開圖表時的預設畫面）。
    function renderChart(stockId, hoverIdx) {{
      var hist = PRICE_HISTORY[stockId];
      if (!hist || !hist.dates.length) return;
      var n = hist.dates.length;
      if (hoverIdx === null || hoverIdx === undefined) hoverIdx = chartRange.end;
      hoverIdx = Math.max(chartRange.start, Math.min(chartRange.end, hoverIdx));

      var priceSeries = PRICE_SERIES.filter(function (s) {{ return seriesVisible[s.key]; }})
        .map(function (s) {{ return {{ key: s.key, color: s.color, width: s.width, values: hist[s.key] }}; }});
      var closeDot = {{ key: 'close', color: '#1a1a1a', values: hist.close }};
      // 多點模式：原本每條顯示中的均線各一個點，再加上收盤價那一點；
      // 單點模式：不管勾了哪些均線，十字線上只標收盤價這一個點。
      var dotSeries = crosshairMode === 'single' ? [closeDot] : priceSeries.concat([closeDot]);
      var priceState = drawPanel(priceChart, hist.dates, priceSeries, hoverIdx, {{
        padBottom: 8, showDateLabels: false, range: chartRange,
        ohlc: {{ open: hist.open, high: hist.high, low: hist.low, close: hist.close }},
        dotSeries: dotSeries, showHoverLabel: true,
      }});

      var kdOn = hist.k && hist.d && (seriesVisible.k || seriesVisible.d);
      canvasWrap.classList.toggle('kd-hidden', !kdOn);
      var kdState = null;
      if (kdOn) {{
        var kdSeries = KD_SERIES.filter(function (s) {{ return seriesVisible[s.key]; }})
          .map(function (s) {{ return {{ key: s.key, color: s.color, width: s.width, values: hist[s.key] }}; }});
        kdState = drawPanel(kdChart, hist.dates, kdSeries, hoverIdx, {{
          fixedRange: [0, 100], decimals: 0, gridValues: [0, 20, 50, 80, 100], refLines: [20, 80],
          padTop: 6, padBottom: 22, showDateLabels: true, range: chartRange,
        }});
      }}

      var infoEl = document.getElementById('chartInfo');
      if (infoEl) {{
        var parts = [hist.dates[hoverIdx]];
        var closeVal = hist.close[hoverIdx];
        parts.push('收盤：' + (closeVal === null || closeVal === undefined ? '—' : closeVal.toFixed(2)));
        PRICE_SERIES.forEach(function (s) {{
          if (!seriesVisible[s.key]) return;
          var v = hist[s.key][hoverIdx];
          parts.push(s.label + '：' + (v === null || v === undefined ? '—' : v.toFixed(2)));
        }});
        if (hist.k && hist.d) {{
          KD_SERIES.forEach(function (s) {{
            if (!seriesVisible[s.key]) return;
            var v = hist[s.key][hoverIdx];
            parts.push(s.label + '：' + (v === null || v === undefined ? '—' : v.toFixed(1)));
          }});
        }}
        infoEl.textContent = parts.join('　');
      }}

      // 兩個 canvas 寬度相同，滑鼠/觸控算最近的資料點時共用價格圖那組座標
      // 換算參數即可，不需要分別存兩份；KD 子圖被隱藏時退回用它自己的狀態。
      priceChart._chartState = priceState || kdState;
      resetBtn.hidden = !(chartRange.start > 0 || chartRange.end < n - 1);
      // 「回到最新」跟「顯示全部區間」是兩個不同情境：後者是「有縮放就show」，
      // 前者專門處理「縮放/平移後，最新一天（今天）被移出可視範圍看不到」
      // 這個使用者實際回報過的情況，只要最新一天不在畫面裡就顯示，不管
      // 目前是不是有縮放。
      jumpLatestBtn.hidden = chartRange.end >= n - 1;
    }}

    function updateLegendUI() {{
      document.querySelectorAll('.legend-item[data-series]').forEach(function (btn) {{
        var key = btn.getAttribute('data-series');
        btn.classList.toggle('off', !seriesVisible[key]);
      }});
      kdGroupToggle.classList.toggle('off', !(seriesVisible.k || seriesVisible.d));
    }}

    function openChart(stockId, name) {{
      if (!PRICE_HISTORY[stockId]) return;
      currentChartStockId = stockId;
      chartRange = {{ start: 0, end: PRICE_HISTORY[stockId].dates.length - 1 }};
      document.getElementById('chartStockLabel').textContent = (name || '') + '（' + stockId + '）';
      document.getElementById('tableView').hidden = true;
      document.getElementById('chartView').hidden = false;
      updateLegendUI();
      // hidden 屬性剛拿掉的當下，canvas 所在的容器可能還沒完成排版，
      // clientWidth/clientHeight 會量到 0，用 requestAnimationFrame 等一次
      // 排版完成再畫圖，避免圖表整個空白。
      requestAnimationFrame(function () {{
        renderChart(stockId, null);
        resizeFrame();
      }});
    }}

    function closeChart() {{
      document.getElementById('chartView').hidden = true;
      document.getElementById('tableView').hidden = false;
      currentChartStockId = null;
      resizeFrame();
    }}

    document.querySelectorAll('.price-link').forEach(function (el) {{
      el.addEventListener('click', function () {{
        openChart(el.getAttribute('data-stock-id'), el.getAttribute('data-name'));
      }});
    }});
    document.querySelector('.chart-back-btn').addEventListener('click', closeChart);

    // 圖例點下去切換該條線顯示/隱藏；K、D 都關掉時 renderChart() 裡會自動
    // 把整個 KD 子圖藏起來（見 kdOn 判斷），不需要在這裡另外處理。
    document.querySelectorAll('.legend-item[data-series]').forEach(function (btn) {{
      btn.addEventListener('click', function () {{
        var key = btn.getAttribute('data-series');
        seriesVisible[key] = !seriesVisible[key];
        updateLegendUI();
        if (currentChartStockId) {{
          renderChart(currentChartStockId, null);
          resizeFrame();
        }}
      }});
    }});

    // 「KD 全部」是把 K、D 兩條線當一組一起開/關的捷徑：兩條有任一條開著
    // 就視為目前「開」，點一下就兩條一起關掉；兩條都關著的時候點一下就
    // 兩條一起打開。
    kdGroupToggle.addEventListener('click', function () {{
      var bothOn = seriesVisible.k && seriesVisible.d;
      seriesVisible.k = !bothOn;
      seriesVisible.d = !bothOn;
      updateLegendUI();
      if (currentChartStockId) {{
        renderChart(currentChartStockId, null);
        resizeFrame();
      }}
    }});

    modeBtn.addEventListener('click', function () {{
      crosshairMode = crosshairMode === 'multi' ? 'single' : 'multi';
      modeBtn.textContent = '查價模式：' + (crosshairMode === 'multi' ? '多點' : '單點');
      if (currentChartStockId) renderChart(currentChartStockId, null);
    }});

    resetBtn.addEventListener('click', function () {{
      if (!currentChartStockId) return;
      chartRange = {{ start: 0, end: PRICE_HISTORY[currentChartStockId].dates.length - 1 }};
      renderChart(currentChartStockId, null);
    }});

    // 「回到最新」保留目前縮放的天數範圍（span），只是把整個窗口平移到
    // 結尾對齊最新一天——跟「顯示全部區間」不一樣，不會把縮放重置掉，
    // 單純解決「查價查到比較早的日期、放大過後看不到今天」這件事。
    jumpLatestBtn.addEventListener('click', function () {{
      if (!currentChartStockId) return;
      var hist = PRICE_HISTORY[currentChartStockId];
      var n = hist.dates.length;
      var span = chartRange.end - chartRange.start + 1;
      var newEnd = n - 1;
      var newStart = Math.max(0, newEnd - span + 1);
      chartRange = {{ start: newStart, end: newEnd }};
      renderChart(currentChartStockId, null);
    }});

    function idxFromClientX(clientX) {{
      var state = priceChart._chartState;
      if (!state) return null;
      var rect = priceChart.getBoundingClientRect();
      var count = state.end - state.start + 1;
      var rel = (clientX - rect.left - state.padLeft) / state.plotW;
      return Math.round(state.start + rel * (count - 1));
    }}

    // 把 {{newStart, newEnd}} 夾回 [0, n-1] 的合法範圍內，天數（span）不變、
    // 只是整體往左或往右推回界線內——縮放跟平移最後都會呼叫這個，邏輯只
    // 寫一次。
    function clampRange(newStart, newEnd, n) {{
      if (newStart < 0) {{ newEnd -= newStart; newStart = 0; }}
      if (newEnd > n - 1) {{ newStart -= (newEnd - (n - 1)); newEnd = n - 1; }}
      newStart = Math.max(0, newStart);
      newEnd = Math.min(n - 1, newEnd);
      return {{ start: newStart, end: newEnd }};
    }}

    // 兩指縮放（手機）／滾輪（滑鼠，桌機測試用）都是同一件事：改變目前
    // chartRange 涵蓋的天數（縮放），並讓「兩指中點／滑鼠所在位置」對應
    // 的那個資料點盡量停留在畫面上同一個位置，體感才會像「用手指撐開/
    // 收攏那個點附近」，而不是整段區間跳來跳去。
    function applyZoom(factor, anchorIdx) {{
      if (!currentChartStockId) return;
      var hist = PRICE_HISTORY[currentChartStockId];
      var n = hist.dates.length;
      var span = chartRange.end - chartRange.start + 1;
      var newSpan = Math.max(10, Math.min(n, Math.round(span / factor)));
      if (newSpan === span) return;
      var anchorRatio = span <= 1 ? 0 : (anchorIdx - chartRange.start) / (span - 1);
      var newStart = Math.round(anchorIdx - anchorRatio * (newSpan - 1));
      chartRange = clampRange(newStart, newStart + newSpan - 1, n);
      renderChart(currentChartStockId, anchorIdx);
    }}

    // 平移：天數範圍（span）不變，整段窗口往前或往後移 daysDelta 天——這是
    // 為了解決縮放/查價到比較早的日期之後，最新一天被移出可視範圍、又不
    // 想整個重置縮放回全區間的情況。正值往「更早」的日期移動，負值往
    // 「更新」的日期移動（見呼叫端手勢方向的換算）。
    function applyPan(daysDelta) {{
      if (!currentChartStockId || !daysDelta) return;
      var hist = PRICE_HISTORY[currentChartStockId];
      var n = hist.dates.length;
      var span = chartRange.end - chartRange.start + 1;
      var newStart = Math.round(chartRange.start - daysDelta);
      chartRange = clampRange(newStart, newStart + span - 1, n);
      renderChart(currentChartStockId, null);
    }}

    function touchDistance(touches) {{
      var dx = touches[0].clientX - touches[1].clientX;
      var dy = touches[0].clientY - touches[1].clientY;
      return Math.sqrt(dx * dx + dy * dy);
    }}

    var pinchState = null;

    // 價格圖跟 KD 子圖是同一個查價/縮放互動的兩個畫面，滑鼠/觸控在任一個
    // 畫布上操作都要同步反映到兩張圖，所以兩個 canvas 都掛同一組事件處理，
    // 而不是各自獨立。單指＝查價（拖曳看該日數值），雙指＝縮放（撐開/
    // 收攏改變顯示的天數範圍），滑鼠滾輪在桌機上也能縮放，方便沒有觸控
    // 螢幕時測試。
    [priceChart, kdChart].forEach(function (canvas) {{
      canvas.addEventListener('mousemove', function (ev) {{
        if (!currentChartStockId) return;
        var idx = idxFromClientX(ev.clientX);
        if (idx !== null) renderChart(currentChartStockId, idx);
      }});
      canvas.addEventListener('mouseleave', function () {{
        if (currentChartStockId) renderChart(currentChartStockId, null);
      }});
      canvas.addEventListener('wheel', function (ev) {{
        if (!currentChartStockId) return;
        ev.preventDefault();
        // 觸控板兩指左右滑會產生比較大的 deltaX，視為「平移」而不是縮放；
        // 一般滑鼠滾輪幾乎只有 deltaY，維持原本的縮放行為。
        if (Math.abs(ev.deltaX) > Math.abs(ev.deltaY)) {{
          var state = priceChart._chartState;
          if (state) {{
            var span = state.end - state.start + 1;
            applyPan((ev.deltaX / state.plotW) * span);
          }}
          return;
        }}
        var idx = idxFromClientX(ev.clientX);
        if (idx === null) return;
        applyZoom(ev.deltaY < 0 ? 1.15 : 1 / 1.15, idx);
      }}, {{ passive: false }});
      canvas.addEventListener('touchstart', function (ev) {{
        if (!currentChartStockId) return;
        if (ev.touches.length >= 2) {{
          pinchState = {{
            dist: touchDistance(ev.touches),
            midX: (ev.touches[0].clientX + ev.touches[1].clientX) / 2,
          }};
        }} else if (ev.touches.length === 1) {{
          var idx = idxFromClientX(ev.touches[0].clientX);
          if (idx !== null) renderChart(currentChartStockId, idx);
        }}
      }}, {{ passive: true }});
      canvas.addEventListener('touchmove', function (ev) {{
        if (!currentChartStockId) return;
        if (ev.touches.length >= 2 && pinchState) {{
          // 雙指同時支援縮放（兩指距離改變）跟平移（兩指中點整體移動），
          // 使用者常常是「邊撐開邊移動」，兩者分開判斷、互不干擾。
          var newDist = touchDistance(ev.touches);
          var newMidX = (ev.touches[0].clientX + ev.touches[1].clientX) / 2;
          var factor = newDist / pinchState.dist;
          if (Math.abs(factor - 1) > 0.03) {{
            var anchorIdx = idxFromClientX(newMidX);
            if (anchorIdx !== null) applyZoom(factor, anchorIdx);
            pinchState.dist = newDist;
          }}
          var midShift = newMidX - pinchState.midX;
          if (Math.abs(midShift) > 2) {{
            var state = priceChart._chartState;
            if (state) {{
              var span = state.end - state.start + 1;
              applyPan((midShift / state.plotW) * span);
            }}
            pinchState.midX = newMidX;
          }}
          ev.preventDefault();
        }} else if (ev.touches.length === 1) {{
          var idx = idxFromClientX(ev.touches[0].clientX);
          if (idx !== null) renderChart(currentChartStockId, idx);
          ev.preventDefault();
        }}
      }}, {{ passive: false }});
      canvas.addEventListener('touchend', function (ev) {{
        if (ev.touches.length < 2) pinchState = null;
      }});
    }});

    function refresh() {{
      applyTableMaxHeight();
      resizeFrame();
      if (currentChartStockId) {{ renderChart(currentChartStockId, null); }}
    }}

    refresh();
    window.addEventListener('load', refresh);
    window.addEventListener('resize', refresh);
    try {{
      if (window.parent && window.parent !== window) {{
        window.parent.addEventListener('resize', refresh);
      }}
    }} catch (e) {{}}
    // 展開/收合「各分類代表意義」「查詢失敗清單」這兩個 <details> 會改變內容
    // 高度，只需要重新貼合 iframe 高度，不需要重算表格上限。
    document.querySelectorAll('details').forEach(function (d) {{
      d.addEventListener('toggle', resizeFrame);
    }});
    if (window.ResizeObserver) {{
      new ResizeObserver(resizeFrame).observe(document.body);
    }}
  </script>
</body>
</html>"""

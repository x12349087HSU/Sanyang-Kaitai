"""把 0050 均線篩選結果組成一頁獨立、自成一體（沒有外部依賴）的 HTML 網頁。"""
from __future__ import annotations

import html as html_lib

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


def _fmt_price(value: float | None) -> str:
    return f"{value:,.2f}" if value is not None else "—"


def _rows_html(rows: list) -> str:
    if not rows:
        return '<p class="empty">本次篩選查無符合條件的個股。</p>'
    # data-* 屬性給前端欄位篩選用（代號/收盤價/資料日期），之後要加更多可篩選
    # 欄位，比照這裡加一個 data-* 屬性、在 applyFilters() 裡加一個條件即可。
    body_rows = "\n".join(
        f"""<tr data-stock-id="{html_lib.escape(r.stock_id)}" data-close="{r.close}"
              data-date="{r.trade_date.isoformat()}">
          <td>{html_lib.escape(r.stock_id)}</td>
          <td>{html_lib.escape(r.company_name)}</td>
          <td class="num">{_fmt_price(r.close)}</td>
          <td class="num">{_fmt_price(r.ma5)}</td>
          <td class="num">{_fmt_price(r.ma10)}</td>
          <td class="num">{_fmt_price(r.ma20)}</td>
          <td class="num">{_fmt_price(r.ma60)}</td>
          <td>{r.trade_date.isoformat()}</td>
        </tr>"""
        for r in rows
    )
    return f"""<table>
      <thead><tr>
        <th>代號</th><th>名稱</th><th>收盤價</th><th>5MA</th><th>10MA</th><th>20MA</th><th>60MA</th><th>資料日期</th>
      </tr></thead>
      <tbody>
        {body_rows}
        <tr class="no-match-row" hidden><td colspan="8">篩選條件無符合的個股</td></tr>
      </tbody>
    </table>"""


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
    as_of = result.as_of_date
    as_of_text = as_of.isoformat() if as_of else "無可用資料"
    title = f"{universe_label}均線篩選"
    default_tier = TIER_ORDER[0]

    options = "\n".join(
        f'<option value="{tier}"{" selected" if tier == default_tier else ""}>'
        f"{TIER_LABELS[tier]}（{len(result.rows_by_tier(tier))} 檔）</option>"
        for tier in TIER_ORDER
    )

    sections = "".join(
        f"""
        <section class="tier" data-tier="{tier}"{"" if tier == default_tier else " hidden"}
          style="--accent:{_TIER_ACCENT[tier]}">
          <h2><span class="badge">{TIER_LABELS[tier]}</span>（{len(result.rows_by_tier(tier))} 檔）</h2>
          <p class="desc">{TIER_DESCRIPTIONS[tier]}</p>
          {_rows_html(result.rows_by_tier(tier))}
        </section>"""
        for tier in TIER_ORDER
    )

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
  h1 {{ font-size: 1.4rem; margin: 0 0 0.2rem; }}
  .meta {{ color: #666; font-size: 0.85rem; margin-bottom: 1rem; }}
  .filter-bar {{
    display: flex; align-items: center; gap: 0.6rem; margin-bottom: 1.2rem;
    background: #fff; border-radius: 10px; padding: 0.8rem 1rem;
    box-shadow: 0 1px 3px rgba(0,0,0,0.06);
  }}
  .filter-bar label {{ font-size: 0.9rem; color: #444; font-weight: 600; }}
  .filter-bar select {{
    flex: 1; font-size: 0.95rem; padding: 0.4rem 0.6rem; border-radius: 6px;
    border: 1px solid #ccc; background: #fff; color: #1a1a1a;
  }}
  .column-filters {{
    display: flex; flex-wrap: wrap; gap: 0.8rem 1.4rem; margin-bottom: 1.2rem;
    background: #fff; border-radius: 10px; padding: 0.8rem 1rem;
    box-shadow: 0 1px 3px rgba(0,0,0,0.06);
  }}
  .column-filters .field {{ display: flex; flex-direction: column; gap: 0.25rem; }}
  .column-filters label {{ font-size: 0.78rem; color: #666; }}
  .column-filters input {{
    font-size: 0.9rem; padding: 0.35rem 0.5rem; border-radius: 6px;
    border: 1px solid #ccc; background: #fff; color: #1a1a1a; width: 9rem;
  }}
  .column-filters .range-inputs {{ display: flex; align-items: center; gap: 0.35rem; }}
  .column-filters .range-inputs input {{ width: 6rem; }}
  .column-filters button {{
    align-self: flex-end; font-size: 0.82rem; padding: 0.4rem 0.8rem; border-radius: 6px;
    border: 1px solid #ccc; background: #f5f5f5; color: #444; cursor: pointer;
  }}
  tr.no-match-row td {{ color: #888; text-align: center; white-space: normal; }}
  section.tier {{
    background: #fff; border-radius: 10px; padding: 1rem 1.2rem; margin-bottom: 1.2rem;
    border-left: 6px solid var(--accent); box-shadow: 0 1px 3px rgba(0,0,0,0.06);
  }}
  section.tier h2 {{ font-size: 1.1rem; margin: 0 0 0.3rem; }}
  .badge {{ color: var(--accent); font-weight: 700; }}
  .desc {{ color: #555; font-size: 0.85rem; margin: 0 0 0.8rem; }}
  table {{
    width: 100%; border-collapse: collapse; font-size: 0.85rem; display: block;
    overflow: auto; max-height: 55vh;
  }}
  thead {{ position: sticky; top: 0; }}
  th, td {{ text-align: left; padding: 0.4rem 0.5rem; border-bottom: 1px solid #eee; white-space: nowrap; }}
  td.num, th:nth-child(n+3) {{ text-align: right; }}
  tbody tr:hover {{ background: #faf8f5; }}
  .empty {{ color: #888; font-size: 0.85rem; }}
  details.skipped {{ font-size: 0.8rem; color: #777; margin-top: 1rem; }}
  footer {{ margin-top: 1.6rem; font-size: 0.78rem; color: #888; line-height: 1.7; }}
  @media (max-width: 480px) {{
    body {{ padding: 1rem; }}
    table {{ font-size: 0.78rem; }}
    th, td {{ padding: 0.3rem; }}
  }}
</style>
</head>
<body>
  <h1>{html_lib.escape(title)}</h1>
  <p class="meta">篩選範圍：{html_lib.escape(universe_label)}（共 {len(result.rows) + len(result.skipped)} 檔）　資料日期：{as_of_text}　產生時間：{result.generated_at.isoformat()}　資料來源：FinMind（+ 證交所官方備援）</p>
  <div class="filter-bar">
    <label for="tierSelect">篩選分類</label>
    <select id="tierSelect">
      {options}
    </select>
  </div>
  <div class="column-filters">
    <div class="field">
      <label for="filterStockId">代號</label>
      <input type="text" id="filterStockId" placeholder="例如 2330" inputmode="numeric" />
    </div>
    <div class="field">
      <label>收盤價</label>
      <div class="range-inputs">
        <input type="number" id="filterMinClose" placeholder="最低" step="0.01" />
        <span>～</span>
        <input type="number" id="filterMaxClose" placeholder="最高" step="0.01" />
      </div>
    </div>
    <div class="field">
      <label for="filterDate">資料日期</label>
      <input type="date" id="filterDate" />
    </div>
    <button type="button" id="filterReset">清除欄位篩選</button>
  </div>
  {sections}
  {_skipped_html(result.skipped)}
  <footer>
    均線分級為巢狀判定：多頭（紅）與空頭（綠）各四級，例如「{TIER_LABELS[3]}」代表
    同時站上 5MA/10MA/20MA，不代表站上或跌破 60MA——若也站上 60MA，會被歸類到更高
    一級的「{TIER_LABELS[4]}」；空頭四級（{TIER_LABELS[-1]}／{TIER_LABELS[-2]}／
    {TIER_LABELS[-3]}／{TIER_LABELS[-4]}）是鏡像邏輯，條件改成「跌破」對應數量的均線。
    多空訊號不一致（例如站上 5MA 但跌破 10MA）的股票不列入這八個等級。
    5MA/10MA/20MA/60MA 皆為收盤價簡單移動平均（SMA），非官方統一標準。<br />
    {html_lib.escape(config.DISCLAIMER_TEXT)}
  </footer>
  <script>
    // 欄位篩選：套用在「目前顯示中的那個等級」的表格列上，跟均線分級（哪個
    // section 顯示）是各自獨立的兩層篩選，可以疊加使用。之後要加更多可篩選
    // 欄位（例如名稱、5MA 等），在 _rows_html() 補一個 data-* 屬性，這裡加一個
    // 對應的 if 判斷即可，不需要更動篩選分類（tier）那一層的邏輯。
    function visibleSection() {{
      return document.querySelector('section.tier:not([hidden])');
    }}

    function applyColumnFilters() {{
      var section = visibleSection();
      if (!section) return;

      var stockIdQuery = document.getElementById('filterStockId').value.trim().toLowerCase();
      var minCloseRaw = document.getElementById('filterMinClose').value;
      var maxCloseRaw = document.getElementById('filterMaxClose').value;
      var minClose = minCloseRaw === '' ? null : parseFloat(minCloseRaw);
      var maxClose = maxCloseRaw === '' ? null : parseFloat(maxCloseRaw);
      var dateQuery = document.getElementById('filterDate').value;

      var rows = section.querySelectorAll('tbody tr[data-stock-id]');
      var visibleCount = 0;
      rows.forEach(function (row) {{
        var stockId = (row.getAttribute('data-stock-id') || '').toLowerCase();
        var close = parseFloat(row.getAttribute('data-close'));
        var date = row.getAttribute('data-date') || '';

        var match = true;
        if (stockIdQuery && stockId.indexOf(stockIdQuery) === -1) match = false;
        if (match && minClose !== null && !(close >= minClose)) match = false;
        if (match && maxClose !== null && !(close <= maxClose)) match = false;
        if (match && dateQuery && date !== dateQuery) match = false;

        row.hidden = !match;
        if (match) visibleCount++;
      }});

      var noMatchRow = section.querySelector('.no-match-row');
      if (noMatchRow) noMatchRow.hidden = visibleCount > 0;
    }}

    document.getElementById('tierSelect').addEventListener('change', function (ev) {{
      var selected = ev.target.value;
      document.querySelectorAll('section.tier').forEach(function (section) {{
        section.hidden = section.getAttribute('data-tier') !== selected;
      }});
      applyColumnFilters();
    }});

    ['filterStockId', 'filterMinClose', 'filterMaxClose', 'filterDate'].forEach(function (id) {{
      document.getElementById(id).addEventListener('input', applyColumnFilters);
    }});

    document.getElementById('filterReset').addEventListener('click', function () {{
      document.getElementById('filterStockId').value = '';
      document.getElementById('filterMinClose').value = '';
      document.getElementById('filterMaxClose').value = '';
      document.getElementById('filterDate').value = '';
      applyColumnFilters();
    }});
  </script>
</body>
</html>"""

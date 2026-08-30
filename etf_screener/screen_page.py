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
    ("tier", "分類"),
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
          <td class="num">{html_lib.escape(attrs['close'])}</td>
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
      <summary>各分類代表意義（點擊展開）</summary>
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
    as_of = result.as_of_date
    as_of_text = as_of.isoformat() if as_of else "無可用資料"
    title = f"{universe_label}均線篩選"

    ordered_rows: list[tuple[int, object]] = [
        (tier, r) for tier in TIER_ORDER for r in result.rows_by_tier(tier)
    ]
    col_keys = [col for col, _ in _COLUMNS]

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
  .meta {{ color: #666; font-size: 0.85rem; margin-bottom: 0.6rem; }}
  details.legend {{ margin-bottom: 1rem; }}
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
    overflow: auto; max-height: 65vh;
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
  footer {{ margin-top: 1.6rem; font-size: 0.78rem; color: #888; line-height: 1.7; }}
  @media (max-width: 480px) {{
    body {{ padding: 1rem; }}
    table {{ font-size: 0.78rem; }}
    td {{ padding: 0.3rem 0.4rem; }}
  }}
</style>
</head>
<body>
  <h1>{html_lib.escape(title)}</h1>
  <p class="meta">篩選範圍：{html_lib.escape(universe_label)}（共 {len(result.rows) + len(result.skipped)} 檔）　資料日期：{as_of_text}　產生時間：{result.generated_at.isoformat()}　資料來源：FinMind（+ 證交所官方備援）</p>
  {_legend_html()}
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
  <footer>
    均線分級為巢狀判定：多頭（紅）與空頭（綠）各四級，例如「{TIER_LABELS[3]}」代表
    同時站上 5MA/10MA/20MA，不代表站上或跌破 60MA——若也站上 60MA，會被歸類到更高
    一級的「{TIER_LABELS[4]}」；空頭四級是鏡像邏輯，條件改成「跌破」對應數量的均線。
    多空訊號不一致（例如站上 5MA 但跌破 10MA）的股票不列入這八個等級。
    5MA/10MA/20MA/60MA 皆為收盤價簡單移動平均（SMA），非官方統一標準，表格中未
    顯示各均線數值，僅顯示分類結果。<br />
    {html_lib.escape(config.DISCLAIMER_TEXT)}
  </footer>
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
  </script>
</body>
</html>"""

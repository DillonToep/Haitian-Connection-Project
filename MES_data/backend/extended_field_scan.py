"""Label-driven extraction of the "extended info" fields (客户名称,
机型, 原料信息, 产品重量, 运水/模温, 操作设定, etc. -- everything rendered
by EXTENDED_INFO_SECTIONS in frontend/js/app.js) from an uploaded
注塑成型条件参数表 workbook.

The older EXTENDED_CELL_MAP in export_xlsx.py was built against a
different, differently-laid-out template (试模成型参数表) and only
covers a handful of overlapping fields at the WRONG fixed coordinates
for this layout -- e.g. its (7, 4) "ext:machine_maker" cell lands on an
unrelated cell in a 注塑成型条件参数表 workbook, which is why 机台厂商
was being read from the wrong place while every other extended field
(客户名称, 机型, 日期, 原料信息, 运水/模温, 操作设定, ...) was never read
at all.

This module is layout-specific (deliberately -- there is exactly one
known layout for this sheet so far), but every value is located by
searching for its Chinese label text rather than assuming a byte-exact
coordinate, so it tolerates the sheet gaining/losing a row elsewhere
(hot-runner block populated or not, extra revision rows, etc.) as long
as the label text itself stays put relative to its own value.

Two value-placement patterns are used on this sheet:
  - "same row, to the right"  (row 2's 客户名称/注塑机编号/机型/机台产商/日期)
  - "same column, below"      (everything else: 模具编号/产品名称/... row3-4,
    原料信息 row5-6, 产品重量 row7-8, 顶针/残余料量位置, 周期设定, 操作设定)

Checkbox-style fields (本厂提供/客户提供/射胶方式/运水类别/操作设定) are
read as "is there a check-mark (√) in the expected cell", not a text
value.
"""
from __future__ import annotations

try:
    from .label_scan_xlsx import normalize_label
except ImportError:  # allow standalone testing outside the backend package
    from label_scan_xlsx import normalize_label


def _is_blank(value) -> bool:
    return value is None or (isinstance(value, str) and value.strip() == "")


def _find_label(grid, aliases, exact_only: bool = True):
    """First (r, c) whose cell text matches one of `aliases` after
    normalize_label(). Exact match preferred (see label_scan_xlsx's
    find_all_title_cells for why substring matching alone is risky --
    a short label can be a substring of an unrelated, longer one)."""
    loose_hit = None
    for r, row in enumerate(grid):
        for c, value in enumerate(row):
            if value is None or not isinstance(value, str):
                continue
            normalized = normalize_label(value)
            if not normalized:
                continue
            if any(normalized == normalize_label(alias) for alias in aliases):
                return (r, c)
            if loose_hit is None and any(normalize_label(alias) in normalized for alias in aliases):
                loose_hit = (r, c)
    return None if exact_only else loose_hit


def _value_right(grid, r, c, max_right=4):
    """First non-blank cell to the right of (r, c) within max_right
    columns, on the same row -- for the "label, value" same-row pattern."""
    label_text = grid[r][c] if c < len(grid[r]) else None
    row = grid[r]
    for cc in range(c + 1, min(len(row), c + 1 + max_right)):
        value = row[cc]
        if _is_blank(value) or value == label_text:
            continue
        return value
    return None


def _value_below(grid, r, c, max_down=4):
    """First non-blank cell directly below (r, c) within max_down rows,
    same column -- for the "label row, value row" pattern.

    A merged label cell (e.g. a label merged across several rows, with
    its real value sitting in the first UNMERGED row right after it)
    resolves to the same repeated text on every row of that merge (see
    build_resolved_grid[_xlrd]) -- those repeats must be skipped, or the
    label's own merged-cell echo gets mistaken for its value."""
    label_text = grid[r][c] if c < len(grid[r]) else None
    for rr in range(r + 1, min(len(grid), r + 1 + max_down)):
        if c < len(grid[rr]):
            value = grid[rr][c]
            if _is_blank(value) or value == label_text:
                continue
            return value
    return None


def _is_checked(value) -> bool:
    if value is None:
        return False
    text = str(value).strip()
    return "√" in text or text == "v" or text == "V"


def _checked_below(grid, r, c, max_down=3) -> bool:
    label_text = grid[r][c] if c < len(grid[r]) else None
    for rr in range(r + 1, min(len(grid), r + 1 + max_down)):
        if c < len(grid[rr]):
            value = grid[rr][c]
            if value == label_text:
                continue
            if _is_checked(value):
                return True
    return False


# ---------------------------------------------------------------------
# Simple label -> (direction, field_key) rules. "right" fields are all
# on the same header row as each other; "below" fields have their value
# one (or a few) rows straight down from the label.
# ---------------------------------------------------------------------

_RIGHT_FIELDS = [
    (("客户名称",), "customer_name"),
    (("注塑机编号",), "customer_machine_no"),
    (("机型",), "machine_model"),
    (("机台产商", "机台厂商"), "machine_maker"),
    (("日期",), "form_date"),
]

_BELOW_FIELDS = [
    # (aliases, field_key, max_down)
    (("模具编号",), None, 1),  # informational only -- fed from the mold record elsewhere, not written back
    (("产品名称",), None, 1),
    (("产品编号",), None, 1),  # handled separately -- also feeds header.product_code
    (("文件版本",), "file_version", 1),
    (("原料名称",), "material_name", 1),
    (("原料产地",), "material_origin", 1),
    (("色种编号",), "color_code", 1),
    (("颜色",), "color", 1),
    (("烘料时间",), "drying_time", 1),
    (("焗炉温度",), "oven_temperature", 1),
    (("射胶总时间秒", "射胶总时间"), "cycle_injection_total", 1),
    (("冷却总时间秒", "冷却总时间"), "cycle_cooling_total", 1),
    (("抽呵时间秒", "抽呵时间"), "cycle_suction_total", 1),
    (("全程总时间秒", "全程总时间"), "cycle_grand_total", 1),
    (("需用人数个", "需用人数"), "op_headcount", 1),
    # These two labels sit inside a multi-row-tall merged header cell,
    # so their real value starts a few rows further down than a plain
    # one-row label -- see _value_below's merged-echo skipping.
    (("残余料量位置MM", "残余料量位置"), "residual_material_position", 4),
    (("顶出次数",), "ejector_count", 3),
]

_WEIGHT_FIELDS = [(("毛重",), "gross_weight"), (("净重",), "net_weight"), (("水口重",), "runner_weight")]

_CHECKBOX_BELOW_FIELDS = [
    (("本厂提供",), "supplied_by_factory"),
    (("客户提供",), "supplied_by_customer"),
    (("机水",), "water_temp_machine"),
    (("热水",), "water_temp_hot_water"),
    (("热油",), "water_temp_hot_oil"),
    (("冷水",), "water_temp_cold_water"),
    (("手动",), "op_manual"),
    (("半自动",), "op_semi_auto"),
    (("全自动",), "op_full_auto"),
    (("机械手",), "op_robot"),
]

# fit_tonnage: the label cell's OWN row/col holds a combined
# "模具尺寸（MM)、适合机台吨位(T)" header; the value directly below is
# just the tonnage ("100T") on this template (mold_dimensions has no
# separate cell of its own on this layout).
_TONNAGE_LABEL_ALIASES = ("模具尺寸MM适合机台吨位T", "适合机台吨位T", "适合机台吨位")


def _scan_injection_mode(grid) -> dict:
    """射胶方式 is one free-text cell like
    '射胶方式：   位置   √    ×  √        时间      ×  √' -- a checkbox
    per method (位置/时间), each followed by a short run of √/× marks.
    Only the FIRST mark after each method name reflects that method's
    current selection on this template (the remaining marks are stray
    OCR-of-paper artifacts from repeated edits), so this reads only the
    first √/× token following each label."""
    result = {}
    for row in grid:
        for value in row:
            if not isinstance(value, str) or "射胶方式" not in value:
                continue
            for label, key in (("位置", "injection_mode_position"), ("时间", "injection_mode_time")):
                idx = value.find(label)
                if idx == -1:
                    continue
                tail = value[idx + len(label):]
                for ch in tail:
                    if ch in "√×xX":
                        result[key] = (ch == "√")
                        break
            return result
    return result


def _scan_water_grid(grid) -> dict:
    """运水/模温 row-label x column-header grid:
        headers (A板/B板/行呵) on one row, with 抽芯明细 to their right
        运水设定(Ref) / 标准温度±5℃ / 实测模温±5℃ label rows below it,
        each holding up to 3 values (A/B/行呵) plus a shared 抽芯明细 cell.
    """
    result = {}
    header_pos = _find_label(grid, ("A板",))
    if header_pos is None:
        return result
    header_row, a_col = header_pos
    b_col = a_col + 1
    c_col = a_col + 2  # 行呵

    row_defs = [
        (("运水设定Ref", "运水设定"), ("water_ref_a", "water_ref_b", "water_ref_c")),
        (("标准温度±5℃", "标准温度"), ("water_std_a", "water_std_b", "water_std_c")),
        (("实测模温±5℃", "实测模温"), ("water_measured_a", "water_measured_b", "water_measured_c")),
    ]
    # Row labels for this grid sit in the column just left of A板's
    # column, scanning downward from the header row.
    label_col = a_col - 1
    if label_col < 0:
        return result

    for aliases, keys in row_defs:
        for r in range(header_row + 1, min(len(grid), header_row + 6)):
            if label_col >= len(grid[r]):
                continue
            cell = grid[r][label_col]
            if not isinstance(cell, str):
                continue
            if not any(normalize_label(cell) == normalize_label(a) for a in aliases):
                continue
            for key, col in zip(keys, (a_col, b_col, c_col)):
                if col < len(grid[r]) and not _is_blank(grid[r][col]):
                    result[key] = grid[r][col]
            break

    # 抽芯明细 spans the same row block, one column to the right of 行呵.
    detail_col = c_col + 1
    detail_header = _find_label(grid, ("抽芯明细",))
    if detail_header is not None:
        dr, dc = detail_header
        value = _value_below(grid, dr, dc, max_down=1)
        if value is None and dc < len(grid[header_row]):
            pass
        if not _is_blank(value):
            result["water_cavity_detail"] = value

    return result


def _scan_hot_runner(grid) -> dict:
    """热流道温度设定±10℃ -- up to 10 stage columns split across two
    header rows (1段..5段, then 6段..10段), each with its data value one
    row below its own header row. Blank/no-hot-runner molds simply have
    nothing below the headers, which is fine -- nothing is written."""
    result = {}
    header_pos = _find_label(grid, ("热流道温度设定", "热流道温度设定±10℃"), exact_only=False)
    if header_pos is None:
        return result
    header_row, header_col = header_pos

    def _stage_cols(row_idx):
        cols = {}
        if row_idx >= len(grid):
            return cols
        for c in range(header_col + 1, min(len(grid[row_idx]), header_col + 13)):
            cell = grid[row_idx][c]
            if not isinstance(cell, str):
                continue
            normalized = normalize_label(cell)
            if normalized.endswith("段") and normalized[:-1].isdigit():
                cols[int(normalized[:-1])] = c
        return cols

    first_row_cols = _stage_cols(header_row)
    second_header_row = header_row + 2  # data row for 1-5段 sits between the two header rows
    second_row_cols = _stage_cols(second_header_row) if second_header_row < len(grid) else {}

    for stage, col in first_row_cols.items():
        value = grid[header_row + 1][col] if header_row + 1 < len(grid) and col < len(grid[header_row + 1]) else None
        if not _is_blank(value):
            result[f"hot_runner_t{stage}"] = value

    for stage, col in second_row_cols.items():
        value = grid[second_header_row + 1][col] if second_header_row + 1 < len(grid) and col < len(grid[second_header_row + 1]) else None
        if not _is_blank(value):
            result[f"hot_runner_t{stage}"] = value

    return result


def scan_extended_fields(grid) -> dict:
    """Returns {extended_field_key: value} for a 注塑成型条件参数表-layout
    grid (see label_scan_xlsx.build_resolved_grid /
    build_resolved_grid_xlrd for how to build one). Only keys with an
    actual non-blank value found on the sheet are included."""
    result: dict = {}

    for aliases, key in _RIGHT_FIELDS:
        pos = _find_label(grid, aliases)
        if pos is None:
            continue
        value = _value_right(grid, *pos)
        if not _is_blank(value):
            result[key] = value

    for aliases, key, max_down in _BELOW_FIELDS:
        if key is None:
            continue
        pos = _find_label(grid, aliases)
        if pos is None:
            continue
        value = _value_below(grid, *pos, max_down=max_down)
        if not _is_blank(value):
            result[key] = value

    for aliases, key in _WEIGHT_FIELDS:
        pos = _find_label(grid, aliases)
        if pos is None:
            continue
        value = _value_below(grid, *pos, max_down=1)
        if not _is_blank(value):
            result[key] = value

    for aliases, key in _CHECKBOX_BELOW_FIELDS:
        pos = _find_label(grid, aliases)
        if pos is None:
            continue
        if _checked_below(grid, *pos):
            result[key] = True

    tonnage_pos = _find_label(grid, _TONNAGE_LABEL_ALIASES, exact_only=False)
    if tonnage_pos is not None:
        value = _value_below(grid, *tonnage_pos, max_down=1)
        if not _is_blank(value):
            result["fit_tonnage"] = value

    result.update(_scan_injection_mode(grid))
    result.update(_scan_water_grid(grid))
    result.update(_scan_hot_runner(grid))

    return result


def scan_header_overrides(grid) -> dict:
    """A couple of extended-scan labels double as header info that
    HEADER_CELL_MAP doesn't reliably catch on this layout (产品编号 has
    no entry in HEADER_CELL_MAP at all). Returned separately so the
    caller can merge these into `header` rather than `extended`."""
    result = {}
    pos = _find_label(grid, ("产品编号",))
    if pos is not None:
        value = _value_below(grid, *pos)
        if not _is_blank(value):
            result["product_code"] = value
    return result
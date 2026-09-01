from __future__ import annotations

try:
    from .label_scan_xlsx import normalize_label
except ImportError:
    from label_scan_xlsx import normalize_label


def _is_blank(value) -> bool:
    return value is None or (isinstance(value, str) and value.strip() == "")


def _find_label(grid, aliases, exact_only: bool = True):
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
    label_text = grid[r][c] if c < len(grid[r]) else None
    row = grid[r]
    for cc in range(c + 1, min(len(row), c + 1 + max_right)):
        value = row[cc]
        if _is_blank(value) or value == label_text:
            continue
        return value
    return None


def _value_below(grid, r, c, max_down=4):
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


_RIGHT_FIELDS = [
    (("客户名称",), "customer_name"),
    (("注塑机编号",), "customer_machine_no"),
    (("机型",), "machine_model"),
    (("机台产商", "机台厂商"), "machine_maker"),
    (("日期",), "form_date"),
]

_BELOW_FIELDS = [
    (("模具编号",), None, 1),
    (("产品名称",), None, 1),
    (("产品编号",), None, 1),
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

# Every key in _CHECKBOX_BELOW_FIELDS is a boolean-style field -- exposed
# so the write side (export_xlsx.py) knows to render True as "√" / False
# as a cleared cell instead of writing a raw Python bool into the sheet.
CHECKBOX_KEYS = {key for _, key in _CHECKBOX_BELOW_FIELDS}

_TONNAGE_LABEL_ALIASES = ("模具尺寸MM适合机台吨位T", "适合机台吨位T", "适合机台吨位")


def _scan_injection_mode(grid) -> dict:
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
    result = {}
    header_pos = _find_label(grid, ("A板",))
    if header_pos is None:
        return result
    header_row, a_col = header_pos
    b_col = a_col + 1
    c_col = a_col + 2

    row_defs = [
        (("运水设定Ref", "运水设定"), ("water_ref_a", "water_ref_b", "water_ref_c")),
        (("标准温度±5℃", "标准温度"), ("water_std_a", "water_std_b", "water_std_c")),
        (("实测模温±5℃", "实测模温"), ("water_measured_a", "water_measured_b", "water_measured_c")),
    ]
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
    second_header_row = header_row + 2
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
    result = {}
    pos = _find_label(grid, ("产品编号",))
    if pos is not None:
        value = _value_below(grid, *pos)
        if not _is_blank(value):
            result["product_code"] = value
    return result


# ===========================================================================
# ---- WRITE-SIDE (position) lookups --------------------------------------
# ===========================================================================
#
# Mirrors of _value_right / _value_below, but returning the CELL POSITION
# a field would resolve to, rather than reading whatever is currently
# sitting there. This is what export_xlsx.overlay_values_onto_template
# needs for the newer "注塑成型条件参数表" layout: it must locate where to
# WRITE a value (or blank a cell) even for a field that's currently empty,
# using the exact same label-search rules the read side above already
# uses -- so a value written on export reads back correctly on the next
# import, and vice versa.
#
# Unlike _value_right/_value_below (which skip blank cells while looking
# for an existing value), these skip only cells that are literal repeats
# of the label's own text -- which happens when the label itself sits in
# a merged cell spanning several rows/columns (build_resolved_grid
# expands merges by repeating the anchor's value across every covered
# cell). Skipping those repeats is what keeps a write from landing back
# on top of the label itself; landing on a currently-blank cell is fine
# and expected.
# ===========================================================================

def _write_pos_right(grid, r, c, max_right=4):
    label_text = grid[r][c] if c < len(grid[r]) else None
    row = grid[r]
    for cc in range(c + 1, min(len(row), c + 1 + max_right)):
        if row[cc] == label_text:
            continue
        return (r, cc)
    return (r, c + 1)


def _write_pos_below(grid, r, c, max_down=4):
    label_text = grid[r][c] if c < len(grid[r]) else None
    for rr in range(r + 1, min(len(grid), r + 1 + max_down)):
        if c < len(grid[rr]) and grid[rr][c] == label_text:
            continue
        return (rr, c)
    return (r + 1, c)


# Header fields (模具编号/产品名称/产品编号/模穴数) share the exact same
# "label row, value row below" layout as _BELOW_FIELDS -- they're marked
# key=None there because the READ side treats them as informational only
# (fed from the mold record, not written back into `extended`). The
# write side needs their positions regardless, since export must still
# put the mold's own code/name/product-code/cavities into those cells.
_HEADER_LABEL_FIELDS = (
    (("模具编号",), "mold_code"),
    (("产品名称",), "mold_name"),
    (("产品编号",), "product_code"),
    (("模穴数",), "cavities"),
)


def locate_new_layout_fields(grid) -> dict:
    """Returns {"header": {field: (row0, col0)}, "extended": {key: (row0, col0)}}
    for every header/extended field this module knows how to place on the
    newer 注塑成型条件参数表 layout, located by searching for each field's
    own label text -- exactly mirroring scan_extended_fields /
    scan_header_overrides above, just returning a position instead of a
    value. A field whose label can't be found on this particular sheet is
    simply omitted, rather than falling back to a guessed coordinate."""
    header: dict = {}
    extended: dict = {}

    for aliases, field in _HEADER_LABEL_FIELDS:
        pos = _find_label(grid, aliases)
        if pos is not None:
            header[field] = _write_pos_below(grid, *pos, max_down=1)

    for aliases, key in _RIGHT_FIELDS:
        pos = _find_label(grid, aliases)
        if pos is not None:
            extended[key] = _write_pos_right(grid, *pos)

    for aliases, key, max_down in _BELOW_FIELDS:
        if key is None:
            continue
        pos = _find_label(grid, aliases)
        if pos is not None:
            extended[key] = _write_pos_below(grid, *pos, max_down=max_down)

    for aliases, key in _WEIGHT_FIELDS:
        pos = _find_label(grid, aliases)
        if pos is not None:
            extended[key] = _write_pos_below(grid, *pos, max_down=1)

    tonnage_pos = _find_label(grid, _TONNAGE_LABEL_ALIASES, exact_only=False)
    if tonnage_pos is not None:
        extended["fit_tonnage"] = _write_pos_below(grid, *tonnage_pos, max_down=1)

    for aliases, key in _CHECKBOX_BELOW_FIELDS:
        pos = _find_label(grid, aliases)
        if pos is not None:
            extended[key] = _write_pos_below(grid, *pos, max_down=3)

    header_pos = _find_label(grid, ("A板",))
    if header_pos is not None:
        header_row, a_col = header_pos
        b_col, c_col = a_col + 1, a_col + 2
        label_col = a_col - 1
        row_defs = [
            (("运水设定Ref", "运水设定"), ("water_ref_a", "water_ref_b", "water_ref_c")),
            (("标准温度±5℃", "标准温度"), ("water_std_a", "water_std_b", "water_std_c")),
            (("实测模温±5℃", "实测模温"), ("water_measured_a", "water_measured_b", "water_measured_c")),
        ]
        if label_col >= 0:
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
                        extended[key] = (r, col)
                    break
        detail_header = _find_label(grid, ("抽芯明细",))
        if detail_header is not None:
            dr, dc = detail_header
            extended["water_cavity_detail"] = _write_pos_below(grid, dr, dc, max_down=1)

    hr_pos = _find_label(grid, ("热流道温度设定", "热流道温度设定±10℃"), exact_only=False)
    if hr_pos is not None:
        header_row, header_col = hr_pos

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
        second_header_row = header_row + 2
        second_row_cols = _stage_cols(second_header_row) if second_header_row < len(grid) else {}

        for stage, col in first_row_cols.items():
            if header_row + 1 < len(grid):
                extended[f"hot_runner_t{stage}"] = (header_row + 1, col)
        for stage, col in second_row_cols.items():
            if second_header_row + 1 < len(grid):
                extended[f"hot_runner_t{stage}"] = (second_header_row + 1, col)

    return {"header": header, "extended": extended}
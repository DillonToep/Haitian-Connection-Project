"""Reverses the cell maps in export_xlsx.py so a filled-in 试模成型参数表
can be read back into structured data for import.

Three source formats are supported, all mapped onto the same
HEADER_CELL_MAP / EXTENDED_CELL_MAP / PARAMETER_CELL_MAP /
_HOT_RUNNER_ROW / _HOT_RUNNER_COLS / _MERGES cell positions defined in
export_xlsx.py (so the maps only need to be maintained in one place):

- .xlsx / .xlsm -- read via openpyxl, using the workbook's own merged
  cells (a value only lives on a merge's top-left cell).
- .xls (Excel 97-2003 / legacy BIFF) -- read via xlrd, same idea but
  using xlrd's merged_cells info.
- .csv -- read as a plain row/column grid via the stdlib csv module.
  CSV has no merged-cell concept, so every mapped cell must contain its
  own value directly (i.e. a CSV exported from a merged sheet will only
  have the value in the top-left cell of each former merge anyway,
  which is exactly what these cell maps expect).

Only cells listed in the maps are read; anything else on the sheet is
ignored, same scope limitation the export side documents.
"""
from io import BytesIO, StringIO
import csv
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import re

from openpyxl import load_workbook

from .export_xlsx import (
    HEADER_CELL_MAP,
    EXTENDED_CELL_MAP,
    PARAMETER_CELL_MAP,
    _HOT_RUNNER_ROW,
    _HOT_RUNNER_COLS,
    _MERGES,
)
from .label_scan_xlsx import (
    build_resolved_grid,
    build_resolved_grid_xlrd,
    scan_all_blocks,
)

# Anchor-cell lookup for the *built-in* xlsx template's merges -- only
# used by the xlsx reader (openpyxl only stores a value on the top-left
# cell of a merged range; every other cell in that range reads back as
# None on a workbook built from our own template).
_ANCHOR_FOR = {}
for _r0, _r1, _c0, _c1 in _MERGES:
    for _rr in range(_r0, _r1):
        for _cc in range(_c0, _c1):
            _ANCHOR_FOR[(_rr, _cc)] = (_r0, _c0)


def _normalize_numeric_string(value):
    """Whole/rounded numbers become a plain integer string ("25", never
    "25.0"), matching how target_value is stored everywhere else in the
    app (see the equivalent helper in backend/routers/favorites.py).
    Non-numeric values (enum codes, free text) pass through unchanged."""
    if value is None:
        return value
    candidate = value.strip() if isinstance(value, str) else value
    if candidate == "":
        return value
    try:
        number = Decimal(str(candidate))
    except (InvalidOperation, ValueError, TypeError):
        return str(value).strip() if isinstance(value, str) else value
    return str(int(number.to_integral_value(rounding=ROUND_HALF_UP)))


def _clean(value):
    if value is None:
        return None
    if isinstance(value, str):
        value = value.strip()
    return value if value not in (None, "") else None


_FULLWIDTH_DIGITS = str.maketrans("０１２３４５６７８９", "0123456789")


def _normalize_extended_text(value):
    if value is None:
        return ""
    text = str(value).translate(_FULLWIDTH_DIGITS)
    text = text.replace("\n", "").replace("\r", "")
    text = text.replace("\u3000", "").replace(" ", "")
    text = text.replace("（", "(").replace("）", ")")
    text = text.replace("℃", "C").replace("°", "")
    text = text.replace("±", "")
    text = re.sub(r"\([^)]*\)", "", text)
    text = text.replace("%", "")
    text = text.strip()
    return text


def _is_truthy_checkbox(value):
    if value is None:
        return False
    normalized = _normalize_extended_text(value)
    if normalized in {"", "0", "False", "No", "否", "未", "N", "OFF", "off"}:
        return False
    if normalized in {"1", "True", "Yes", "是", "Y", "ON", "on", "√", "✓", "☑", "勾", "选中"}:
        return True
    if re.fullmatch(r"[0-9]+(?:\.[0-9]+)?", normalized):
        return float(normalized) > 0
    return bool(normalized)


def _scan_extended_values(grid):
    """Best-effort parser for the human-entered extended fields on the
    试模成型参数表. It reads by label text rather than fixed coordinates so
    uploaded files whose layout drifts still populate the same key names the
    frontend expects.
    """
    aliases = {
        "mold_code": ("模具编号", "模具代号"),
        "mold_name": ("产品名称", "模具名称", "模具名"),
        "product_code": ("产品编号", "产品代号", "产品号"),
        "cavities": ("模穴数", "穴数"),
        "customer_name": ("客户名称", "客户",),
        "customer_machine_no": ("注塑机编号", "机台编号", "机号", "注塑机号"),
        "machine_model": ("机型", "机型号"),
        "machine_maker": ("机台厂商", "机台产商", "厂商"),
        "form_date": ("日期", "日期:", "试模日期"),
        "mold_dimensions": ("模具尺寸MM", "模具尺寸", "模具尺寸(MM)", "模具尺寸mm"),
        "fit_tonnage": ("适合机台吨位T", "适合机台吨位", "适合机台吨位(T)", "适合机台吨位t"),
        "file_version": ("文件版本", "版本", "文件版号"),
        "material_name": ("原料名称", "胶料名称"),
        "material_origin": ("原料产地", "料源"),
        "drying_time": ("烘料时间", "烘料时间H", "烘料时间(h)"),
        "oven_temperature": ("焗炉温度", "烘料温度", "烘料温度C"),
        "supplied_by_factory": ("本厂提供",),
        "supplied_by_customer": ("客户提供",),
        "gross_weight": ("毛重", "毛重g"),
        "net_weight": ("净重", "净重g"),
        "runner_weight": ("水口重", "水口重g"),
        "injection_mode_position": ("位置方式",),
        "injection_mode_time": ("时间方式",),
        "residual_material_position": ("残余料量位置", "残余料量位置MM", "残余料量位置(mm)"),
        "water_temp_machine": ("机水C", "机水", "机水(℃)"),
        "water_temp_hot_water": ("热水C", "热水", "热水(℃)"),
        "water_temp_hot_oil": ("热油C", "热油", "热油(℃)"),
        "water_temp_cold_water": ("冷水C", "冷水", "冷水(℃)"),
        "ejector_stall_seconds": ("停留时间秒", "停留时间", "停留时间(秒)"),
        "ejector_count": ("顶出次数", "顶针次数"),
        "ejector_position": ("顶针位置", "顶出位置"),
        "cycle_injection_total": ("射胶总时间秒", "射胶总时间", "射胶总时间(秒)"),
        "cycle_cooling_total": ("冷却总时间秒", "冷却总时间", "冷却总时间(秒)"),
        "cycle_suction_total": ("抽呵时间秒", "抽呵时间", "抽呵时间(秒)"),
        "cycle_grand_total": ("全程总时间秒", "全程总时间", "全程总时间(秒)"),
        "op_manual": ("手动",),
        "op_semi_auto": ("半自动",),
        "op_full_auto": ("全自动",),
        "op_robot": ("机械手",),
        "op_headcount": ("需用人数", "需用人数个", "需用人数(个)"),
    }

    def _matches_alias(value, alias_set):
        text = _normalize_extended_text(value)
        return text in alias_set or any(text == alias or text.startswith(alias) for alias in alias_set)

    def _read_value_from_label(row_idx, col_idx):
        row = grid[row_idx]
        candidates = []
        for c in range(col_idx + 1, min(len(row), col_idx + 6)):
            cell = row[c]
            if cell is None or str(cell).strip() == "":
                continue
            candidates.append(cell)
            if not _normalize_extended_text(cell).startswith("□") and not _normalize_extended_text(cell).startswith("☐"):
                return _clean(cell)
        for r in range(row_idx + 1, min(len(grid), row_idx + 6)):
            cell = grid[r][col_idx]
            if cell is None or str(cell).strip() == "":
                continue
            return _clean(cell)
        for c in range(col_idx + 1, min(len(row), col_idx + 6)):
            if row[c] is not None and str(row[c]).strip() != "":
                return _clean(row[c])
        return None

    found = {}
    for row_idx, row in enumerate(grid):
        for col_idx, value in enumerate(row):
            if value is None:
                continue
            normalized = _normalize_extended_text(value)
            for field_name, alias_list in aliases.items():
                alias_set = {alias for alias in alias_list}
                if not _matches_alias(value, alias_set):
                    continue
                if field_name in {"supplied_by_factory", "supplied_by_customer", "injection_mode_position", "injection_mode_time", "water_temp_machine", "water_temp_hot_water", "water_temp_hot_oil", "water_temp_cold_water", "op_manual", "op_semi_auto", "op_full_auto", "op_robot"}:
                    candidate = None
                    for c in range(col_idx + 1, min(len(row), col_idx + 5)):
                        cell = row[c]
                        if cell is not None and str(cell).strip() != "":
                            candidate = cell
                            break
                    if candidate is None:
                        for r in range(row_idx + 1, min(len(grid), row_idx + 5)):
                            cell = grid[r][col_idx]
                            if cell is not None and str(cell).strip() != "":
                                candidate = cell
                                break
                    found[field_name] = _is_truthy_checkbox(candidate)
                else:
                    value_from_cell = _read_value_from_label(row_idx, col_idx)
                    if value_from_cell is not None:
                        found[field_name] = value_from_cell
                break

    # Grid-style values like 运水设定 / 标准温度 / 实测模温. The sheet
    # usually formats them as label + value cells in a row, so read the
    # non-empty cells immediately to the right of the label and assign them
    # in left-to-right order to A/B/C columns when present.
    row_aliases = {"运水设定": "water_ref", "标准温度": "water_std", "实测模温": "water_measured"}
    for row_idx, row in enumerate(grid):
        label_col = None
        label_key = None
        for col_idx, value in enumerate(row):
            candidate = row_aliases.get(_normalize_extended_text(value))
            if candidate is not None:
                label_key = candidate
                label_col = col_idx
                break
        if label_key is None:
            continue
        values = []
        for c_idx in range(label_col + 1, min(len(row), label_col + 6)):
            cell_value = row[c_idx]
            if cell_value not in (None, ""):
                values.append(_clean(cell_value))
        for offset, value in enumerate(values[:3]):
            found[f"{label_key}_{'abc'[offset]}"] = value

    # Product-weight values are usually in the same row as the label, so
    # capture those even when the label is read as a standalone text cell.
    weight_aliases = {
        "gross_weight": ("毛重",),
        "net_weight": ("净重",),
        "runner_weight": ("水口重",),
    }
    for row_idx, row in enumerate(grid):
        for col_idx, value in enumerate(row):
            norm = _normalize_extended_text(value)
            for field_name, aliases in weight_aliases.items():
                if norm not in aliases and not any(norm == alias or norm.startswith(alias) for alias in aliases):
                    continue
                candidate = _read_value_from_label(row_idx, col_idx)
                if candidate is not None:
                    found[field_name] = candidate
                break

    return found


def _scan_extended_xlsx(file_bytes: bytes) -> dict:
    workbook = load_workbook(BytesIO(file_bytes), data_only=True)
    worksheet = workbook.active
    grid = build_resolved_grid(worksheet)
    return _scan_extended_values(grid)


def _scan_extended_xls(file_bytes: bytes) -> dict:
    try:
        import xlrd
    except ImportError as error:
        raise RuntimeError(
            "服务器缺少 xlrd 库，无法解析 .xls 文件（请安装 xlrd 或改用 .xlsx/.csv）"
        ) from error
    try:
        workbook = xlrd.open_workbook(file_contents=file_bytes, formatting_info=True)
    except Exception:
        workbook = xlrd.open_workbook(file_contents=file_bytes)
    sheet = workbook.sheet_by_index(0)
    grid = build_resolved_grid_xlrd(sheet)
    return _scan_extended_values(grid)


def _scan_extended_csv(file_bytes: bytes) -> dict:
    text = file_bytes.decode("utf-8-sig", errors="replace")
    rows = list(csv.reader(StringIO(text)))
    return _scan_extended_values(rows)


def _scan_parameters_xlsx(file_bytes: bytes) -> dict:
    """Label-driven parameter scan for .xlsx/.xlsm -- replaces reading
    PARAMETER_CELL_MAP by fixed coordinate. See label_scan_xlsx.py for
    why: an uploaded workbook's real row/column layout can differ from
    the built-in template's, and fixed coordinates silently misread the
    wrong cell (or a merged banner cell) when it does."""
    workbook = load_workbook(BytesIO(file_bytes), data_only=True)
    worksheet = workbook.active
    grid = build_resolved_grid(worksheet)
    return scan_all_blocks(grid)


def _scan_parameters_xls(file_bytes: bytes) -> dict:
    try:
        import xlrd
    except ImportError as error:
        raise RuntimeError(
            "服务器缺少 xlrd 库，无法解析 .xls 文件（请安装 xlrd 或改用 .xlsx/.csv）"
        ) from error
    try:
        workbook = xlrd.open_workbook(file_contents=file_bytes, formatting_info=True)
    except Exception:
        workbook = xlrd.open_workbook(file_contents=file_bytes)
    sheet = workbook.sheet_by_index(0)
    grid = build_resolved_grid_xlrd(sheet)
    return scan_all_blocks(grid)


def _make_xlsx_reader(file_bytes: bytes):
    """.xlsx / .xlsm -- openpyxl. Resolves each mapped cell against the
    UPLOADED workbook's own merged ranges first (same approach the .xls
    reader below uses), falling back to the built-in template's static
    merge map (_ANCHOR_FOR) for any cell the uploaded file doesn't merge
    itself. The fallback keeps this working exactly as before for a
    workbook whose merges happen to match the built-in template, while
    the real-merges-first lookup fixes cells whose merge boundaries in
    the actual uploaded file differ from that static assumption (e.g. a
    template that was hand-edited, or one whose merges don't line up
    1:1 with ours) -- previously a mismatch here silently read back
    blank instead of resolving to wherever the value actually lives."""
    workbook = load_workbook(BytesIO(file_bytes), data_only=True)
    worksheet = workbook.active

    anchor_for = dict(_ANCHOR_FOR)
    for merged_range in worksheet.merged_cells.ranges:
        anchor = (merged_range.min_row - 1, merged_range.min_col - 1)
        for r in range(merged_range.min_row - 1, merged_range.max_row):
            for c in range(merged_range.min_col - 1, merged_range.max_col):
                anchor_for[(r, c)] = anchor

    def _read(row0: int, col0: int):
        anchor_row0, anchor_col0 = anchor_for.get((row0, col0), (row0, col0))
        value = worksheet.cell(row=anchor_row0 + 1, column=anchor_col0 + 1).value
        return _clean(value)

    return _read


def _make_xls_reader(file_bytes: bytes):
    """Legacy .xls (Excel 97-2003 / BIFF), via xlrd. openpyxl cannot open
    this format, and xlrd 2.x dropped xlsx support entirely, so xlrd is
    used only for this one path."""
    try:
        import xlrd
    except ImportError as error:
        raise RuntimeError(
            "服务器缺少 xlrd 库，无法解析 .xls 文件（请安装 xlrd 或改用 .xlsx/.csv）"
        ) from error

    # formatting_info=True is required for xlrd to populate
    # sheet.merged_cells at all -- without it the attribute is always an
    # empty list regardless of what the file actually contains, which
    # silently defeated the merge-anchor resolution below for every cell
    # that isn't itself a merge's top-left corner (several of the
    # PARAMETER_CELL_MAP / EXTENDED_CELL_MAP entries aren't). A handful of
    # malformed/legacy .xls files raise while xlrd parses the formatting
    # records this needs, so fall back to the old (merge-blind) behavior
    # for those rather than failing the import outright.
    try:
        workbook = xlrd.open_workbook(file_contents=file_bytes, formatting_info=True)
    except Exception:
        workbook = xlrd.open_workbook(file_contents=file_bytes)
    sheet = workbook.sheet_by_index(0)

    # Build an anchor map from THIS file's own merged cells (not the
    # static template map above) -- an uploaded .xls may not be merged
    # identically to the generated xlsx template.
    anchor_for = {}
    for rlo, rhi, clo, chi in getattr(sheet, "merged_cells", []):
        for r in range(rlo, rhi):
            for c in range(clo, chi):
                anchor_for[(r, c)] = (rlo, clo)

    def _read(row0: int, col0: int):
        anchor_row0, anchor_col0 = anchor_for.get((row0, col0), (row0, col0))
        if anchor_row0 >= sheet.nrows or anchor_col0 >= sheet.ncols:
            return None
        value = sheet.cell_value(anchor_row0, anchor_col0)
        return _clean(value)

    return _read


def _make_csv_reader(file_bytes: bytes):
    """.csv -- plain row/column grid, no merged-cell concept. A mapped
    cell must carry its own value directly."""
    text = file_bytes.decode("utf-8-sig", errors="replace")
    rows = list(csv.reader(StringIO(text)))

    def _read(row0: int, col0: int):
        if row0 >= len(rows) or col0 >= len(rows[row0]):
            return None
        return _clean(rows[row0][col0])

    return _read


def _reader_for(file_bytes: bytes, filename: str):
    ext = (filename or "").lower().rsplit(".", 1)[-1] if "." in (filename or "") else ""
    if ext == "xls":
        return _make_xls_reader(file_bytes)
    if ext == "csv":
        return _make_csv_reader(file_bytes)
    return _make_xlsx_reader(file_bytes)  # .xlsx / .xlsm (default/fallback)


def parse_trial_parameter_workbook(file_bytes: bytes, filename: str = "") -> dict:
    """Returns
    {
        "header": {"mold_code": ..., "mold_name": ..., "cavities": ...},
        "extended": {key: value, ...},
        "parameters": {tag: normalized_value_string, ...},
    }
    Every sub-dict only contains keys the sheet actually had a
    non-blank value for -- a blank cell means "leave whatever is
    already saved alone", never "clear it".

    `filename` picks the parser: .xls -> xlrd, .csv -> csv module,
    anything else (.xlsx/.xlsm, or unspecified) -> openpyxl.
    """
    read_cell = _reader_for(file_bytes, filename)

    header: dict = {}
    for (row0, col0), key in HEADER_CELL_MAP.items():
        _, field = key.split(":", 1)
        value = read_cell(row0, col0)
        if value is not None:
            header[field] = value

    extended: dict = {}
    for (row0, col0), key in EXTENDED_CELL_MAP.items():
        _, field = key.split(":", 1)
        value = read_cell(row0, col0)
        if value is not None:
            extended[field] = value

    ext = (filename or "").lower().rsplit(".", 1)[-1] if "." in (filename or "") else ""
    if ext == "xls":
        extended.update(_scan_extended_xls(file_bytes))
    elif ext == "csv":
        extended.update(_scan_extended_csv(file_bytes))
    else:
        extended.update(_scan_extended_xlsx(file_bytes))

    for offset, col0 in enumerate(_HOT_RUNNER_COLS):
        value = read_cell(_HOT_RUNNER_ROW, col0)
        if value is not None:
            extended[f"hot_runner_t{offset + 1}"] = value

    # ---- parameters: label-driven scan for .xlsx/.xlsm/.xls, since this
    # is the path that broke against a real-world layout drift (extra
    # inserted row shifted every fixed coordinate below it). .csv has no
    # merged-cell/label-search story worth building (a CSV export of a
    # merged sheet only carries a value in each former merge's top-left
    # cell anyway), so it stays on the fixed-coordinate reader.
    ext = (filename or "").lower().rsplit(".", 1)[-1] if "." in (filename or "") else ""
    if ext == "xls":
        raw_parameters = _scan_parameters_xls(file_bytes)
    elif ext == "csv":
        raw_parameters = None
    else:
        raw_parameters = _scan_parameters_xlsx(file_bytes)

    parameters: dict = {}
    if raw_parameters is not None:
        for tag, value in raw_parameters.items():
            if value not in (None, ""):
                parameters[tag] = _normalize_numeric_string(value)
    else:
        for (row0, col0), key in PARAMETER_CELL_MAP.items():
            _, tag = key.split(":", 1)
            value = read_cell(row0, col0)
            if value is not None:
                parameters[tag] = _normalize_numeric_string(value)

    return {"header": header, "extended": extended, "parameters": parameters}
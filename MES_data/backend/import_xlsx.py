"""Reverses the cell maps in export_xlsx.py so a filled-in 试模成型参数表
(.xlsx) can be read back into structured data for import.

This intentionally mirrors export_xlsx.py's approach: it reuses that
module's HEADER_CELL_MAP / EXTENDED_CELL_MAP / PARAMETER_CELL_MAP /
_HOT_RUNNER_ROW / _HOT_RUNNER_COLS / _MERGES so the two stay in sync --
any cell added to one side's map should be added to the other, and if
export_xlsx.py's maps ever change, this module picks up the change
automatically rather than needing a parallel edit.

Only cells listed in those maps are read; anything else on the sheet
(试模员/试模日期/审核/试模结果 defect checklist, etc.) is ignored, same
scope limitation the export side documents.
"""
from io import BytesIO
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from openpyxl import load_workbook

from .export_xlsx import (
    HEADER_CELL_MAP,
    EXTENDED_CELL_MAP,
    PARAMETER_CELL_MAP,
    _HOT_RUNNER_ROW,
    _HOT_RUNNER_COLS,
    _MERGES,
)

# Same anchor-cell lookup export_xlsx.py builds for writing -- needed here
# for reading too, since openpyxl only stores a value on the top-left cell
# of a merged range; every other cell in that range reads back as None.
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


def _read_cell(worksheet, row0: int, col0: int):
    anchor_row0, anchor_col0 = _ANCHOR_FOR.get((row0, col0), (row0, col0))
    value = worksheet.cell(row=anchor_row0 + 1, column=anchor_col0 + 1).value
    if value is None:
        return None
    if isinstance(value, str):
        value = value.strip()
    return value if value not in (None, "") else None


def parse_trial_parameter_workbook(file_bytes: bytes) -> dict:
    """Returns
    {
        "header": {"mold_code": ..., "mold_name": ..., "cavities": ...},
        "extended": {key: value, ...},
        "parameters": {tag: normalized_value_string, ...},
    }
    Every sub-dict only contains keys the sheet actually had a
    non-blank value for -- a blank cell means "leave whatever is
    already saved alone", never "clear it".
    """
    workbook = load_workbook(BytesIO(file_bytes), data_only=True)
    worksheet = workbook.active

    header: dict = {}
    for (row0, col0), key in HEADER_CELL_MAP.items():
        _, field = key.split(":", 1)
        value = _read_cell(worksheet, row0, col0)
        if value is not None:
            header[field] = value

    extended: dict = {}
    for (row0, col0), key in EXTENDED_CELL_MAP.items():
        _, field = key.split(":", 1)
        value = _read_cell(worksheet, row0, col0)
        if value is not None:
            extended[field] = value

    for offset, col0 in enumerate(_HOT_RUNNER_COLS):
        value = _read_cell(worksheet, _HOT_RUNNER_ROW, col0)
        if value is not None:
            extended[f"hot_runner_t{offset + 1}"] = value

    parameters: dict = {}
    for (row0, col0), key in PARAMETER_CELL_MAP.items():
        _, tag = key.split(":", 1)
        value = _read_cell(worksheet, row0, col0)
        if value is not None:
            parameters[tag] = _normalize_numeric_string(value)

    return {"header": header, "extended": extended, "parameters": parameters}
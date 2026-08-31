"""Label-driven reader for the 试模成型参数表 workbook.

Unlike PARAMETER_CELL_MAP in export_xlsx.py / import_xlsx.py (which reads
fixed (row, col) coordinates captured from one reference file), this
module finds each value by searching for the block's title text and its
row label text, then reading whichever column actually carries that
stage's data in the uploaded file. This survives an uploaded sheet that
has extra/missing rows or shifted columns relative to the built-in
template, as long as the block titles and row labels themselves read the
same (e.g. "射胶设定", "速度", "1段") -- which is guaranteed for this
single incoming format.

Core idea, matching the real layout observed in an uploaded .xls:

    row 11: 射胶设定±10﹪ | 1段  2段  3段  4段 | ... | 保压设定±10﹪ | 1段 2段 3段
    row 12:               速度 | 10.0 2.0  8.0
    row 13:               压力 | 160.0
    row 14:               位置 | 25.8 25.0 13.0
    row 15:               时间（S）| ...

- The block title ("射胶设定") and the stage header ("1段"/"2段"/...) sit
  in the SAME row.
- The row label ("速度"/"压力"/"位置") sits one column to the right of
  the block title's column, on each subsequent row.
- Data cells sit to the right of the row label, aligned under whichever
  stage-header column they belong to.

So instead of "value is always at (14, 2)", we ask: "find the row whose
label reads '速度' inside the 射胶设定 block, then find the column whose
header reads '1段', and read the cell at that intersection." A block
whose title cell drifted, or that gained an extra row, is still read
correctly as long as the label text itself didn't change.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import re


# ---------------------------------------------------------------------
# Text normalization -- the uploaded sheet's labels carry inconsistent
# whitespace, full-width punctuation, embedded newlines, and tolerance
# suffixes ("±10﹪" / "±10%"). Every label comparison goes through this
# so "射胶设定±10﹪", "射胶设定 ±10%", "射胶设定\n±10%" all match the same
# canonical key.
# ---------------------------------------------------------------------

_FULLWIDTH_DIGITS = str.maketrans("０１２３４５６７８９", "0123456789")

def normalize_label(text) -> str:
    if text is None:
        return ""
    text = str(text).translate(_FULLWIDTH_DIGITS)
    text = text.replace("\n", "").replace("\r", "")
    text = re.sub(r"[±\s]", "", text)
    text = re.sub(r"[（(][^）)]*[）)]", "", text)  # drop parenthetical units, e.g. "(秒)"
    text = re.sub(r"[±%％﹪]?\s*\d+\s*[%％﹪]", "", text)  # drop "±10%" / "10%" tolerance hints
    return text.strip()


_STAGE_RE = re.compile(r"^(\d+)\s*(段|级)$")

def stage_number(text) -> int | None:
    """Returns the stage number for a header cell like '1段' / '3级', or
    None if the cell isn't a stage-header cell at all."""
    if text is None:
        return None
    normalized = str(text).translate(_FULLWIDTH_DIGITS).strip()
    match = _STAGE_RE.match(normalized)
    return int(match.group(1)) if match else None


# ---------------------------------------------------------------------
# Block schema -- mirrors PARAMETER_GRID_BLOCKS in app.js / the original
# PARAMETER_CELL_MAP in export_xlsx.py, but expressed as label text
# instead of coordinates. Only blocks that were previously covered by
# PARAMETER_CELL_MAP are listed here; extending coverage later is just
# adding another BlockDef.
# ---------------------------------------------------------------------

@dataclass
class RowDef:
    label_aliases: tuple  # normalized label texts that identify this row
    tags_by_stage: dict   # {stage_number: tag}, e.g. {1: "IV1", 2: "IV2", ...}


@dataclass
class SimpleRowDef:
    """A row with no per-stage columns -- just 'label -> single value',
    read from the first non-blank cell to the right of the label."""
    label_aliases: tuple
    tag: str


@dataclass
class BlockDef:
    title_aliases: tuple
    rows: tuple = field(default_factory=tuple)
    simple_rows: tuple = field(default_factory=tuple)
    # How many columns to the right of the title cell to search for stage
    # headers / row data before giving up and assuming we've drifted into
    # a neighboring block. Generous on purpose -- the row-label search
    # below is what actually disambiguates, this is just a safety cap.
    max_width: int = 12
    # How many rows below the title row to search for this block's row
    # labels before giving up (a block whose rows never showed up isn't
    # searched forever).
    max_height: int = 10


BLOCK_DEFS: tuple[BlockDef, ...] = (
    BlockDef(
        title_aliases=("料温设定温度",),
        # 射嘴 has no backing tag (see export_xlsx.py comment) -- only
        # 1段..5段 are mapped.
        rows=(
            RowDef(("温度",), {1: "TS1", 2: "TS2", 3: "TS3", 4: "TS4", 5: "TS5"}),
        ),
    ),
    BlockDef(
        title_aliases=("射胶设定",),
        rows=(
            RowDef(("速度",), {1: "IV1", 2: "IV2", 3: "IV3", 4: "IV4", 5: "IV5"}),
            RowDef(("压力",), {1: "IP1", 2: "IP2", 3: "IP3", 4: "IP4", 5: "IP5"}),
            RowDef(("位置",), {1: "IS1", 2: "IS2", 3: "IS3", 4: "IS4", 5: "IS5"}),
        ),
        simple_rows=(
            SimpleRowDef(("射胶时间秒", "射胶时间"), "EPLST"),
            SimpleRowDef(("冷却时间S", "冷却时间"), "CT"),
        ),
    ),
    BlockDef(
        title_aliases=("保压",),
        rows=(
            RowDef(("速度",), {1: "PV1", 2: "PV2", 3: "PV3"}),
            RowDef(("压力",), {1: "PP1", 2: "PP2", 3: "PP3"}),
            RowDef(("时间S", "时间"), {1: "PT1", 2: "PT2", 3: "PT3"}),
        ),
    ),
    BlockDef(
        title_aliases=("锁模设定",),
        rows=(
            RowDef(("速度",), {1: "MCV1", 2: "MCV2", 3: "MCV3"}),
            RowDef(("压力",), {1: "MCP1", 2: "MCP2", 3: "MCP3"}),
            RowDef(("位置",), {1: "MCS1", 2: "MCS2", 3: "MCS3"}),
        ),
        simple_rows=(
            # "高压" is its own labeled column in this block rather than a
            # numbered stage -- treated as a simple row keyed by that
            # label text, mapped to the 5th (final) lock-clamp stage
            # (matches the machine panel's own "高压" = last stage
            # convention -- see export_xlsx.py comment).
            SimpleRowDef(("高压速度",), "MCV5"),
            SimpleRowDef(("高压压力",), "MCP5"),
            SimpleRowDef(("高压位置",), "MCS5"),
        ),
    ),
    BlockDef(
        title_aliases=("开模设定",),
        rows=(
            RowDef(("速度",), {1: "MOV1", 2: "MOV2", 3: "MOV3", 4: "MOV4"}),
            RowDef(("压力",), {1: "MOP1", 2: "MOP2", 3: "MOP3", 4: "MOP4"}),
            RowDef(("位置",), {1: "MOS1", 2: "MOS2", 3: "MOS3", 4: "MOS4"}),
        ),
    ),
    BlockDef(
        title_aliases=("顶出次数",),
        simple_rows=(
            SimpleRowDef(("顶出次数", "顶针次数"), "EJET"),
        ),
    ),
    BlockDef(
        title_aliases=("熔胶设定",),
        rows=(
            RowDef(("速度",), {1: "PLV1", 2: "PLV2", 3: "PLV3", 4: "PLV4"}),
            RowDef(("压力",), {1: "PLP1", 2: "PLP2", 3: "PLP3", 4: "PLP4"}),
            RowDef(("位置",), {1: "PLS1", 2: "PLS2", 3: "PLS3", 4: "PLS4"}),
            RowDef(("背压",), {1: "PLBP1", 2: "PLBP2", 3: "PLBP3", 4: "PLBP4"}),
        ),
        simple_rows=(
            SimpleRowDef(("熔胶时间S", "熔胶时间"), "EPLST"),
            SimpleRowDef(("周期S", "周期"), "ECYCT"),
        ),
    ),
)


# ---------------------------------------------------------------------
# Grid construction: resolve merged cells to their anchor value so every
# (row, col) inside a merge reads the same text/value the top-left cell
# holds, matching how the sheet visually reads.
# ---------------------------------------------------------------------

def build_resolved_grid(worksheet) -> list[list]:
    """worksheet: an openpyxl worksheet (data_only=True) or an xlrd sheet
    wrapped with a `.merged_cells`-like interface. Returns a dense
    row-major list-of-lists of cell values, with merged ranges expanded
    so every covered cell reads the anchor's value."""
    max_row = worksheet.max_row
    max_col = worksheet.max_column
    grid = [[None] * max_col for _ in range(max_row)]
    for row in worksheet.iter_rows():
        for cell in row:
            grid[cell.row - 1][cell.column - 1] = cell.value

    for merged_range in worksheet.merged_cells.ranges:
        anchor_value = grid[merged_range.min_row - 1][merged_range.min_col - 1]
        for r in range(merged_range.min_row - 1, merged_range.max_row):
            for c in range(merged_range.min_col - 1, merged_range.max_col):
                grid[r][c] = anchor_value

    return grid


def build_resolved_grid_xlrd(sheet) -> list[list]:
    """Same as build_resolved_grid but for an xlrd sheet (legacy .xls)."""
    grid = [[sheet.cell_value(r, c) if c < sheet.ncols else None for c in range(sheet.ncols)]
            for r in range(sheet.nrows)]
    for rlo, rhi, clo, chi in getattr(sheet, "merged_cells", []):
        anchor_value = grid[rlo][clo]
        for r in range(rlo, rhi):
            for c in range(clo, chi):
                if r < len(grid) and c < len(grid[r]):
                    grid[r][c] = anchor_value
    return grid


# ---------------------------------------------------------------------
# Label search primitives
# ---------------------------------------------------------------------

def _matches_any(cell_text, aliases: tuple) -> bool:
    normalized = normalize_label(cell_text)
    if not normalized:
        return False
    return any(normalized == normalize_label(alias) or normalize_label(alias) in normalized
               for alias in aliases)


def find_all_title_cells(grid, aliases: tuple):
    """Every (row, col) whose text matches one of `aliases` -- a block
    title can legitimately appear more than once if the sheet repeats a
    section (rare, but cheaper to support than to assume away)."""
    hits = []
    for r, row in enumerate(grid):
        for c, value in enumerate(row):
            if value is None or not isinstance(value, str):
                continue
            if _matches_any(value, aliases):
                hits.append((r, c))
    return hits


def _first_non_blank_after(grid, row: int, start_col: int, max_col: int):
    """First non-blank cell value at `row`, scanning columns
    [start_col, max_col) -- used for SimpleRowDef value extraction."""
    for c in range(start_col, min(max_col, len(grid[row]))):
        value = grid[row][c]
        if value not in (None, ""):
            return value
    return None


def _stage_columns_in_row(grid, row: int, start_col: int, end_col: int) -> dict:
    """{stage_number: column} for every stage-header cell found in
    `row` within [start_col, end_col)."""
    columns = {}
    for c in range(start_col, min(end_col, len(grid[row]))):
        stage = stage_number(grid[row][c])
        if stage is not None and stage not in columns:
            columns[stage] = c
    return columns


def _row_label_matches(grid, row: int, col: int, aliases: tuple) -> bool:
    if col >= len(grid[row]):
        return False
    return _matches_any(grid[row][col], aliases)


def scan_block(grid, block: BlockDef) -> dict:
    """Returns {tag: value} for every tag this block successfully
    located in `grid`. Silently yields fewer tags (never raises) if some
    rows/columns aren't found -- matches the existing "only write cells
    we're confident about" philosophy of the fixed-coordinate reader."""
    result = {}
    for tag, (r, c) in locate_block(grid, block).items():
        if r >= len(grid) or c >= len(grid[r]):
            continue
        value = grid[r][c]
        if value not in (None, ""):
            result[tag] = value
    return result


def locate_block(grid, block: BlockDef) -> dict:
    """Like scan_block, but returns {tag: (row0, col0)} -- the CELL
    POSITION each tag resolves to in this grid, regardless of whether
    that cell currently holds a value. This is what the write side
    (export_xlsx.overlay_values_onto_template) needs: it must know where
    to put a value (or blank a cell) even for a tag whose source data
    happens to be empty right now.

    Unlike scan_block, a row/simple-row is located as soon as its label
    is found -- there is no "value not in (None, '')" filter here, since
    an empty target cell is still a valid, real position to write to."""
    result: dict = {}
    title_hits = find_all_title_cells(grid, block.title_aliases)

    for title_row, title_col in title_hits:
        label_col = title_col + 1
        data_start_col = label_col + 1
        data_end_col = title_col + block.max_width
        row_search_end = min(len(grid), title_row + block.max_height)

        stage_columns = _stage_columns_in_row(grid, title_row, data_start_col, data_end_col)

        for row_def in block.rows:
            for r in range(title_row + 1, row_search_end):
                if not _row_label_matches(grid, r, label_col, row_def.label_aliases):
                    continue
                for stage, tag in row_def.tags_by_stage.items():
                    col = stage_columns.get(stage)
                    if col is None:
                        continue
                    result.setdefault(tag, (r, col))
                break

        for simple in block.simple_rows:
            for r in range(title_row, row_search_end):
                if not _row_label_matches(grid, r, label_col, simple.label_aliases):
                    continue
                # First cell to the right of the label -- mirrors
                # _first_non_blank_after's scan start, but we just need
                # *a* stable position, not necessarily a filled one.
                col = data_start_col
                result.setdefault(simple.tag, (r, col))
                break

    return result


def scan_all_blocks(grid) -> dict:
    """{tag: raw_value} across every BlockDef -- the label-driven
    replacement for reading PARAMETER_CELL_MAP by fixed coordinate.
    Later blocks never overwrite a tag already found by an earlier one,
    so an ambiguous duplicate title elsewhere in the sheet can't clobber
    a value already read correctly."""
    combined: dict = {}
    for block in BLOCK_DEFS:
        for tag, value in scan_block(grid, block).items():
            combined.setdefault(tag, value)
    return combined


def covered_tags() -> set:
    """Every tag BLOCK_DEFS knows how to locate by label (across all row
    types). Used by the write side to decide when it's safe to fall back
    to a fixed coordinate: a tag BLOCK_DEFS covers but couldn't locate on
    this particular sheet means "this block/stage genuinely isn't on the
    sheet", not "go guess a stale coordinate" -- falling back for those
    is what let a fixed fallback land inside an unrelated merged banner
    cell. Only tags BLOCK_DEFS has no opinion about at all should ever
    use the fixed PARAMETER_CELL_MAP coordinate."""
    tags = set()
    for block in BLOCK_DEFS:
        for row_def in block.rows:
            tags.update(row_def.tags_by_stage.values())
        for simple in block.simple_rows:
            tags.add(simple.tag)
    return tags


def locate_all_blocks(grid) -> dict:
    """{tag: (row0, col0)} across every BlockDef -- the write-side
    counterpart of scan_all_blocks. Used by
    export_xlsx.overlay_values_onto_template to find where each
    parameter tag's cell actually lives in an uploaded workbook, instead
    of assuming the fixed PARAMETER_CELL_MAP coordinates. Earlier blocks
    win on a duplicate tag, same precedence as scan_all_blocks."""
    combined: dict = {}
    for block in BLOCK_DEFS:
        for tag, pos in locate_block(grid, block).items():
            combined.setdefault(tag, pos)
    return combined
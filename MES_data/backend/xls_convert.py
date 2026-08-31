"""Converts a legacy .xls (BIFF / Excel 97-2003) workbook into an
equivalent .xlsx workbook, so it can be stored and overlaid the same way
an uploaded .xlsx/.xlsm 试模成型参数表 template already is (see
template_storage.py / export_xlsx.overlay_values_onto_template).

Without this, uploading a .xls template silently fell back to
generating a sheet from the built-in static template on export (see
import_trial_parameter_sheet in routers/export.py) -- POST .../import
only ever saved .xlsx/.xlsm uploads as templates, never .xls -- so a
machine's own .xls-based layout/branding was replaced by the generic
built-in template the very first time someone exported. Values parsed
out of the .xls were still saved correctly; only the visual template
was wrong.

Uses xls2xlsx (openpyxl under the hood) to do the actual conversion.
Some .xls files contain built-in Chinese/Asian-locale number-format
codes (BIFF format ids in the 27-36 / 50-58 / etc. ranges) that xlrd
cannot resolve to a format string -- xlrd leaves format_str as None for
these, which then crashes every downstream xls->xlsx writer (openpyxl,
xlwt) that assumes every number format has a string. These are patched
to a safe 'General' fallback before conversion; this only affects the
display format of a handful of built-in locale number formats, never
cell values or any other formatting (fonts, borders, merges, colors,
column widths all come through untouched).
"""
from io import BytesIO

from xls2xlsx import XLS2XLSX


def convert_xls_to_xlsx_bytes(content: bytes) -> bytes:
    """Returns .xlsx-format bytes equivalent to the given legacy .xls
    file's bytes, preserving text, merges, and formatting. Raises on
    files xls2xlsx genuinely cannot parse (e.g. a corrupted workbook, or
    one saved in the older BIFF5-and-earlier formats xlrd doesn't
    support) -- callers should catch and fall back to leaving the file
    un-templated, exactly as before this module existed."""
    converter = XLS2XLSX(content)

    # See module docstring -- patch unresolved built-in number formats
    # before generating the xlsx stylesheet, or openpyxl raises trying to
    # write a NumberFormat with formatCode=None.
    book = getattr(converter, "book", None)
    if book is not None:
        for number_format in book.format_map.values():
            if number_format.format_str is None:
                number_format.format_str = "General"

    workbook = converter.to_xlsx()
    buffer = BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()
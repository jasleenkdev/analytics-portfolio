"""openpyxl helpers: data sheets written as values, analysis sheets written as live formulas."""
from __future__ import annotations

import pandas as pd
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet

HEADER_FILL = PatternFill("solid", fgColor="1C5CAB")
HEADER_FONT = Font(bold=True, color="FFFFFF")
INPUT_FILL = PatternFill("solid", fgColor="FFF4D6")


def style_header(ws: Worksheet, row: int, n_cols: int) -> None:
    for c in range(1, n_cols + 1):
        cell = ws.cell(row=row, column=c)
        cell.fill, cell.font = HEADER_FILL, HEADER_FONT
        cell.alignment = Alignment(horizontal="center", wrap_text=True)


def write_frame(ws: Worksheet, df: pd.DataFrame, formats: dict | None = None) -> None:
    """Write a DataFrame as plain values from A1, with a styled header and frozen top row."""
    formats = formats or {}
    ws.append(list(df.columns))
    for row in df.itertuples(index=False):
        ws.append([None if (isinstance(v, float) and pd.isna(v)) else
                   (v.to_pydatetime() if isinstance(v, pd.Timestamp) else v) for v in row])
    style_header(ws, 1, len(df.columns))
    for i, col in enumerate(df.columns, start=1):
        if col in formats:
            for r in range(2, len(df) + 2):
                ws.cell(row=r, column=i).number_format = formats[col]
    ws.freeze_panes = "A2"
    autosize(ws)


def add_formula_column(ws: Worksheet, header: str, template: str, n_rows: int, number_format: str | None = None) -> str:
    """Append a column whose cells hold `template.format(r=row)`; returns the column letter."""
    col = ws.max_column + 1
    letter = get_column_letter(col)
    ws.cell(row=1, column=col, value=header)
    style_header(ws, 1, col)
    for r in range(2, n_rows + 2):
        cell = ws.cell(row=r, column=col, value=template.format(r=r))
        if number_format:
            cell.number_format = number_format
    autosize(ws)
    return letter


def col_of(ws: Worksheet, header: str) -> str:
    for cell in ws[1]:
        if cell.value == header:
            return cell.column_letter
    raise KeyError(header)


def autosize(ws: Worksheet) -> None:
    for col in ws.columns:
        width = max(len(str(c.value)) if c.value is not None and not str(c.value).startswith("=") else 8 for c in col)
        ws.column_dimensions[col[0].column_letter].width = min(max(10, width + 2), 48)

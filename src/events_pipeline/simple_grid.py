"""A minimal in-memory workbook that duck-types the small slice of the
openpyxl Worksheet/Workbook API that spreadsheet.py's business logic
(pending_feedback_rows, append_events, move_past_events_to_history, etc.)
actually uses: cell(row, column).value, max_row, iter_rows, append,
delete_rows, sheetnames, and indexing.

This lets sheets_store.py reuse every one of those functions completely
unchanged against a Google Sheets-backed grid instead of an openpyxl
Workbook — real formatting for the Sheets backend is applied separately,
in bulk, via sheets_client.apply_formatting(), so the styling calls those
functions make (column_dimensions, freeze_panes, auto_filter,
add_data_validation) are accepted here and simply ignored.
"""
from __future__ import annotations

from types import SimpleNamespace


class _Cell:
    __slots__ = ("_row", "_col")

    def __init__(self, row: list, col: int):
        self._row = row
        self._col = col  # 1-indexed

    @property
    def value(self):
        idx = self._col - 1
        return self._row[idx] if idx < len(self._row) else None

    @value.setter
    def value(self, new_value) -> None:
        idx = self._col - 1
        while len(self._row) <= idx:
            self._row.append(None)
        self._row[idx] = new_value

    def __setattr__(self, name, value):
        if name in ("_row", "_col", "value"):
            # "value" must reach object.__setattr__ so the `value` property's
            # setter actually runs — it's a data descriptor, not a plain attr.
            object.__setattr__(self, name, value)
        # anything else (fill, font, ...) is cosmetic styling meant for a
        # real spreadsheet backend and is silently accepted here.


class _ColumnDimensions(dict):
    def __missing__(self, key):
        dim = SimpleNamespace(hidden=False, width=None)
        self[key] = dim
        return dim


class SimpleSheet:
    def __init__(self, title: str = ""):
        self.title = title
        self.rows: list[list] = []
        self.column_dimensions = _ColumnDimensions()
        self.auto_filter = SimpleNamespace(ref=None)
        self.freeze_panes = None

    @property
    def max_row(self) -> int:
        return len(self.rows)

    def cell(self, row: int, column: int) -> _Cell:
        idx = row - 1
        while len(self.rows) <= idx:
            self.rows.append([])
        return _Cell(self.rows[idx], column)

    def append(self, values) -> None:
        self.rows.append(list(values))

    def iter_rows(self, min_row: int = 1, values_only: bool = False):
        for row in self.rows[min_row - 1 :]:
            if values_only:
                yield tuple(row)
            else:
                yield [_Cell(row, i + 1) for i in range(len(row))]

    def delete_rows(self, start: int, amount: int) -> None:
        del self.rows[start - 1 : start - 1 + amount]

    def add_data_validation(self, _dv) -> None:
        pass  # applied separately via sheets_client.apply_formatting


class SimpleWorkbook:
    def __init__(self):
        self._sheets: dict[str, SimpleSheet] = {}

    def create_sheet(self, title: str) -> SimpleSheet:
        sheet = SimpleSheet(title)
        self._sheets[title] = sheet
        return sheet

    def __getitem__(self, name: str) -> SimpleSheet:
        return self._sheets[name]

    def __contains__(self, name: str) -> bool:
        return name in self._sheets

    @property
    def sheetnames(self) -> list[str]:
        return list(self._sheets.keys())

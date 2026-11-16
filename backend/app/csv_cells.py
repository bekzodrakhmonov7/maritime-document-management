"""CSV cells a spreadsheet won't run: a cell that would start a formula is
prefixed with an apostrophe (CSV injection). Shared by every CSV the API writes."""

# A cell starting with one of these is a formula to a spreadsheet.
FORMULA_STARTS = ("=", "+", "-", "@", "\t", "\r")


def spreadsheet_safe(text: str) -> str:
    return f"'{text}" if text.startswith(FORMULA_STARTS) else text

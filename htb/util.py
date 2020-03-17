#!/usr/bin/env python3
from typing import List, Dict
from colorama import Style, Fore, Back
from cmd2.ansi import strip_style


def readuntil(f, delim: List[bytes]):
    result = []
    while True:
        b = f.read(1)
        if b == b"" or b in delim:
            break
        if b in delim:
            break
    return b"".join(result)


def build_table(data: List[List[str]], highlight=True) -> List[str]:
    """ Build an ASCII table for the terminal. Each item in headers and data can
    can start with "<", ">", or "^" to control justification. Column justification
    propogates to all cells in the column unless overridden. If highlight is true,
    column headers will use the `Style.BRIGHT` colorama style. """

    # Find number of rows and columns
    rows = len(data)
    columns = len(data[0])

    # Find widths of columns
    if columns > 1:
        padding = [1] + [2] * (columns - 1) + [1]
    else:
        padding = [1]

    width = [
        max([len(strip_style(data[r][c])) for r in range(rows)]) for c in range(columns)
    ]
    column_justify = []

    # Find column justification
    for c in range(columns):
        if len(data[0][c]) == 0 or data[0][c][0] not in "<>^":
            column_justify.append("<")
        else:
            column_justify.append(data[0][c][0])
            data[0][c] = data[0][c][1:]

    # Initialize output
    output = []

    # Build table
    for r in range(rows):
        row = []
        for c in range(columns):
            # Find correct justification
            if len(data[r][c]) > 0 and data[r][c][0] in "<>^":
                justify = data[r][c][0]
                data[r][c] = data[r][c][1:]
            else:
                justify = column_justify[c]

            # Highlight the headers if requested
            if highlight and r == 0:
                style = Style.BRIGHT
            else:
                style = ""

            w = width[c]
            placeholder = "A" * len(strip_style(data[r][c]))

            # Justify fake input to avoid issues with formatting
            row.append(f"{placeholder:{justify}{w}}")
            # Insert correct input after justification
            row[-1] = style + row[-1].replace(placeholder, data[r][c]) + Style.RESET_ALL

        # Build this row
        output.append(" ".join(row))

    return output

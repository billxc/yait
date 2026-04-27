"""Terminal kanban board renderer for yait."""

from __future__ import annotations


def render_board(issues: list, workflow: dict, terminal_width: int = 80) -> str:
    """Render a terminal kanban board, grouping issues by workflow status columns.

    Args:
        issues: List of Issue objects.
        workflow: Workflow dict with "statuses" key (list of status strings).
        terminal_width: Available terminal width in characters.

    Returns:
        Plain text string of the rendered board.
    """
    statuses = workflow.get("statuses", ["open", "closed"])
    num_cols = len(statuses)
    if num_cols == 0:
        return "(no statuses configured)"

    # Column width: divide terminal width evenly, account for separators
    # Each separator is " | " (3 chars) between columns
    separator_width = 3 * (num_cols - 1)
    usable_width = terminal_width - separator_width
    col_width = max(usable_width // num_cols, 20)

    # Group issues by status
    grouped: dict[str, list] = {s: [] for s in statuses}
    for issue in issues:
        if issue.status in grouped:
            grouped[issue.status].append(issue)

    # Build column headers
    headers = []
    for s in statuses:
        count = len(grouped[s])
        header = f"{s} ({count})"
        headers.append(header)

    # Build separator line
    sep_char = "\u2500"  # ─
    col_sep = "\u2502"   # │

    # Format a cell to fit column width
    def _pad(text: str) -> str:
        if len(text) > col_width:
            return text[: col_width - 1] + "\u2026"
        return text.ljust(col_width)

    lines = []

    # Header line
    header_parts = [_pad(h) for h in headers]
    lines.append((" " + col_sep + " ").join(header_parts))

    # Separator line
    sep_parts = [sep_char * col_width for _ in statuses]
    lines.append(col_sep.join(sep_parts))

    # Build card lines for each column
    def _format_card(issue) -> str:
        prefix = f"#{issue.id}"
        parts = [prefix]
        if issue.priority and issue.priority != "none":
            parts.append(f"[{issue.priority}]")
        # Remaining width for title
        used = sum(len(p) for p in parts) + len(parts)  # +spaces
        title_max = col_width - used
        title = issue.title
        if len(title) > title_max:
            title = title[: max(title_max - 1, 0)] + "\u2026"
        parts.append(title)
        return " ".join(parts)

    # Find max rows
    max_rows = max((len(grouped[s]) for s in statuses), default=0)
    if max_rows == 0:
        # All columns empty
        empty_parts = [_pad("(empty)") for _ in statuses]
        lines.append((" " + col_sep + " ").join(empty_parts))
    else:
        for row in range(max_rows):
            row_parts = []
            for s in statuses:
                col_issues = grouped[s]
                if row == 0 and len(col_issues) == 0:
                    row_parts.append(_pad("(empty)"))
                elif row < len(col_issues):
                    card = _format_card(col_issues[row])
                    row_parts.append(_pad(card))
                else:
                    row_parts.append(" " * col_width)
            lines.append((" " + col_sep + " ").join(row_parts))

    return "\n".join(lines)

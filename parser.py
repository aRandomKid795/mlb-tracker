"""
Parses pasted slip text into {slip_number: [(player, line), ...]}.

Expected format (matches how you paste them):

    Slip 1
    1. Player Name - More 5.5 Hitter Fantasy Score
    2. Another Player - More 3 Hitter Fantasy Score
    ...
    Slip 2
    ...

Robust to:
  - "More" / "Less" (records the side; grading currently assumes More/over)
  - line movement like "5.5 - 6" (takes the higher number)
  - accents and extra whitespace
"""

import re

SLIP_HEADER = re.compile(r"^\s*slip\s+(\d+)", re.IGNORECASE)
# captures: leg number, player name, side (More/Less), line (last number if range)
LEG_LINE = re.compile(
    r"^\s*\d+\.\s*(.+?)\s*-\s*(More|Less)\s+([\d.]+(?:\s*-\s*[\d.]+)?)",
    re.IGNORECASE,
)


def _parse_line_value(raw):
    """'5.5' -> 5.5 ; '5.5 - 6' -> 6.0 (take the higher/newer number)."""
    nums = [float(x) for x in re.findall(r"[\d.]+", raw)]
    return max(nums) if nums else None


def parse_slips(text):
    """
    Returns (slips, warnings).
    slips: {int: [(player, line_float), ...]}
    warnings: list of strings for lines that couldn't be parsed.
    """
    slips = {}
    warnings = []
    current = None

    for lineno, raw in enumerate(text.splitlines(), 1):
        if not raw.strip():
            continue
        header = SLIP_HEADER.match(raw)
        if header:
            current = int(header.group(1))
            slips[current] = []
            continue
        m = LEG_LINE.match(raw)
        if m:
            if current is None:
                warnings.append(f"Line {lineno}: leg before any 'Slip N' header — skipped.")
                continue
            player = m.group(1).strip()
            line_val = _parse_line_value(m.group(3))
            if line_val is None:
                warnings.append(f"Line {lineno}: couldn't read line number — skipped.")
                continue
            slips[current].append((player, line_val))
        else:
            # ignore anything that isn't a header or a leg (blank labels etc.)
            if raw.strip() and not raw.lower().strip().startswith("slip"):
                warnings.append(f"Line {lineno}: didn't match a leg — skipped: {raw.strip()[:60]}")

    # drop empty slips
    slips = {k: v for k, v in slips.items() if v}
    return slips, warnings

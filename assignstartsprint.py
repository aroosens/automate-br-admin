#!/usr/bin/env python3
import argparse
import csv
import sys
from pathlib import Path

def sniff_dialect(sample: str):
    sniffer = csv.Sniffer()
    try:
        # Try common delimiters: comma, semicolon, tab
        return sniffer.sniff(sample, delimiters=[",", ";", "\t"])
    except csv.Error:
        # Fallback to comma
        class Fallback(csv.Dialect):
            delimiter = ","
            quotechar = '"'
            doublequote = True
            skipinitialspace = False
            lineterminator = "\n"
            quoting = csv.QUOTE_MINIMAL
        return Fallback

def to_float_or_inf(v):
    try:
        return float(str(v).strip())
    except (ValueError, TypeError):
        return float("inf")

def parse_args():
    p = argparse.ArgumentParser(
        description="Sort CSV by Sprintnr (numeric) then Story, keeping one row per (Story,Sprintnr)."
    )
    p.add_argument("input", help="Path to input CSV")
    p.add_argument("-o", "--output", default="output.csv", help="Path to output CSV (required unless --dry-run)")
    p.add_argument("--encoding", default="utf-8-sig",
                   help="File encoding (default: utf-8-sig for Excel compatibility)")
    p.add_argument("--story-col", default="Story",
                   help="Story column name (default: Story)")
    p.add_argument("--sprint-col", default="Sprintnr",
                   help="Sprint column name (default: Sprintnr)")
    p.add_argument("--dry-run", action="store_true",
                   help="Preview only; do not write an output file")
    p.add_argument("--head", type=int, default=15,
                   help="Number of preview rows in dry-run (default: 15)")
    p.add_argument("--sep", choices=[",",";"], default=None,
                   help="Force delimiter (',' or ';'). If omitted, auto-detect.")
    p.add_argument("--normalize-story", action="store_true",
                   help="Trim and lowercase Story before dedup (treat 'CON-1' and 'con-1' as same)")
    return p.parse_args()

def main():
    args = parse_args()

    if not args.dry_run and not args.output:
        sys.exit("Error: --output is required unless you use --dry-run")

    # --- Read file, detect/force delimiter
    with open(args.input, "r", encoding=args.encoding, newline="") as f:
        sample = f.read(4096)
        f.seek(0)
        dialect = sniff_dialect(sample) if args.sep is None else type("Forced", (csv.Dialect,), {
            "delimiter": args.sep,
            "quotechar": '"',
            "doublequote": True,
            "skipinitialspace": False,
            "lineterminator": "\n",
            "quoting": csv.QUOTE_MINIMAL
        })
        reader = csv.DictReader(f, dialect=dialect)

        if reader.fieldnames is None:
            sys.exit("Error: No header row found.")

        fieldnames = reader.fieldnames[:]
        # Strip BOM if present on first header
        if fieldnames and fieldnames[0].startswith("\ufeff"):
            fieldnames[0] = fieldnames[0].lstrip("\ufeff")

        # Case-insensitive header resolution
        lower_map = {h.lower(): h for h in fieldnames}
        story_key  = lower_map.get(args.story_col.lower())
        sprint_key = lower_map.get(args.sprint_col.lower())
        if not story_key or not sprint_key:
            sys.exit(f"Error: Required columns not found. "
                     f"Have: {fieldnames}. Need: '{args.story_col}' and '{args.sprint_col}'.")

        rows = list(reader)

    # --- Optional normalization of Story (for dedup equivalence)
    def norm_story(s):
        s = "" if s is None else str(s)
        return s.strip().lower() if args.normalize_story else s.strip()

    # --- Sort: Sprintnr (numeric asc), then Story (case-insensitive asc)
    rows.sort(key=lambda r: (to_float_or_inf(r.get(sprint_key)),
                             norm_story(r.get(story_key)).lower()))

    # --- Deduplicate per (Story, Sprintnr): keep first after sort
    seen = set()
    unique_rows = []
    for r in rows:
        key = (norm_story(r.get(story_key)))
        if key in seen:
            continue
        seen.add(key)
        unique_rows.append({  # keep only the two columns we want to output
            "Story": r.get(story_key, ""),
            "Sprintnr": r.get(sprint_key, "")
        })

    total_in, total_out = len(rows), len(unique_rows)
    removed = total_in - total_out

    if args.dry_run:
        # Build a text preview
        # We'll render as a simple aligned table for the first N rows
        head = max(0, min(args.head, total_out))
        cols = ["Story", "Sprintnr"]
        preview_rows = unique_rows[:head]

        # Prepare columns to show: below command in case you want to keep all original columns
        # cols = fieldnames

        # Compute column widths
        def cell(r, c):
            v = r.get(c, "")
            return "" if v is None else str(v)
        widths = {c: max(len(c), *(len(cell(r,c)) for r in preview_rows)) for c in cols}

        # Header
        lines = []
        header_line = " | ".join(c.ljust(widths[c]) for c in cols)
        sep_line = "-+-".join("-"*widths[c] for c in cols)
        lines.append(header_line)
        lines.append(sep_line)

        # Rows
        for r in preview_rows:
            lines.append(" | ".join(cell(r, c).ljust(widths[c]) for c in cols))

        print("\n".join([
            f"[DRY-RUN] Sorted + deduplicated preview (first {head} of {total_out} rows)",
            *lines,
            "",
            f"Input rows:  {total_in}",
            f"Output rows: {total_out}",
            f"Removed dupes (by Story,Sprintnr): {removed}",
            f"Delimiter:   {'forced '+args.sep if args.sep else 'auto-detected'}",
            f"Encoding:    {args.encoding}",
            "(No file written)"
        ]))
        return

    # --- Persist output
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding=args.encoding, newline="") as out:
        # Write with the same delimiter used for reading (if forced, use that)
        out_dialect = dialect
        writer = csv.DictWriter(out, fieldnames=["Story", "Sprintnr"], dialect=out_dialect)
        writer.writeheader()
        writer.writerows(unique_rows)

    print(f"Wrote {total_out} rows to {out_path} (removed {removed} duplicates).")

if __name__ == "__main__":
    main()




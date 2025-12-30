
#!/usr/bin/env python3
import argparse
import csv
import os
import sys
from pathlib import Path

def sniff_dialect(sample: str):
    sniffer = csv.Sniffer()
    try:
        return sniffer.sniff(sample, delimiters=[",", ";", "\t"])
    except csv.Error:
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
        description="Sort by Sprintnr (numeric) then Story; keep unique (Story,Sprintnr); output only Story,Sprintnr."
    )
    p.add_argument("input", help="Path to input CSV (absolute path recommended)")
    p.add_argument("-o", "--output", default="output.csv", help="Path to output CSV (required unless --dry-run)")
    p.add_argument("--encoding", default="utf-8-sig", help="Encoding (default utf-8-sig)")
    p.add_argument("--sep", choices=[",",";"], default=None,
                   help="Force delimiter; if omitted, auto-detect.")
    p.add_argument("--story-col", default="Story", help="Story column name (default Story)")
    p.add_argument("--sprint-col", default="Sprintnr", help="Sprint column name (default Sprintnr)")
    p.add_argument("--dry-run", action="store_true", help="Preview only; do not write output")
    p.add_argument("--head", type=int, default=15, help="Rows to show in preview (default 15)")
    p.add_argument("--normalize-story", action="store_true",
                   help="Trim/lower Story before dedup (treat 'CON-1' and ' con-1 ' as same)")
    return p.parse_args()

def main():
    args = parse_args()

    in_path = Path(args.input).expanduser()
    if not in_path.is_absolute():
        in_path = (Path.cwd() / in_path).resolve()

    if not in_path.exists():
        here = Path.cwd()
        parent = in_path.parent
        try:
            listing = ", ".join(sorted(os.listdir(parent))[:50])
        except Exception:
            listing = "(unavailable)"
        sys.exit("\n".join([
            f"Error: Input file not found: {in_path}",
            f"Working directory: {here}",
            f"Parent directory: {parent}",
            f"Parent listing (first items): {listing}"
        ]))

    # --- Read & detect/force delimiter
    with open(in_path, "r", encoding=args.encoding, newline="") as f:
        sample = f.read(4096); f.seek(0)
        dialect = sniff_dialect(sample) if args.sep is None else type("Forced",(csv.Dialect,),{
            "delimiter": args.sep, "quotechar": '"', "doublequote": True,
            "skipinitialspace": False, "lineterminator": "\n", "quoting": csv.QUOTE_MINIMAL
        })
        reader = csv.DictReader(f, dialect=dialect)
        if reader.fieldnames is None:
            sys.exit("Error: No header row found in CSV.")
        fieldnames = reader.fieldnames[:]
        if fieldnames and fieldnames[0].startswith("\ufeff"):
            fieldnames[0] = fieldnames[0].lstrip("\ufeff")
        lower_map = {h.lower(): h for h in fieldnames}
        story_key  = lower_map.get(args.story_col.lower())
        sprint_key = lower_map.get(args.sprint_col.lower())
        if not story_key or not sprint_key:
            sys.exit(f"Error: Missing columns. Found {fieldnames}. "
                     f"Need '{args.story_col}' and '{args.sprint_col}'.")
        rows = list(reader)

    def norm_story(s):
        s = "" if s is None else str(s)
        return s.strip().lower() if args.normalize_story else s.strip()

    # Sort: Sprintnr (numeric asc), then Story (case-insensitive asc)
    rows.sort(key=lambda r: (to_float_or_inf(r.get(sprint_key)),
                             norm_story(r.get(story_key)).lower()))

    # Deduplicate per (Story, Sprintnr): keep first after sort
    seen = set()
    unique_rows = []
    for r in rows:
        key = (norm_story(r.get(story_key)), to_float_or_inf(r.get(sprint_key)))
        if key in seen:
            continue
        seen.add(key)
        unique_rows.append({  # keep only the two columns we want to output
            "Story": r.get(story_key, ""),
            "Sprintnr": r.get(sprint_key, "")
        })

    total_in  = len(rows)
    total_out = len(unique_rows)
    removed   = total_in - total_out

    if args.dry_run:
        head = max(0, min(args.head, total_out))
        # Build a small table of just Story and Sprintnr
        cols = ["Story", "Sprintnr"]
        def cell(row, c):
            v = row.get(c, "")
            return "" if v is None else str(v)
        widths = {c: max(len(c), *(len(cell(r,c)) for r in unique_rows[:head])) for c in cols}
        header = " | ".join(c.ljust(widths[c]) for c in cols)
        sep = "-+-".join("-"*widths[c] for c in cols)
        lines = [header, sep]
        for r in unique_rows[:head]:
            lines.append(" | ".join(cell(r,c).ljust(widths[c]) for c in cols))

        print("\n".join([
            f"[DRY-RUN] Preview (first {head} of {total_out}) from {in_path}",
            *lines, "",
            f"Input rows:  {total_in}",
            f"Output rows: {total_out}",
            f"Removed dupes (by Story,Sprintnr): {removed}",
            f"Delimiter:   {'forced '+args.sep if args.sep else 'auto-detected'}",
            f"Encoding:    {args.encoding}",
            "(No file written)"
        ]))
        return

    # Persist only Story,Sprintnr (and use the same delimiter as read)
    out_path = Path(args.output).expanduser()
    if not out_path.is_absolute():
        out_path = (Path.cwd() / out_path).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with open(out_path, "w", encoding=args.encoding, newline="") as out:
        writer = csv.DictWriter(out, fieldnames=["Story", "Sprintnr"], dialect=dialect)
        writer.writeheader()
        writer.writerows(unique_rows)

    print(f"Wrote {total_out} rows (Story,Sprintnr) to {out_path} (removed {removed} duplicates).")

if __name__ == "__main__":
    main()

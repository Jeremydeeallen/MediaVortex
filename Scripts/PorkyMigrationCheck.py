"""Diagnostic: classify T:-drive DB rows after porky/brain migration split.

Categories:
  ON_T       — file present at T:\... (porky content, DB correct)
  ON_U       — file is at U:\... (brain content, DB path needs updating)
  GONE       — file is at neither T: nor U: (cleaned-up shows, can be deleted)

The scanner only knows about T:\... paths. Files in ON_U would be deleted
from the DB by the scanner even though they're not actually gone — they
need path-correction first.
"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + "/..")
from Repositories.DatabaseManager import DatabaseManager


def main():
    dm = DatabaseManager()
    total = dm.DatabaseService.ExecuteQuery(
        "SELECT COUNT(*) AS n FROM MediaFiles WHERE SUBSTRING(FilePath, 1, 2) = 'T:'"
    )[0]['n']
    print(f"Total T: rows in DB: {total:,}")
    print()

    sample_size = 1000
    rows = dm.DatabaseService.ExecuteQuery(
        "SELECT FilePath FROM MediaFiles WHERE SUBSTRING(FilePath, 1, 2) = 'T:' "
        "ORDER BY random() LIMIT %s",
        (sample_size,)
    )

    on_t = on_u = gone = 0
    on_u_examples = []
    gone_examples = []
    sep = chr(92)

    for r in rows:
        p = r['filepath']
        if os.path.exists(p):
            on_t += 1
        else:
            # Try same path but on U:
            u_path = 'U:' + p[2:]
            if os.path.exists(u_path):
                on_u += 1
                if len(on_u_examples) < 5:
                    on_u_examples.append((p, u_path))
            else:
                gone += 1
                if len(gone_examples) < 5:
                    gone_examples.append(p)

    n = len(rows)
    print(f"Sample of {n} random T: rows:")
    print(f"  ON_T  (still at original path)         : {on_t:5}  ({on_t/n*100:5.1f}%)")
    print(f"  ON_U  (moved to brain mount, needs re-path) : {on_u:5}  ({on_u/n*100:5.1f}%)")
    print(f"  GONE  (truly cleaned up)               : {gone:5}  ({gone/n*100:5.1f}%)")
    print()
    print(f"Projection across {total:,} rows:")
    print(f"  ON_T  ~{int(total * on_t / n):,}")
    print(f"  ON_U  ~{int(total * on_u / n):,}  <-- these need path correction before scan")
    print(f"  GONE  ~{int(total * gone / n):,}  <-- these would be deleted by scan (correct cleanup)")
    if on_u_examples:
        print()
        print("ON_U examples (need to be re-pathed T: -> U:):")
        for t, u in on_u_examples:
            print(f"  was: {t}")
            print(f"  is:  {u}")
            print()
    if gone_examples:
        print("GONE examples (truly absent, scanner cleanup is correct):")
        for p in gone_examples:
            print(f"  {p}")


if __name__ == "__main__":
    main()

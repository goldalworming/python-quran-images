#!/usr/bin/env python3
"""
migrate_v2.py – build quran_v2.db from the OFFICIAL KFGQPC v2 sources.

Inputs (both downloaded from qul.tarteel.ai):

  qpc-v2-15-lines.db/qpc-v2-15-lines.db
    – per-page line breaks, line_type ∈ {'surah_name','basmallah','ayah'},
      is_centered flag, first_word_id..last_word_id range per ayah line.

  qpc-v2.db/qpc-v2.db
    – words table: (id, location, surah, ayah, word, text).
      text is 1–3 PUA chars (the QCF2 glyph(s) for the word).

Output: quran_v2.db with the same schema as before:

  pages(page_number, line_number, position, line_type,
        font_file, glyph_code, surah_number, is_centered)
  words(word_id, page_number, line_number, position,
        sura_number, ayah_number, word_position,
        arabic_text, glyph_code, font_file)
  page_bboxes(...)
"""

import argparse
import os
import sqlite3
import sys
from pathlib import Path

HERE             = Path(__file__).resolve().parent
PAGES_DB         = HERE / "qpc-v2-15-lines.db" / "qpc-v2-15-lines.db"
WORDS_DB         = HERE / "qpc-v2.db"           / "qpc-v2.db"
DEFAULT_OUT      = HERE / "quran_v2.db"

BSML_FONT        = "QCF2BSML.ttf"

# QCF2BSML.ttf PUA codepoints for basmala (verified: ﭑﭒﭓ = U+FB51..U+FB53)
BASMALA_CODES    = [0xFB51, 0xFB52, 0xFB53]


def surah_name_code(n: int) -> int:
    """QCF2BSML.ttf surah-name PUA codepoint for surah N (1..114).

    Verified empirically: surah names occupy a logically-contiguous range
    that skips a cmap gap between U+FBB1 and U+FBD3.
        N = 1..37  -> 0xFB8D..0xFBB1
        N = 38..114-> 0xFBD3..0xFC1F
    """
    if 1 <= n <= 37:
        return 0xFB8C + n
    if 38 <= n <= 114:
        return 0xFBAD + n
    raise ValueError(f"surah_number out of range: {n}")

SCHEMA = """
CREATE TABLE pages (
  page_number   INTEGER NOT NULL,
  line_number   INTEGER NOT NULL,
  position      INTEGER NOT NULL,
  line_type     TEXT    NOT NULL,
  font_file     TEXT,
  glyph_code    INTEGER,
  surah_number  INTEGER,
  is_centered   INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (page_number, line_number, position)
);
CREATE INDEX idx_pages_pn ON pages(page_number);

CREATE TABLE words (
  word_id        INTEGER PRIMARY KEY AUTOINCREMENT,
  page_number    INTEGER NOT NULL,
  line_number    INTEGER NOT NULL,
  position       INTEGER NOT NULL,
  sura_number    INTEGER NOT NULL,
  ayah_number    INTEGER NOT NULL,
  word_position  INTEGER NOT NULL,
  arabic_text    TEXT,
  glyph_code     INTEGER NOT NULL,
  font_file      TEXT    NOT NULL
);
CREATE INDEX idx_words_loc  ON words(sura_number, ayah_number, word_position);
CREATE INDEX idx_words_page ON words(page_number);

CREATE TABLE page_bboxes (
  page_number INTEGER NOT NULL,
  line_number INTEGER NOT NULL,
  position    INTEGER NOT NULL,
  img_width   INTEGER NOT NULL,
  min_x INTEGER, max_x INTEGER, min_y INTEGER, max_y INTEGER,
  PRIMARY KEY (page_number, line_number, position, img_width)
);
"""


def migrate(out_path: Path):
    if not PAGES_DB.exists():
        print(f"ERROR: {PAGES_DB} not found.", file=sys.stderr)
        sys.exit(1)
    if not WORDS_DB.exists():
        print(f"ERROR: {WORDS_DB} not found.", file=sys.stderr)
        sys.exit(1)

    if out_path.exists():
        print(f"Removing existing {out_path}")
        out_path.unlink()

    conn = sqlite3.connect(str(out_path))
    conn.execute("PRAGMA journal_mode = MEMORY")
    conn.execute("PRAGMA synchronous = OFF")
    conn.executescript(SCHEMA)

    pages_src = sqlite3.connect(str(PAGES_DB))
    words_src = sqlite3.connect(str(WORDS_DB))

    # Pre-load all words for fast random access.
    words_map = {}    # id → (location, surah, ayah, word_idx, text)
    for r in words_src.execute("SELECT id, location, surah, ayah, word, text FROM words"):
        words_map[r[0]] = r[1:]

    # The last word of each ayah is the rosette end-marker.
    max_word_for_ayah = {}    # (surah, ayah) → max word_position
    for (_loc, surah, ayah, word_idx, _text) in words_map.values():
        key = (surah, ayah)
        if word_idx > max_word_for_ayah.get(key, 0):
            max_word_for_ayah[key] = word_idx

    n_glyphs = n_words = n_skipped = 0

    # Iterate pages in order.
    for page_num in range(1, 605):
        page_font = f"QCF2{page_num:03d}.ttf"
        lines = pages_src.execute(
            "SELECT line_number, line_type, is_centered, "
            "       first_word_id, last_word_id, surah_number "
            "FROM pages WHERE page_number=? ORDER BY line_number",
            (page_num,),
        ).fetchall()

        for ln_num, ltype, centered, first_w, last_w, surah_num in lines:

            if ltype == "surah_name":
                # Two glyphs: position 1 = "سُورَةُ" prefix (rightmost in RTL),
                # position 2 = the surah name (leftmost).
                name_code = surah_name_code(int(surah_num))
                for pos, code in [(1, 0xFB8C), (2, name_code)]:
                    conn.execute(
                        "INSERT INTO pages "
                        "(page_number, line_number, position, line_type, "
                        " font_file, glyph_code, surah_number, is_centered) "
                        "VALUES (?, ?, ?, 'sura', ?, ?, ?, ?)",
                        (page_num, ln_num, pos, BSML_FONT, code,
                         int(surah_num), centered),
                    )
                    n_glyphs += 1

            elif ltype == "basmallah":
                for i, cp in enumerate(BASMALA_CODES):
                    conn.execute(
                        "INSERT INTO pages "
                        "(page_number, line_number, position, line_type, "
                        " font_file, glyph_code, surah_number, is_centered) "
                        "VALUES (?, ?, ?, 'bismillah', ?, ?, NULL, ?)",
                        (page_num, ln_num, i + 1, BSML_FONT, cp, centered),
                    )
                    n_glyphs += 1

            elif ltype == "ayah":
                if not isinstance(first_w, int) or not isinstance(last_w, int):
                    print(f"[warn] page {page_num} L{ln_num} ayah missing word ids")
                    n_skipped += 1
                    continue

                # Position 1 = rightmost (first in RTL reading) — i.e., the
                # word with the SMALLEST word_id in the official range.
                pos = 1
                for wid in range(first_w, last_w + 1):
                    rec = words_map.get(wid)
                    if rec is None:
                        print(f"[warn] missing word_id {wid} (page {page_num} L{ln_num})")
                        continue
                    location, sura, ayah, word_idx, text = rec
                    # Each `text` is 1–3 PUA glyphs.
                    if not text:
                        continue
                    is_marker = (word_idx == max_word_for_ayah.get((sura, ayah), 0))
                    glyph_line_type = "ayah_marker" if is_marker else "ayah"
                    word_first_pos = pos  # position of this word's first/rightmost glyph
                    for ch in text:
                        conn.execute(
                            "INSERT INTO pages "
                            "(page_number, line_number, position, line_type, "
                            " font_file, glyph_code, surah_number, is_centered) "
                            "VALUES (?, ?, ?, ?, ?, ?, NULL, ?)",
                            (page_num, ln_num, pos, glyph_line_type,
                             page_font, ord(ch), centered),
                        )
                        pos += 1
                        n_glyphs += 1
                    # Record word entry (one per word_id).
                    conn.execute(
                        "INSERT INTO words "
                        "(page_number, line_number, position, "
                        " sura_number, ayah_number, word_position, "
                        " arabic_text, glyph_code, font_file) "
                        "VALUES (?, ?, ?, ?, ?, ?, NULL, ?, ?)",
                        (page_num, ln_num, word_first_pos,
                         sura, ayah, word_idx,
                         ord(text[0]), page_font),
                    )
                    n_words += 1
            else:
                print(f"[warn] page {page_num} L{ln_num} unknown line_type={ltype!r}")
                n_skipped += 1

    conn.commit()

    counts = {}
    for tbl in ("pages", "words", "page_bboxes"):
        (n,) = conn.execute(f"SELECT COUNT(*) FROM {tbl}").fetchone()
        counts[tbl] = n
    conn.close()
    pages_src.close()
    words_src.close()

    print(f"\nMigration done:")
    print(f"  glyphs inserted: {n_glyphs}")
    print(f"  words inserted:  {n_words}")
    print(f"  skipped lines:   {n_skipped}")
    print(f"  row counts:      {counts}")


def main():
    p = argparse.ArgumentParser(description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--out", type=Path, default=DEFAULT_OUT,
                   help=f"Output SQLite path (default: {DEFAULT_OUT})")
    args = p.parse_args()
    migrate(args.out)


if __name__ == "__main__":
    main()

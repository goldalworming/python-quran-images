"""SQLite-backed access layer for the QPC v2 Quran data."""

import os
import sqlite3


class QuranDBv2:
    def __init__(self, db_path: str):
        if not os.path.exists(db_path):
            raise RuntimeError(
                f"SQLite database not found at {db_path!r}. "
                f"Run `python migrate_v2.py` first."
            )
        self._conn = sqlite3.connect(db_path)
        self._conn.row_factory = sqlite3.Row
        cur = self._conn.execute("SELECT 1 FROM pages LIMIT 1")
        if cur.fetchone() is None:
            raise RuntimeError(f"Database {db_path!r} is empty.")

    def clear_page_bboxes(self, page_numbers):
        placeholders = ",".join(["?"] * len(page_numbers))
        self._conn.execute(
            f"DELETE FROM page_bboxes WHERE page_number IN ({placeholders})",
            list(page_numbers),
        )
        self._conn.commit()

    def get_page_lines(self, page_number):
        """
        Return a list of line dicts. Each line:
            {
                'line_number': int,
                'type': 'sura' | 'bismillah' | 'ayah',
                'font_file': str,            # primary font on the line
                'surah_number': int | None,  # only for sura lines
                'is_centered': bool,
                'glyphs': [
                    {'page_line_id': '<page>_<line>_<position>',
                     'line_number': int,
                     'position': int,
                     'font_file': str,
                     'glyph_code': int,
                     'glyph_id': str,          # uniquely identifies the glyph instance
                     'glyph_type': 'sura' | 'bismillah' | 'ayah'},
                    ...
                ]
            }
        Glyphs are ordered by position DESC (rightmost first, matching v1).
        """
        sql = """
            SELECT page_number, line_number, position, line_type,
                   font_file, glyph_code, surah_number, is_centered
            FROM pages
            WHERE page_number = ?
            ORDER BY line_number ASC, position DESC
        """
        cur = self._conn.execute(sql, (page_number,))
        rows = [dict(r) for r in cur.fetchall()]

        lines = {}
        for row in rows:
            ln = row["line_number"]
            if ln not in lines:
                lines[ln] = {
                    "line_number": ln,
                    "type": row["line_type"],
                    "font_file": row["font_file"],
                    "surah_number": row["surah_number"],
                    "is_centered": bool(row["is_centered"]),
                    "glyphs": [],
                }
            page_line_id = f'{row["page_number"]}_{row["line_number"]}_{row["position"]}'
            lines[ln]["glyphs"].append({
                "page_line_id": page_line_id,
                "line_number":  row["line_number"],
                "position":     row["position"],
                "font_file":    row["font_file"],
                "glyph_code":   row["glyph_code"],
                "glyph_id":     f'{row["font_file"]}_{row["glyph_code"]}' if row["glyph_code"] else None,
                "glyph_type":   row["line_type"],
            })

        return list(lines.values())

    def set_page_line_bbox(self, page_line_id, img_width, min_x, max_x, min_y, max_y):
        """page_line_id is the synthetic '{page}_{line}_{position}' string."""
        page, line, pos = (int(x) for x in page_line_id.split("_"))
        self._conn.execute(
            "INSERT OR REPLACE INTO page_bboxes "
            "(page_number, line_number, position, img_width, "
            " min_x, max_x, min_y, max_y) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (page, line, pos, img_width, min_x, max_x, min_y, max_y),
        )
        self._conn.commit()

    def get_words_for_page(self, page_number):
        """
        Return word rows for tajwid lookup. Each row:
            {glyph_id, sura_number, ayah_number, word_pos, arabic_text}
        """
        sql = """
            SELECT page_number, line_number, position,
                   sura_number, ayah_number, word_position AS word_pos,
                   arabic_text, glyph_code, font_file
            FROM words
            WHERE page_number = ?
            ORDER BY sura_number ASC, ayah_number ASC, word_position ASC
        """
        cur = self._conn.execute(sql, (page_number,))
        out = []
        for r in cur.fetchall():
            d = dict(r)
            d["glyph_id"] = f'{d["font_file"]}_{d["glyph_code"]}'
            out.append(d)
        return out

    def offset_page_bboxes(self, page_number, img_width, dx, dy):
        self._conn.execute(
            "UPDATE page_bboxes "
            "SET min_x = min_x + ?, max_x = max_x + ?, "
            "    min_y = min_y + ?, max_y = max_y + ? "
            "WHERE page_number = ? AND img_width = ?",
            (dx, dx, dy, dy, page_number, img_width),
        )
        self._conn.commit()

    def close(self):
        self._conn.close()

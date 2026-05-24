"""
Quran page image generator for QPC v2 — adapted from v1 generator.py.

Differences from v1:
- New DB schema (pages table) with all per-glyph rows in one place.
- Per-page fonts named QCF2NNN.ttf (lowercase); BSML font is QCF2BSML.ttf.
- Surah-header rendering: ornament only (sura-name glyph mapping TBD).
"""

import json
import math
import os

from PIL import Image, ImageChops, ImageDraw, ImageFont

from src.db import QuranDBv2
from src.tajwid import build_tajwid_map, letter_count

PHI = (math.sqrt(5) + 1) / 2  # golden ratio ≈ 1.618

FONT_DIR     = os.path.join(os.path.dirname(__file__), "..", "res", "fonts")
FONT_DEFAULT = os.path.join(FONT_DIR, "QCF2BSML.ttf")

# Tentative ornament glyph code in QCF2BSML.ttf (widest glyph in cmap).
# Verified empirically: U+FC20 has width 16384, by far the widest = full-line ornament box.
ORNAMENT_HEADER_BOX = 0xFC20

BLACK = (0, 0, 0, 255)
SURA_GREEN = (37, 99, 75, 255)
SURA_GREEN_BG = (240, 253, 244, 255)  # tailwind green-50
PAGE_BG = (0xFD, 0xFC, 0xF8)  # cream paper background


def _font_path(font_file: str) -> str:
    path = os.path.join(FONT_DIR, font_file)
    if not os.path.exists(path):
        return FONT_DEFAULT
    return path


_font_cache: dict = {}


def _get_font(font_file: str, ptsize: int) -> ImageFont.FreeTypeFont:
    key = (font_file, ptsize)
    if key not in _font_cache:
        _font_cache[key] = ImageFont.truetype(_font_path(font_file), size=ptsize)
    return _font_cache[key]


def _get_metrics(font_file: str, ptsize: int, default_font):
    font = _get_font(font_file, ptsize)
    return font.getmetrics()  # (ascent, descent) = (char_up, char_down)


def _glyph_bbox(font: ImageFont.FreeTypeFont, code: int):
    text = chr(code)
    try:
        left, top, right, bottom = font.getbbox(text, anchor="ls")
    except Exception:
        left, top, right, bottom = 0, 0, 0, 0
    return left, right, top, bottom


def _glyph_advance(font: ImageFont.FreeTypeFont, code: int) -> float:
    """Horizontal advance width — may be 0 for combining/overlay glyphs
    whose visual bbox is larger than the cursor advance."""
    try:
        return float(font.getlength(chr(code)))
    except Exception:
        return 0.0


class PageGeneratorV2:
    def __init__(self, db: QuranDBv2, tajwid: bool = False):
        self._db = db
        self._tajwid = tajwid
        self.anchor_map = {}
        if tajwid:
            try:
                with open("tajweed_anchors.json", "r") as f:
                    self.anchor_map = json.load(f)
            except FileNotFoundError:
                pass

    def generate(self, pages, width, output):
        os.makedirs(output, exist_ok=True)
        valid_pages = [p for p in pages if 1 <= p <= 604]
        if valid_pages:
            self._db.clear_page_bboxes(valid_pages)

        for page_num in reversed(valid_pages):
            print(f"Page: {page_num}")
            image = self._create(page_num, width)
            out_path = os.path.join(output, f"{page_num}.png")
            image.save(out_path, "PNG", compress_level=9)

    def _create(self, page_number, width):
        # v2 fonts are visually narrower than v1 — use a smaller divisor
        # so the natural line width fills more of the page.
        fontfactor = 18.0
        fontdelta = 1.0

        page_width  = width
        page_height = int(width * PHI * fontdelta)
        ptsize      = int(width / fontfactor)
        margin_top  = ptsize / 2.0
        coord_y     = margin_top

        image = Image.new("RGBA", (page_width, page_height), (255, 255, 255, 0))
        draw = ImageDraw.Draw(image)
        default_font = ImageFont.truetype(FONT_DEFAULT, size=ptsize)

        if self._tajwid:
            word_rows = self._db.get_words_for_page(page_number)
            tajwid_info = build_tajwid_map(word_rows)
        else:
            tajwid_info = {}

        lines = self._db.get_page_lines(page_number)

        for line in lines:
            line_font_file = line["font_file"] or "QCF2BSML.ttf"
            line_font = _get_font(line_font_file, ptsize)
            char_up, char_down = _get_metrics(line_font_file, ptsize, default_font)

            glyphs = line["glyphs"]

            # Pre-pass: line width + ink extent.
            line_max_x = 0
            actual_min_y = 0
            actual_max_y = 0
            for g in glyphs:
                if g["glyph_code"] is None:
                    continue
                gf = _get_font(g["font_file"] or line_font_file, ptsize)
                _, gm_x, g_min_y, g_max_y = _glyph_bbox(gf, g["glyph_code"])
                line_max_x   += _glyph_advance(gf, g["glyph_code"])
                actual_min_y  = min(actual_min_y, g_min_y)
                actual_max_y  = max(actual_max_y, g_max_y)

            actual_line_height = actual_max_y - actual_min_y
            line_min_y = actual_min_y if actual_min_y < 0 else -char_up
            line_coord_x = (page_width - line_max_x) / 2.0
            per_gap_extra = 0

            if coord_y <= margin_top and line_min_y < 0:
                coord_y -= line_min_y

            # Sura-header ornament.
            orn_center_y = None
            orn_bottom_y = None
            if line["type"] == "sura":
                orn_center_y, orn_bottom_y = self._render_ornament(
                    draw, page_width, coord_y, ptsize, margin_top, char_up,
                    line.get("surah_number"),
                )

            # Render glyphs.
            page_coord_x = None
            previous_w = 0

            for g in glyphs:
                if g["glyph_code"] is None:
                    continue  # 'sura' placeholder row — name rendering deferred
                gf = _get_font(g["font_file"] or line_font_file, ptsize)
                g_min_x, g_max_x, g_min_y, g_max_y = _glyph_bbox(gf, g["glyph_code"])

                if page_coord_x is None:
                    page_coord_x = line_coord_x
                else:
                    page_coord_x = page_coord_x + previous_w + per_gap_extra
                previous_w = _glyph_advance(gf, g["glyph_code"])

                use_coord_y = coord_y
                if line["type"] == "sura" and orn_center_y is not None:
                    glyph_ink_mid = (g_min_y + g_max_y) / 2.0
                    use_coord_y = orn_center_y - glyph_ink_mid

                if g["glyph_type"] == "ayah_marker":
                    self._draw_ayah_marker(
                        image, draw, gf, g["glyph_code"],
                        page_coord_x, use_coord_y,
                        g_min_x, g_max_x, g_min_y, g_max_y,
                    )
                else:
                    self._draw_glyph(
                        image, draw, gf,
                        g["glyph_id"], g["glyph_code"],
                        page_coord_x, use_coord_y,
                        tajwid_info.get(g["glyph_id"]),
                    )

                if line["type"] in ("ayah", "bismillah"):
                    min_x = int(page_coord_x + g_min_x)
                    max_x = int(min_x + (g_max_x - g_min_x) + 0.5)
                    min_y = int(use_coord_y + g_min_y)
                    max_y = int(min_y + (g_max_y - g_min_y) + 0.5)
                    self._db.set_page_line_bbox(
                        g["page_line_id"], page_width,
                        min_x, max_x, min_y, max_y,
                    )

            # Line advance.
            if line["type"] == "sura":
                # Move below the ornament instead of using font metrics.
                if orn_bottom_y is not None:
                    coord_y = orn_bottom_y + 1.1 * ptsize
                else:
                    coord_y += char_up
            elif line["type"] == "bismillah":
                # Basmala glyphs in QCF2BSML are tall — use measured ink
                # height plus a gap to prevent overlap with the next line.
                coord_y += actual_line_height + 0.8 * ptsize
            else:
                coord_y -= char_down
                coord_y += 2 * char_up

        # Centre content on canvas.
        content_bbox = image.getbbox()
        background = Image.new("RGB", image.size, PAGE_BG)

        if content_bbox:
            cl, ct, cr, cb = content_bbox
            cw = cr - cl
            ch = cb - ct
            paste_x = (page_width - cw) // 2
            paste_y = (page_height - ch) // 2
            content = image.crop(content_bbox)
            background.paste(content, (paste_x, paste_y), mask=content.split()[3])
            dx = paste_x - cl
            dy = paste_y - ct
            if dx != 0 or dy != 0:
                self._db.offset_page_bboxes(page_number, page_width, dx, dy)
        else:
            background.paste(image, mask=image.split()[3])

        self._draw_edge_marker(background, page_number)

        return background

    def _draw_edge_marker(self, background, page_number):
        """Three thin gray vertical lines full-height on the outer edge:
        right for odd pages, left for even. Innermost line at page_width*0.04
        from the edge, two more spaced outward toward the page edge."""
        page_width, page_height = background.size
        inner_margin = int(page_width * 0.02)
        gap = max(4, int(page_width * 0.008))
        offsets = [inner_margin, inner_margin - gap, inner_margin - 2 * gap]
        draw = ImageDraw.Draw(background)
        for off in offsets:
            x = page_width - off if page_number % 2 == 1 else off
            draw.line([(x, 0), (x, page_height - 1)], fill=(160, 160, 160), width=1)

    def _draw_ayah_marker(self, image, draw, font, glyph_code,
                          anchor_x, anchor_y,
                          g_min_x, g_max_x, g_min_y, g_max_y):
        """Render the ayah end-of-verse rosette with three colours:
        outline = dark green, fill = light green, digit = black.

        The PUA glyph contains both the rosette outline and the digit
        as ink. We separate them by connected-component analysis:
        components that touch the bbox edge are the outline; interior
        components are the digit. The bbox interior (everything inside
        the outline including digit holes) is filled with light green.
        """
        glyph_char = chr(glyph_code)
        pad = 2
        bbox_w = int(g_max_x - g_min_x + 2 * pad)
        bbox_h = int(g_max_y - g_min_y + 2 * pad)
        if bbox_w <= 0 or bbox_h <= 0:
            draw.text((anchor_x, anchor_y), glyph_char,
                      font=font, fill=SURA_GREEN, anchor="ls")
            return

        # Anti-aliased grayscale render of the glyph.
        gray = Image.new("L", (bbox_w, bbox_h), 0)
        ImageDraw.Draw(gray).text(
            (-g_min_x + pad, -g_min_y + pad),
            glyph_char, font=font, fill=255, anchor="ls",
        )
        # Binary mask (any ink at all).
        bin_mask = gray.point(lambda v: 255 if v > 0 else 0)

        # Flood from corners across non-ink pixels = exterior background.
        from collections import deque
        bpx = bin_mask.load()
        outside = Image.new("L", (bbox_w, bbox_h), 0)
        opx = outside.load()
        q = deque()
        for sx, sy in [(0, 0), (bbox_w - 1, 0),
                       (0, bbox_h - 1), (bbox_w - 1, bbox_h - 1)]:
            if bpx[sx, sy] == 0 and opx[sx, sy] == 0:
                opx[sx, sy] = 255
                q.append((sx, sy))
        while q:
            x, y = q.popleft()
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                nx, ny = x + dx, y + dy
                if 0 <= nx < bbox_w and 0 <= ny < bbox_h:
                    if bpx[nx, ny] == 0 and opx[nx, ny] == 0:
                        opx[nx, ny] = 255
                        q.append((nx, ny))

        # Connected components of ink, label as "outline" if touches the
        # bbox edge (within `pad`) — otherwise it's interior (= digit).
        label = [[0] * bbox_w for _ in range(bbox_h)]  # 0=unvisited, 1=outline, 2=digit
        for sy in range(bbox_h):
            for sx in range(bbox_w):
                if bpx[sx, sy] != 0 and label[sy][sx] == 0:
                    pixels = []
                    touches_edge = False
                    label[sy][sx] = -1  # in-progress
                    q.append((sx, sy))
                    while q:
                        x, y = q.popleft()
                        pixels.append((x, y))
                        if x <= pad or y <= pad or x >= bbox_w - 1 - pad or y >= bbox_h - 1 - pad:
                            touches_edge = True
                        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                            nx, ny = x + dx, y + dy
                            if 0 <= nx < bbox_w and 0 <= ny < bbox_h:
                                if bpx[nx, ny] != 0 and label[ny][nx] == 0:
                                    label[ny][nx] = -1
                                    q.append((nx, ny))
                    tag = 1 if touches_edge else 2
                    for x, y in pixels:
                        label[y][x] = tag

        outline_mask = Image.new("L", (bbox_w, bbox_h), 0)
        digit_mask = Image.new("L", (bbox_w, bbox_h), 0)
        olp = outline_mask.load()
        dgp = digit_mask.load()
        gpx = gray.load()
        for y in range(bbox_h):
            row_label = label[y]
            for x in range(bbox_w):
                if row_label[x] == 1:
                    olp[x, y] = gpx[x, y]
                elif row_label[x] == 2:
                    dgp[x, y] = gpx[x, y]

        not_outside = ImageChops.invert(outside)

        paste_x = int(round(anchor_x + g_min_x - pad))
        paste_y = int(round(anchor_y + g_min_y - pad))

        # 1) Light-green background covering the rosette interior.
        light_bg = Image.new("RGBA", (bbox_w, bbox_h), SURA_GREEN_BG)
        image.paste(light_bg, (paste_x, paste_y), mask=not_outside)
        # 2) Dark-green outline.
        dark = Image.new("RGBA", (bbox_w, bbox_h), SURA_GREEN)
        image.paste(dark, (paste_x, paste_y), mask=outline_mask)
        # 3) Black digit.
        black = Image.new("RGBA", (bbox_w, bbox_h), BLACK)
        image.paste(black, (paste_x, paste_y), mask=digit_mask)

    def _draw_glyph(self, image, draw, font, glyph_id, glyph_code,
                    anchor_x, anchor_y, tajwid, fill=BLACK):
        glyph_char = chr(glyph_code)
        if tajwid is None or not tajwid.get("letter_rules"):
            draw.text((anchor_x, anchor_y), glyph_char,
                      font=font, fill=fill, anchor="ls")
            return

        anchor_data = self.anchor_map.get(str(glyph_id))
        if not anchor_data:
            draw.text((anchor_x, anchor_y), glyph_char,
                      font=font, fill=fill, anchor="ls")
            return

        col_intensity = anchor_data["col_intensity"]
        bbox = anchor_data["bbox"]
        _, _, right, bottom = bbox
        ink_w = len(col_intensity)
        ink_h = bottom - bbox[1] + 2

        draw.text((anchor_x, anchor_y), glyph_char,
                  font=font, fill=BLACK, anchor="ls")

        temp_mask = Image.new("L", (ink_w, ink_h), 0)
        ImageDraw.Draw(temp_mask).text(
            (-bbox[0] + 1, -bbox[1] + 1),
            glyph_char, font=font, fill=255, anchor="ls",
        )

        total_intensity = sum(col_intensity)
        if total_intensity == 0:
            return

        letter_rules = tajwid["letter_rules"]
        n = letter_count(tajwid["arabic_text"])

        thresholds = []
        curr = 0
        for idx in range(n):
            target = (idx + 1) / n * total_intensity
            for x, val in enumerate(col_intensity):
                curr += val
                if curr >= target:
                    thresholds.append(x)
                    break

        prev_x = 0
        for i, (letter_idx, rgb) in enumerate(letter_rules):
            if letter_idx is None:
                continue
            seg_idx = n - 1 - letter_idx
            x1 = prev_x
            x2 = thresholds[seg_idx] if seg_idx < len(thresholds) else ink_w
            left_x = min(x1, x2)
            right_x = max(x1, x2)
            prev_x = right_x
            if left_x >= right_x:
                continue
            seg_mask = Image.new("L", (ink_w, ink_h), 0)
            ImageDraw.Draw(seg_mask).rectangle([left_x, 0, right_x, ink_h], fill=255)
            final_mask = ImageChops.multiply(seg_mask, temp_mask)
            color_patch = Image.new("RGBA", (ink_w, ink_h), (*rgb, 255))
            paste_x = int(anchor_x + bbox[0] - 1)
            paste_y = int(anchor_y + bbox[1] - 1)
            crop_rect = (
                max(0, -paste_x),
                max(0, -paste_y),
                min(ink_w, image.width - paste_x),
                min(ink_h, image.height - paste_y),
            )
            if crop_rect[2] > crop_rect[0] and crop_rect[3] > crop_rect[1]:
                cropped_patch = color_patch.crop(crop_rect)
                cropped_mask  = final_mask.crop(crop_rect)
                paste_pos = (max(0, paste_x), max(0, paste_y))
                image.paste(cropped_patch, paste_pos, mask=cropped_mask)

    def _render_ornament(self, draw, page_width, coord_y, ptsize, margin_top,
                          char_up, surah_number=None):
        """
        Draw the ornament box (and, if available, the sura-name glyph inside it).
        Returns (ornament_center_y, ornament_bottom_y) so the caller can both
        centre the sura-name text and advance coord_y below the box.
        """
        orn_ptsize = int(ptsize * 1.8)
        orn_font = ImageFont.truetype(FONT_DEFAULT, size=orn_ptsize)
        orn_min_x, orn_max_x, orn_top, orn_bottom = _glyph_bbox(orn_font, ORNAMENT_HEADER_BOX)
        if orn_max_x == 0:
            return (None, None)
        desired_orn_top = max(float(margin_top), coord_y - char_up)
        orn_coord_y = desired_orn_top - orn_top   # baseline-y
        orn_coord_x = (page_width - orn_max_x) / 2.0
        # Light-green fill behind the central rectangle of the ornament,
        # so the surah-name text sits on a pale green background.
        orn_w = orn_max_x - orn_min_x
        orn_h = orn_bottom - orn_top
        inner_x1 = orn_coord_x + orn_min_x
        inner_x2 = orn_coord_x + orn_min_x + orn_w
        inner_y1 = orn_coord_y + orn_top
        inner_y2 = orn_coord_y + orn_bottom
        draw.rectangle([inner_x1, inner_y1, inner_x2, inner_y2], fill=SURA_GREEN_BG)
        draw.text((orn_coord_x, orn_coord_y), chr(ORNAMENT_HEADER_BOX),
                  font=orn_font, fill=SURA_GREEN, anchor="ls")
        center_y = orn_coord_y + (orn_top + orn_bottom) / 2.0
        bottom_y = orn_coord_y + orn_bottom
        return (center_y, bottom_y)

"""
Tajwid coloring engine – word-level colour annotation for Quran pages.

Implements the Mushaf Tajwid Diponegoro colour scheme:

  Rule                    Colour
  ─────────────────────── ──────────────────────────
  ghunnah                 Red     (220, 30,  30)
  ikhfa / iqlab           Dark-pink (200, 60, 60)
  idgham bi ghunnah       Green   (  0,150,  80)
  idgham bila ghunnah     Blue    ( 30, 80, 180)
  qalqalah                Orange  (180, 90,   0)
  madd                    Sky-blue(  0,100, 200)
  default                 Black   (  0,  0,   0)

Detection is entirely algorithmic: the Arabic Unicode text (with harakat)
stored in word_arabic is analysed per word, with optional next-word context
for cross-word rules (ikhfa, idgham, iqlab).
"""

# ── Arabic Unicode constants ──────────────────────────────────────────────── #

FATHA        = '\u064E'
KASRA        = '\u0650'
DAMMA        = '\u064F'
SHADDA       = '\u0651'
SUKUN        = '\u0652'
TANWIN_FATH  = '\u064B'
TANWIN_KASR  = '\u064D'
TANWIN_DAMM  = '\u064C'
SUPERSCRIPT_ALEF = '\u0670'   # ٰ  (e.g. رَحْمَٰنِ)

ALEF        = '\u0627'   # ا
ALEF_WASLA  = '\u0671'   # ٱ
ALEF_MADDA  = '\u0622'   # آ
WAW         = '\u0648'   # و
YA          = '\u064A'   # ي
NUN         = '\u0646'   # ن
MIM         = '\u0645'   # م
LAM         = '\u0644'   # ل
RA          = '\u0631'   # ر
BA          = '\u0628'   # ب

# ── Letter sets ────────────────────────────────────────────────────────────── #

# Characters that are diacritics, not base letters
DIACRITICS = frozenset({
    FATHA, KASRA, DAMMA, SHADDA, SUKUN,
    TANWIN_FATH, TANWIN_KASR, TANWIN_DAMM,
    SUPERSCRIPT_ALEF,
    '\u0653',  # madda above
    '\u0654',  # hamza above
    '\u0655',  # hamza below
    '\u0656',  # subscript alef
    '\u0657',  # inverted damma
    '\u0658',  # mark noon ghunna
    '\u06DC',  # small high seen
    '\u06DF',  # small high rounded zero
    '\u06E0',  # small high upright rectangular zero
    '\u06E1',  # empty centre high stop
    '\u06E2',  # small high meem isolated form
    '\u06E3',  # small low seen
    '\u06E4',  # small high madda
    '\u06E5',  # small waw
    '\u06E6',  # small ya
    '\u06E7',  # small high ya
    '\u06E8',  # small high noon
    '\u06EA',  # empty centre low stop
    '\u06EB',  # empty centre high stop
    '\u06EC',  # rounded high stop with filled centre
    '\u06ED',  # small low meem
})

QALQALAH_LETTERS = frozenset({
    '\u0642',  # ق
    '\u0637',  # ط
    '\u0628',  # ب
    '\u062C',  # ج
    '\u062F',  # د
})

IDGHAM_GHUNNAH_LETTERS    = frozenset({YA, WAW, MIM, NUN})   # ي و م ن
IDGHAM_NO_GHUNNAH_LETTERS = frozenset({LAM, RA})              # ل ر
IQLAB_LETTER              = BA                                # ب

# ikhfa letters: ص ذ ث ك ج ش ق س د ط ز ف ت ض ظ
IKHFA_LETTERS = frozenset({
    '\u0635', '\u0630', '\u062B', '\u0643', '\u062C',
    '\u0634', '\u0642', '\u0633', '\u062F', '\u0637',
    '\u0632', '\u0641', '\u062A', '\u0636', '\u0638',
})

TANWIN  = frozenset({TANWIN_FATH, TANWIN_KASR, TANWIN_DAMM})
HARAKAT = frozenset({FATHA, KASRA, DAMMA, TANWIN_FATH, TANWIN_KASR, TANWIN_DAMM})

# ── Colour map ─────────────────────────────────────────────────────────────── #
# Colours match the standard Tajweed colour scheme used by alquran.cloud /
# quranwbw.com (all 17 rule types).

RULE_COLORS: dict = {
    'hamza_wasl':           (170, 170, 170),  # #AAAAAA
    'silent':               (170, 170, 170),  # #AAAAAA
    'lam_shamsiyah':        (170, 170, 170),  # #AAAAAA
    'madda_normal':         ( 83, 127, 255),  # #537FFF
    'madda_permissible':    ( 64,  80, 255),  # #4050FF
    'madda_necessary':      (  0,  14, 188),  # #000EBC
    'qalqalah':             (221,   0,   8),  # #DD0008
    'madda_obligatory':     ( 33,  68, 193),  # #2144C1
    'ikhfa_shafawi':        (213,   0, 183),  # #D500B7
    'ikhfa':                (148,   0, 168),  # #9400A8
    'idgham_shafawi':       ( 88, 184,   0),  # #58B800
    'iqlab':                ( 38, 191, 253),  # #26BFFD
    'idgham_ghunnah':       ( 22, 151, 119),  # #169777
    'idgham_no_ghunnah':    ( 22, 146,   0),  # #169200
    'idgham_mutajanisayn':  (161, 161, 161),  # #A1A1A1
    'idgham_mutaqaribayn':  (161, 161, 161),  # #A1A1A1
    'ghunnah':              (255, 126,  30),  # #FF7E1E
    'ghunnah_mim_nun':      (255, 126,  30),  # #FF7E1E
    'madda_shilah':         ( 33,  68, 193),  # #2144C1  (same as obligatory)
    'default':              (  0,   0,   0),  # black
}

# ── Text parsing ───────────────────────────────────────────────────────────── #

def _parse_letters(text: str) -> list:
    """
    Parse Arabic *text* into [(base_letter, {diacritics}), ...].
    Each tuple pairs one base letter with the set of diacritic marks that
    follow it (i.e. belong to it).
    """
    result = []
    marks: set = set()
    pending = None

    for ch in text:
        if ch in DIACRITICS:
            if pending is not None:
                marks.add(ch)
        else:
            if pending is not None:
                result.append((pending, marks))
                marks = set()
            pending = ch
    if pending is not None:
        result.append((pending, marks))
    return result


def _first_consonant(text: str) -> str | None:
    """
    Return the first meaningful consonant of *text*, skipping a leading
    alef-wasla / plain alef that merely carries a vowel.
    """
    letters = _parse_letters(text)
    for i, (ch, _) in enumerate(letters):
        if i == 0 and ch in (ALEF, ALEF_WASLA):
            continue   # skip connecting/wasla alef prefix
        return ch
    return None


# ── Main classification ────────────────────────────────────────────────────── #

def classify_word(arabic_text: str, next_word_text: str | None = None) -> str:
    """
    Return the dominant tajwid rule name for *arabic_text*.

    *next_word_text* – the immediately following word in the same (or next)
    ayah; required for cross-word rules (ikhfa, idgham, iqlab).

    Priority order (highest first):
        ghunnah > iqlab > idgham_ghunnah > idgham_no_ghunnah >
        ikhfa > qalqalah > default
    (Madd is not coloured at word level; reference mushaf uses underlines.)
    """
    letters = _parse_letters(arabic_text)
    if not letters:
        return 'default'

    # 1. Ghunnah: nun or mim with shadda anywhere in the word ─────────────── #
    for ch, marks in letters:
        if ch in (NUN, MIM) and SHADDA in marks:
            return 'ghunnah'

    # 2. Cross-word rules for nun-sakinah / tanwin at end of word ─────────── #
    last_ch, last_marks = letters[-1]
    nun_sakina  = (last_ch == NUN and SUKUN in last_marks)
    has_tanwin  = bool(last_marks & TANWIN)

    if (nun_sakina or has_tanwin) and next_word_text:
        nfl = _first_consonant(next_word_text)
        if nfl == IQLAB_LETTER:
            return 'iqlab'
        if nfl in IDGHAM_GHUNNAH_LETTERS:
            return 'idgham_ghunnah'
        if nfl in IDGHAM_NO_GHUNNAH_LETTERS:
            return 'idgham_no_ghunnah'
        if nfl in IKHFA_LETTERS:
            return 'ikhfa'

    # 3. Mim-sakinah rules ──────────────────────────────────────────────────── #
    mim_sakina = (last_ch == MIM and SUKUN in last_marks)
    if mim_sakina and next_word_text:
        nfl = _first_consonant(next_word_text)
        if nfl == MIM:
            return 'idgham_ghunnah'   # idgham syafawi
        if nfl == BA:
            return 'ikhfa'            # ikhfa syafawi

    # 4. Qalqalah: qalqalah letter with sukun (or sukun-equivalent) ────────── #
    #    Also triggers on tanwin for the LAST letter (waqf position, where
    #    tanwin is realised as sukun), and on U+06E1 / U+06DF which are
    #    alternative sukun notations used in the Uthmani Mushaf.
    SUKUN_LIKE = frozenset({SUKUN, '\u06E1', '\u06DF'})
    for i, (ch, marks) in enumerate(letters):
        is_last = (i == len(letters) - 1)
        has_sukun    = bool(marks & SUKUN_LIKE)
        has_tanwin   = bool(marks & TANWIN)
        if ch in QALQALAH_LETTERS and (has_sukun or (has_tanwin and is_last)):
            return 'qalqalah'

    # NOTE: Madd (long-vowel elongation) is intentionally NOT coloured at the
    # word level.  In Mushaf Tajwid Diponegoro, madd is indicated by coloured
    # underlines, not by colouring the letters themselves.  Almost every Arabic
    # word contains a long vowel, so word-level madd colouring would flood the
    # page with colour and not match the reference.  Madd underlines are a
    # planned future feature.

    return 'default'


# ── Target letter identification ─────────────────────────────────────────── #

def get_target_letter_index(arabic_text: str, rule: str) -> int | None:
    """
    Return the 0-based index (from the LEFT of the Arabic text string) of the
    letter that triggered *rule*.  Returns None if it cannot be determined.

    In RTL rendering the letter at text-index *i* of an *n*-letter word
    occupies the x-band:
        x_from_ink_left = (n - 1 - i) / n  *  ink_width
    so the last letter (i = n-1) is always at the leftmost band.
    """
    letters = _parse_letters(arabic_text)
    if not letters:
        return None

    if rule == 'ghunnah':
        for i, (ch, marks) in enumerate(letters):
            if ch in (NUN, MIM) and SHADDA in marks:
                return i

    elif rule in ('iqlab', 'idgham_ghunnah', 'idgham_no_ghunnah', 'ikhfa'):
        # Cross-word rule: triggered by the LAST letter (nun-sakinah / tanwin
        # / mim-sakinah) which is always the leftmost letter in the RTL glyph.
        return len(letters) - 1

    elif rule == 'qalqalah':
        for i, (ch, marks) in enumerate(letters):
            if ch in QALQALAH_LETTERS and SUKUN in marks:
                return i

    return None


def letter_count(arabic_text: str) -> int:
    """Return the number of base (non-diacritic) letters in *arabic_text*."""
    return len(_parse_letters(arabic_text))


# ── Page-level colour builder ─────────────────────────────────────────────── #

def build_tajwid_map(word_rows: list) -> dict:
    """
    Build ``{glyph_id: info}`` for an entire page.

    *word_rows* – list from ``QuranDB.get_words_for_page()``.
    Each row must contain: glyph_id, arabic_text, sura_number, ayah_number,
    word_pos.

    Each *info* dict contains:
        arabic_text   str
        letter_rules  [(letter_idx, (R, G, B)), ...]
            – one entry per tagged character in the word.
              ``letter_idx`` is the 0-based index from the LEFT of
              ``arabic_text`` of the coloured base letter.

    Only glyphs that have at least one coloured letter are included.

    Primary source: quran-tajweed.json (accurate per-character data).
    Fallback: algorithmic classifier for words absent from the JSON.
    """
    from . import tajwid_data   # lazy import

    json_lookup = tajwid_data.get_lookup()
    result: dict = {}
    n_rows = len(word_rows)

    for i, row in enumerate(word_rows):
        key = (row['sura_number'], row['ayah_number'], row['word_pos'])
        json_hit = json_lookup.get(key)

        if json_hit is None:
            continue   # word not tagged in JSON → render black, no rule

        # json_hit = [(letter_idx, rule_name), ...]
        letter_rules = [
            (idx, RULE_COLORS[rule])
            for idx, rule in json_hit
            if rule in RULE_COLORS
        ]

        if not letter_rules:
            continue

        result[row['glyph_id']] = {
            'arabic_text': row['arabic_text'],
            'letter_rules': letter_rules,
        }

    return result

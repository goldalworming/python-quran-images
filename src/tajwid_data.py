"""
Tajwid data loader – parses quran-tajweed.json from alquran.cloud.

Builds a word-level lookup:
    (sura_number, ayah_number, word_pos) → [(letter_idx, rule_name), ...]

word_pos is 1-based (matching word.position in the DB).
letter_idx is the 0-based index from the LEFT of the Arabic text string
of each tagged base letter.

All 17 rule codes are recognised:

    h  hamza_wasl          s  silent             l  lam_shamsiyah
    n  madda_normal        p  madda_permissible   m  madda_necessary
    o  madda_obligatory    q  qalqalah            g  ghunnah
    f  ikhfa               c  ikhfa_shafawi       i  iqlab
    a  idgham_ghunnah      w  idgham_shafawi      u  idgham_no_ghunnah
    d  idgham_mutajanisayn  b  idgham_mutaqaribayn
"""

import json
import os
import re

_JSON_PATH = os.path.join(os.path.dirname(__file__), '..', 'quran-tajweed.json')

_TAG_RE = re.compile(r'\[([a-z]+)(?::[0-9]+)?\[')

# Arabic diacritics – same set as tajwid.py
_DIACRITICS = frozenset({
    '\u064E', '\u0650', '\u064F', '\u0651', '\u0652',
    '\u064B', '\u064D', '\u064C', '\u0670',
    '\u0653', '\u0654', '\u0655', '\u0656', '\u0657',
    '\u0658', '\u06DC', '\u06DF', '\u06E0', '\u06E1',
    '\u06E2', '\u06E3', '\u06E4', '\u06E5', '\u06E6',
    '\u06E7', '\u06E8', '\u06EA', '\u06EB', '\u06EC', '\u06ED',
})

# Every recognised rule code → internal rule name
_CODE_TO_RULE: dict = {
    'h': 'hamza_wasl',
    's': 'silent',
    'l': 'lam_shamsiyah',
    'n': 'madda_normal',
    'p': 'madda_permissible',
    'm': 'madda_necessary',
    'o': 'madda_obligatory',
    'q': 'qalqalah',
    'g': 'ghunnah',
    'f': 'ikhfa',
    'c': 'ikhfa_shafawi',
    'i': 'iqlab',
    'a': 'idgham_ghunnah',
    'w': 'idgham_shafawi',
    'u': 'idgham_no_ghunnah',
    'd': 'idgham_mutajanisayn',
    'b': 'idgham_mutaqaribayn',
}

_COLORED_CODES = frozenset(_CODE_TO_RULE)

_lookup: dict | None = None   # lazy singleton


def _parse_tagged_words(tagged_text: str) -> list:
    """
    Parse a tajweed-tagged ayah text into a list of
    ``(clean_word_text, char_rules)`` tuples where::

        char_rules = [(letter_idx, rule_name), ...]

    ``letter_idx`` is the 0-based index from the LEFT of the clean Arabic
    text string of the tagged base letter.  ``char_rules`` is empty when no
    rule applies to any letter in the word.

    Tags whose content contains a space span a word boundary.  The part
    before the space is attached to the current word (with its rule), the
    part after the space starts the next word (without a carried-over rule).
    """
    words: list = []

    # Per-word state
    word_chars: list = []       # clean characters accumulated so far
    char_rules: list = []       # [(letter_idx, rule_name), ...] for current word
    base_count: int = 0         # base letters seen in current word

    i = 0
    n = len(tagged_text)

    while i < n:
        m = _TAG_RE.match(tagged_text, i)
        if m:
            code = m.group(1)
            content_start = m.end()
            close = tagged_text.find(']', content_start)
            if close == -1:
                i = content_start
                continue
            content = tagged_text[content_start:close]
            i = close + 1

            rule_name = _CODE_TO_RULE.get(code)  # None for unknown codes
            tag_base_pos = base_count   # index of the first base letter in this tag

            if ' ' in content:
                # Tag crosses a word boundary.
                before, after = content.split(' ', 1)

                # Add 'before' chars to the current word.
                before_base_start = base_count
                for ch in before:
                    word_chars.append(ch)
                    if ch not in _DIACRITICS:
                        base_count += 1

                if rule_name and before:
                    char_rules.append((before_base_start, rule_name))

                # Emit current word.
                words.append((''.join(word_chars), char_rules))
                word_chars = []
                char_rules = []
                base_count = 0

                # 'after' begins the next word (no rule carried over).
                for ch in after:
                    word_chars.append(ch)
                    if ch not in _DIACRITICS:
                        base_count += 1

            else:
                # Entire tag content stays within the current word.
                for ch in content:
                    word_chars.append(ch)
                    if ch not in _DIACRITICS:
                        base_count += 1

                if rule_name and content:
                    char_rules.append((tag_base_pos, rule_name))

        elif tagged_text[i] == ' ':
            if word_chars:
                words.append((''.join(word_chars), char_rules))
            word_chars = []
            char_rules = []
            base_count = 0
            i += 1

        else:
            ch = tagged_text[i]
            word_chars.append(ch)
            if ch not in _DIACRITICS:
                base_count += 1
            i += 1

    if word_chars:
        words.append((''.join(word_chars), char_rules))

    return words


def _has_arabic_letter(text: str) -> bool:
    """Return True if *text* contains at least one standard Arabic base letter."""
    return any(0x0621 <= ord(ch) <= 0x06D5 and ch not in _DIACRITICS for ch in text)


def _build_lookup() -> dict:
    """Load the JSON and return ``{(sura, ayah, word_pos): [(letter_idx, rule_name), ...]}``."""
    lookup: dict = {}
    with open(_JSON_PATH, 'r', encoding='utf-8') as f:
        raw = json.load(f)

    for surah in raw['data']['surahs']:
        sura_num = surah['number']
        for ayah in surah['ayahs']:
            ayah_num = ayah['numberInSurah']
            words = _parse_tagged_words(ayah['text'])
            word_idx = 0
            for clean_text, char_rules in words:
                if not _has_arabic_letter(clean_text):
                    continue   # skip ornament tokens like ۞ (U+06DE)
                word_idx += 1
                if char_rules:
                    lookup[(sura_num, ayah_num, word_idx)] = char_rules

    return lookup


def get_lookup() -> dict:
    """Return the lazily-built lookup (loads JSON on first call)."""
    global _lookup
    if _lookup is None:
        _lookup = _build_lookup()
    return _lookup


def lookup_word(sura: int, ayah: int, word_pos: int):
    """
    Return ``[(letter_idx, rule_name), ...]`` for the given word,
    or ``None`` if the word has no tagged letters.
    """
    return get_lookup().get((sura, ayah, word_pos))

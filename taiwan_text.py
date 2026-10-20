"""Conservative Taiwan glyph conversion; vocabulary changes are opt-in."""
import json
from pathlib import Path
from opencc import OpenCC
from glyph_normalization import normalize_glyphs

TERMS = {}  # No implicit regional vocabulary substitutions.
CONVERSION_CHOICES = {
    '自訂轉換（依個人規則檔）': 'flypy_s2twp.json',
    '只轉繁體字形、保留原詞（建議）': 's2tw.json',
    '完整台灣用語替換（會改動設置、項目等詞）': 's2twp.json',
}

class TaiwanConverter:
    def __init__(self, root=None, config='s2tw.json'):
        self.terms = dict(TERMS) if config == 'flypy_s2twp.json' else {}
        preset = 's2twp' if config == 's2twp.json' else 's2tw'
        if root and config == 'flypy_s2twp.json':
            folder = Path(root) / 'opencc'
            path = folder / config
            if path.is_file():
                data = json.loads(path.read_text(encoding='utf-8-sig'))
                if 'TWPhrases.ocd2' in json.dumps(data):
                    preset = 's2twp'
                terms_path = folder / 'flypy_tw_terms.txt'
                if terms_path.is_file():
                    self.terms = {}
                    for line in terms_path.read_text(encoding='utf-8-sig').splitlines():
                        if line and not line.startswith('#') and '\t' in line:
                            key, value = line.split('\t', 1)
                            self.terms[key] = value.split()[0]
        self.converter = OpenCC(preset)

    def convert(self, text):
        # Apply approved terms once, longest first, before glyph conversion.
        import re
        if self.terms:
            text = re.sub('|'.join(re.escape(k) for k in sorted(self.terms, key=len, reverse=True)), lambda m: self.terms[m.group(0)], text)
        return normalize_glyphs(self.converter.convert(text))

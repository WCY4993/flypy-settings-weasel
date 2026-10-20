"""Reproduce the supplemental dictionary from pinned, licensed McBopomofo data."""
from pathlib import Path
import hashlib
import json
import re
import urllib.request
from glyph_normalization import normalize_glyphs
from taiwan_text import TaiwanConverter

ROOT = Path(__file__).parent

def build(cache=None):
    lock = json.loads((ROOT/'taiwan-upstream.json').read_text(encoding='utf-8'))
    data = {}
    for name, checksum in lock['files'].items():
        path = Path(cache)/name if cache else ROOT/'build/taiwan-source'/name
        if not path.is_file():
            url = f"https://raw.githubusercontent.com/openvanilla/McBopomofo/{lock['commit']}/" + ('LICENSE.txt' if name == 'LICENSE.txt' else 'Source/Data/'+name)
            with urllib.request.urlopen(url, timeout=90) as response: raw = response.read()
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != checksum:
            raise RuntimeError('Taiwan dictionary source checksum mismatch: '+name)
        data[name] = raw.decode('utf-8-sig')
    occurrences = {}
    for line in data['phrase.occ'].splitlines():
        fields = line.split()
        if len(fields) == 2 and fields[1].isdigit(): occurrences[fields[0]] = int(fields[1])
    phonetics, base = {}, []
    for line in data['BPMFBase.txt'].splitlines():
        fields = line.split()
        if len(fields) < 5 or fields[0].startswith('#'): continue
        word, bpmf, py = fields[:3]
        py = re.sub('[1-5]', '', py.lower()).replace('ü','v')
        if not re.fullmatch('[a-z]+', py): continue
        if bpmf in phonetics and phonetics[bpmf] != py: raise RuntimeError('Ambiguous phonetic mapping')
        phonetics[bpmf] = py
        if fields[4] == 'big5' or occurrences.get(word,0) > 0: base.append((word,[py]))
    def han(word):
        return all(0x3400 <= ord(c) <= 0x9fff or 0x20000 <= ord(c) <= 0x323af for c in word)
    rows, skipped = {}, 0
    converter = TaiwanConverter()
    def add(word, syllables):
        nonlocal skipped
        word = word.replace('万','萬')
        if not word or len(word) != len(syllables) or len(word)>16 or not han(word) or normalize_glyphs(word)!=word:
            skipped += 1; return
        # Scale corpus occurrences into Rime's weight range, retaining both spellings.
        weight = min(100000000, max(1,occurrences.get(word,0))*100)
        code = ' '.join(syllables)
        for text, value in ((word,weight),(converter.convert(word),max(1,int(weight*0.8)))):
            rows[text,code] = max(rows.get((text,code),0),value)
    for word, syllables in base: add(word,syllables)
    for line in data['BPMFMappings.txt'].splitlines():
        fields=line.split()
        if len(fields)<2 or fields[0].startswith('#'): continue
        if not all(p in phonetics for p in fields[1:]): skipped+=1;continue
        add(fields[0],[phonetics[p] for p in fields[1:]])
    header = '# Generated from openvanilla/McBopomofo; see licenses/McBopomofo-MIT.txt\n---\nname: flypy_taiwan\nversion: "'+lock['commit'][:12]+'"\nsort: by_weight\nuse_preset_vocabulary: false\n...\n'
    target=ROOT/'flypy_taiwan.dict.yaml'
    target.write_text(header+''.join(f'{word}\t{code}\t{weight}\n' for (word,code),weight in sorted(rows.items())),encoding='utf-8',newline='\n')
    return {'entries':len(rows),'spellings':len({w for w,p in rows}),'skipped':skipped,'source_commit':lock['commit'],'sha256':hashlib.sha256(target.read_bytes()).hexdigest()}

if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--cache');args=parser.parse_args()
    print(json.dumps(build(args.cache),ensure_ascii=False))

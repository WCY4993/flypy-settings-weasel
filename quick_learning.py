"""Read-only access to the exact-spelling journal owned by the Rime Lua engine."""
from pathlib import Path
from glyph_normalization import normalize_glyphs

JOURNAL = 'flypy_learning.tsv'

def records(root):
    path = Path(root) / JOURNAL
    latest = {}
    if not path.is_file():
        return []
    with path.open(encoding='utf-8') as stream:
        for line in stream:
            fields = line.rstrip('\r\n').split('\t')
            if len(fields) != 5:
                continue  # A partial final append must not destroy earlier records.
            mode, code, text, count, manual = fields
            if mode not in ('t', 's') or not code.isascii() or not code.isalpha() or not code.islower() or not count.isdecimal() or not manual.isdecimal():
                continue
            latest[mode, code, text] = (text, code, f'選用 {count} 次；' + ('繁體' if mode == 't' else '簡體'))
    return list(latest.values())

def exact_source(source):
    return source in ('flypy_taiwan.dict.yaml', JOURNAL, 'flypy_personal.dict.yaml')

def row_text(rules, row):
    text = row['text']
    rule = rules.rows.get(text)
    if rule and rule.replacement:
        return rules.output(rule)
    if exact_source(row['source']):
        return rules.store.to_tw.convert(text) if normalize_glyphs(text) != text else text
    return rules.display(text)


def prepare_io(store, changes):
    """Keep machine-specific legacy CRT path bytes out of public defaults."""
    import os
    from settings_core import yaml_parser, dump_yaml, get_patch, set_patch, SettingsError
    result = dict(changes)
    if os.name != 'nt':
        return result
    import ctypes
    cp = ctypes.windll.kernel32.GetACP()
    try:
        encoded = str(store.root).encode('cp'+str(cp)).hex()
    except UnicodeEncodeError as error:
        raise SettingsError('資料路徑包含目前 Windows 舊式檔案編碼無法表示的字元，未套用學習更新。請改用可相容的 Rime 資料路徑。') from error
    name = 'double_pinyin_flypy.custom.yaml'
    raw = result.get(name,store.raw.get(name))
    if not raw:
        return result
    doc = yaml_parser().load(raw.decode('utf-8-sig'))
    # Bundle the two small Lua assets so replacing the GUI also upgrades its runtime.
    import sys
    assets = Path(getattr(sys,'_MEIPASS',Path(__file__).parent)) / 'lua'
    for filename in ('flypy_learning.lua','flypy_number_style.lua','flypy_english.lua'):
        asset = assets / filename
        name_in_store = 'lua/' + filename
        if asset.is_file() and name_in_store in store.raw:
            data = asset.read_bytes()
            if data != store.raw[name_in_store]:
                result[name_in_store] = data
    dictionary = assets.parent / 'flypy_taiwan.dict.yaml'
    if dictionary.is_file() and 'flypy_taiwan.dict.yaml' in store.raw:
        data = dictionary.read_bytes()
        if data != store.raw['flypy_taiwan.dict.yaml']:
            result['flypy_taiwan.dict.yaml'] = data
        base_name = 'flypy_tw.dict.yaml'
        base_raw = result.get(base_name,store.raw.get(base_name))
        if base_raw:
            base_doc = yaml_parser().load(base_raw.decode('utf-8-sig'))
            tables = list(base_doc.get('import_tables',[]))
            if 'flypy_taiwan' not in tables:
                tables.insert(1 if tables else 0,'flypy_taiwan')
                base_doc['import_tables'] = tables
                result[base_name] = dump_yaml(base_doc).encode('utf-8')
    from vocabulary import LUA, LUA_FILE, FILTER
    if LUA_FILE in store.raw and LUA.encode('utf-8') != store.raw[LUA_FILE]:
        result[LUA_FILE] = LUA.encode('utf-8')
    filters = get_patch(doc,'engine/filters')
    if filters is None:
        compiled=store.root/'build/double_pinyin_flypy.schema.yaml'
        filters=yaml_parser().load(compiled.read_text(encoding='utf-8-sig')).get('engine',{}).get('filters',[]) if compiled.is_file() else []
    filters=list(filters)
    for member in ('lua_filter@*flypy_learning','lua_filter@*flypy_english',FILTER):
        if member not in filters:
            position=filters.index('uniquifier') if 'uniquifier' in filters else len(filters)
            filters.insert(position,member)
    if filters.index('lua_filter@*flypy_learning')>filters.index(FILTER):
        filters.remove('lua_filter@*flypy_learning');filters.insert(filters.index(FILTER),'lua_filter@*flypy_learning')
    if filters.index('lua_filter@*flypy_english')>filters.index(FILTER):
        filters.remove('lua_filter@*flypy_english');filters.insert(filters.index(FILTER),'lua_filter@*flypy_english')
    if filters != get_patch(doc,'engine/filters'):
        set_patch(doc,'engine/filters',filters)
        result['double_pinyin_flypy.custom.yaml'] = dump_yaml(doc).encode('utf-8')
    for path, value in [('melt_eng/enable_completion',False),('cn_en/enable_completion',False),('flypy_english/original_first',True)]:
        if get_patch(doc,path) is None:
            set_patch(doc,path,value)
            result[name] = dump_yaml(doc).encode('utf-8')
    english_name = 'melt_eng.custom.yaml'
    english_raw = result.get(english_name,store.raw.get(english_name))
    if english_raw:
        english_doc = yaml_parser().load(english_raw.decode('utf-8-sig'))
        changed = False
        if get_patch(english_doc,'translator/enable_completion') is None:
            set_patch(english_doc,'translator/enable_completion',False); changed = True
        english_filters = list(get_patch(english_doc,'engine/filters') or ['uniquifier'])
        if 'lua_filter@*flypy_english' not in english_filters:
            position = english_filters.index('uniquifier') if 'uniquifier' in english_filters else len(english_filters)
            english_filters.insert(position,'lua_filter@*flypy_english')
            set_patch(english_doc,'engine/filters',english_filters); changed = True
        if changed: result[english_name] = dump_yaml(english_doc).encode('utf-8')
    if get_patch(doc,'flypy_learning/io_path_hex') != encoded or get_patch(doc,'flypy_learning/io_path_utf8_hex') != str(store.root).encode('utf-8').hex():
        set_patch(doc,'flypy_learning/io_path_hex',encoded)
        set_patch(doc,'flypy_learning/io_path_utf8_hex',str(store.root).encode('utf-8').hex())
        result[name] = dump_yaml(doc).encode('utf-8')
    return result

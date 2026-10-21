"""Scoped, transactional editor for the bundled Flypy custom configuration."""
from __future__ import annotations

import copy
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import time
import uuid
from dataclasses import dataclass, replace
from datetime import datetime

from opencc import OpenCC
from ruamel.yaml import YAML
from taiwan_text import TaiwanConverter
from glyph_normalization import normalize_glyphs

VERSION = '2.2.8'
FILES = ('weasel.custom.yaml', 'default.custom.yaml',
         'flypy_personal.dict.yaml', 'flypy_phrases.txt')
OPTIONAL_FILES = ('flypy_taiwan_variants.txt', 'lua/flypy_english.lua', 'flypy_taiwan.dict.yaml', 'flypy_tw.dict.yaml', 'lua/flypy_learning.lua', 'double_pinyin_flypy.custom.yaml', 'melt_eng.custom.yaml',
                  'radical_pinyin.custom.yaml', 'lua/flypy_number_style.lua', 'flypy_vocabulary_rules.tsv',
                  'lua/flypy_vocabulary_filter.lua', 'opencc/flypy_s2twp.json', 'opencc/flypy_tw_terms.txt')
SHIFT_MODES = {
    '上屏候選後切換': 'commit_text',
    '上屏編碼後切換': 'commit_code',
    '清除編碼後切換': 'clear',
    '暫時英文模式': 'inline_ascii',
    '不切換': 'noop',
}


class SettingsError(Exception):
    pass


def yaml_parser():
    parser = YAML(typ='rt')
    parser.preserve_quotes = True
    parser.width = 200
    return parser


def dump_yaml(value):
    stream = io.StringIO()
    yaml_parser().dump(value, stream)
    return stream.getvalue()


def digest(value):
    return hashlib.sha256(value).hexdigest()


def get_patch(document, path, default=None):
    node = document.get('patch', {})
    parts = path.split('/')
    while parts:
        if not isinstance(node, dict):
            return default
        for size in range(len(parts), 0, -1):
            key = '/'.join(parts[:size])
            if key in node:
                node = node[key]
                parts = parts[size:]
                break
        else:
            return default
    return node


def set_patch(document, path, value):
    node = document.setdefault('patch', {})
    parts = path.split('/')
    while parts:
        for size in range(len(parts), 0, -1):
            key = '/'.join(parts[:size])
            if key in node:
                if size == len(parts):
                    for descendant in list(node):
                        if isinstance(descendant,str) and descendant.startswith(key+'/'):
                            del node[descendant]
                    node[key] = value
                    return
                if not isinstance(node[key], dict):
                    raise SettingsError(f'設定結構不相容：{path}，請先檢查個人 YAML。')
                node = node[key]
                parts = parts[size:]
                break
        else:
            target='/'.join(parts)
            for descendant in list(node):
                if isinstance(descendant,str) and descendant.startswith(target+'/'):
                    del node[descendant]
            node[target] = value
            return


@dataclass(eq=True)
class Appearance:
    font_size: int = 16
    label_size: int = 11
    comment_size: int = 12
    font_face: str = 'Microsoft JhengHei UI, Segoe UI, Segoe UI Emoji'
    horizontal: bool = False
    page_size: int = 8
    shift_left: str = 'commit_text'
    shift_right: str = 'commit_text'


@dataclass(eq=True)
class Entry:
    uid: str
    text: str
    code: str
    weight: int


class Table:
    """Retain unchanged rows and comments byte-for-byte within the text table."""
    def __init__(self, name, content, chinese):
        self.name, self.chinese = name, chinese
        self.content = content
        self.newline = '\r\n' if '\r\n' in content else '\n'
        lines = content.splitlines(keepends=True)
        self.header = ''
        if chinese:
            end = next((i for i, line in enumerate(lines) if line.strip() == '...'), None)
            if end is None:
                raise SettingsError(f'{name} 缺少詞庫標頭結束符號 ...。')
            self.header, lines = ''.join(lines[:end + 1]), lines[end + 1:]
        self.blocks, self.entries = [], []
        for i, line in enumerate(lines):
            raw = line.rstrip('\r\n')
            if not raw.strip() or raw.lstrip().startswith('#'):
                self.blocks.append(('literal', line))
                continue
            fields = raw.split('\t')
            if len(fields) != 3:
                raise SettingsError(f'{name} 第 {i + 1} 個詞條格式不支援；需要三欄並以 Tab 分隔。')
            try:
                weight = int(fields[2])
            except ValueError as error:
                raise SettingsError(f'{name} 的權重／順序不是整數。') from error
            entry = Entry(f'row-{i}', fields[0], fields[1], weight)
            self.entries.append(entry)
            self.blocks.append(('row', (entry, line)))

    def render(self, entries):
        if entries == self.entries:
            return self.content
        header = self.header
        if self.chinese:
            header = re.sub(r'(?m)^version:.*$',
                            f'version: "{datetime.now():%Y-%m-%d-%H%M%S}"', header)
        by_id = {entry.uid: entry for entry in entries}
        emitted = set()
        output = [header]
        for kind, block in self.blocks:
            if kind == 'literal':
                output.append(block)
                continue
            old, raw = block
            entry = by_id.get(old.uid)
            if entry is None:
                continue
            emitted.add(entry.uid)
            output.append(raw if entry == old else self.line(entry))
        for entry in entries:
            if entry.uid not in emitted:
                if output and output[-1] and not output[-1].endswith(('\n', '\r')):
                    output.append(self.newline)
                output.append(self.line(entry))
        return ''.join(output)

    def line(self, entry):
        return f'{entry.text}\t{entry.code}\t{entry.weight}{self.newline}'


class Store:
    def __init__(self, user_dir, weasel_root=None):
        self.root = Path(user_dir).resolve()
        self.weasel_root = Path(weasel_root) if weasel_root else None
        self.backup_root = self.root / 'maintenance' / 'settings-backups'
        self.to_tw = TaiwanConverter(self.root)
        self.to_s = OpenCC('t2s')
        self.load()

    def load(self):
        if not self.root.is_dir():
            raise SettingsError(f'找不到 Rime 使用者資料夾：{self.root}')
        try:
            self.raw = {name: (self.root / name).read_bytes() for name in FILES}
        except FileNotFoundError as error:
            raise SettingsError('找不到本套配置需要的個人檔案；這個工具適用於目前的雾凇小鶴配置。') from error
        self.raw.update({name: (self.root / name).read_bytes() if (self.root / name).is_file() else None
                         for name in OPTIONAL_FILES})
        schema_raw = self.raw.get('double_pinyin_flypy.custom.yaml')
        schema = yaml_parser().load(schema_raw.decode('utf-8-sig')) if schema_raw else {}
        self.to_tw = TaiwanConverter(self.root, get_patch(schema, 'traditionalize/opencc_config', 's2tw.json'))
        self.weasel = self.read_yaml('weasel.custom.yaml')
        self.default = self.read_yaml('default.custom.yaml')
        self.words = Table('flypy_personal.dict.yaml', self.decode('flypy_personal.dict.yaml'), True)
        self.phrases = Table('flypy_phrases.txt', self.decode('flypy_phrases.txt'), False)
        w, d = self.weasel, self.default
        self.appearance = Appearance(
            int(get_patch(w, 'style/font_point', 16)),
            int(get_patch(w, 'style/label_font_point', 11)),
            int(get_patch(w, 'style/comment_font_point', 12)),
            str(get_patch(w, 'style/font_face', Appearance().font_face)),
            bool(get_patch(w, 'style/horizontal', False)),
            int(get_patch(d, 'menu/page_size', 8)),
            str(get_patch(d, 'ascii_composer/switch_key/Shift_L', 'commit_text')),
            str(get_patch(d, 'ascii_composer/switch_key/Shift_R', 'commit_text')))

    def decode(self, name):
        try:
            return self.raw[name].decode('utf-8-sig')
        except UnicodeDecodeError as error:
            raise SettingsError(f'{name} 不是 UTF-8，未作任何修改。') from error

    def read_yaml(self, name):
        try:
            document = yaml_parser().load(self.decode(name))
            if not isinstance(document, dict) or not isinstance(document.get('patch'), dict):
                raise ValueError('missing patch mapping')
            return document
        except Exception as error:
            raise SettingsError(f'{name} 無法解析，請先修正 YAML：{error}') from error

    def assert_unchanged(self):
        for name, old in self.raw.items():
            actual = (self.root / name).read_bytes() if (self.root / name).is_file() else None
            if actual != old:
                raise SettingsError(f'{name} 已被其他程式修改。請先按「重新讀取」，避免覆蓋外部變更。')

    def normalize_word(self, display_text, code, weight, original=None):
        display_text = display_text.strip()
        # Legacy rows survive an unchanged edit; new valid traditional spellings stay exact.
        text = original.text if original and display_text == original.text else self.to_tw.convert(display_text) if normalize_glyphs(display_text) != display_text else display_text
        return self.make_entry(text, code, weight, True, original)

    def make_entry(self, text, code, weight, chinese, original=None):
        text = text.strip()
        if not text or any(c in text for c in '\r\n\t\x00'):
            raise SettingsError('詞彙不能空白，也不能包含 Tab 或換行。')
        try:
            weight = int(weight)
        except (TypeError, ValueError) as error:
            raise SettingsError('權重／順序必須是整數。') from error
        code = ' '.join(code.lower().replace('ü', 'v').split())
        if chinese:
            if not 1 <= weight <= 100000000:
                raise SettingsError('中文權重請填 1～100000000，一般使用 10000 即可。')
            if not re.fullmatch(r'[a-z]+(?: [a-z]+)*', code):
                raise SettingsError('請填無聲調完整拼音，音節用空格分開；ü 可寫 v。')
            hanzi = [c for c in text if '\u3400' <= c <= '\u9fff' or 0x20000 <= ord(c) <= 0x323af]
            if not hanzi or any(c not in hanzi and c not in '·・' for c in text):
                raise SettingsError('此頁請填中文字詞；數字、英文或中英混合短語請加在「英文與捷徑」。')
            if len(hanzi) != len(code.split()):
                raise SettingsError(f'這個詞有 {len(hanzi)} 個中文字，請填 {len(hanzi)} 個拼音音節。')
        else:
            if not re.fullmatch(r'[a-z]{2,48}', code):
                raise SettingsError('捷徑碼請用 2～48 個小寫英文字母；數字鍵要留給選字。')
            if not 1 <= weight <= 99:
                raise SettingsError('候選順序請填 1～99，通常填 1。')
        return Entry(original.uid if original else uuid.uuid4().hex, text, code, weight)

    def validate(self, appearance, words, phrases):
        for value, low, high, label in [
            (appearance.font_size, 10, 40, '候選字級'),
            (appearance.label_size, 8, 30, '數字字級'),
            (appearance.comment_size, 8, 30, '註解字級'),
            (appearance.page_size, 5, 9, '每頁候選數')]:
            if not isinstance(value, int) or not low <= value <= high:
                raise SettingsError(f'{label} 請填 {low}～{high}。')
        if not appearance.font_face.strip() or any(c in appearance.font_face for c in '\n\r\x00'):
            raise SettingsError('字體名稱不正確。')
        for mode, original in [(appearance.shift_left, self.appearance.shift_left),
                               (appearance.shift_right, self.appearance.shift_right)]:
            if mode not in SHIFT_MODES.values() and mode != original:
                raise SettingsError('Shift 切換方式不正確。')
        for entries, chinese in [(words, True), (phrases, False)]:
            seen, ids = set(), set()
            for entry in entries:
                self.make_entry(entry.text, entry.code, entry.weight, chinese, entry)
                key = (entry.text, entry.code)
                if key in seen or entry.uid in ids:
                    raise SettingsError(f'重複詞條：{entry.text}／{entry.code}')
                seen.add(key)
                ids.add(entry.uid)

    def build(self, appearance, words, phrases):
        self.validate(appearance, words, phrases)
        w, d = copy.deepcopy(self.weasel), copy.deepcopy(self.default)
        pairs = [
            (w, 'style/font_point', appearance.font_size, self.appearance.font_size),
            (w, 'style/label_font_point', appearance.label_size, self.appearance.label_size),
            (w, 'style/comment_font_point', appearance.comment_size, self.appearance.comment_size),
            (w, 'style/font_face', appearance.font_face, self.appearance.font_face),
            (w, 'style/horizontal', appearance.horizontal, self.appearance.horizontal),
            (d, 'menu/page_size', appearance.page_size, self.appearance.page_size),
            (d, 'ascii_composer/switch_key/Shift_L', appearance.shift_left, self.appearance.shift_left),
            (d, 'ascii_composer/switch_key/Shift_R', appearance.shift_right, self.appearance.shift_right)]
        changed_w = changed_d = False
        for document, key, value, old in pairs:
            if value != old:
                set_patch(document, key, value)
                if document is w:
                    changed_w = True
                else:
                    changed_d = True
        data = dict(self.raw)
        for name, document, changed in [('weasel.custom.yaml', w, changed_w), ('default.custom.yaml', d, changed_d)]:
            if changed:
                data[name] = dump_yaml(document).encode('utf-8')
        for name, table, entries in [('flypy_personal.dict.yaml', self.words, words), ('flypy_phrases.txt', self.phrases, phrases)]:
            if entries != table.entries:
                data[name] = table.render(entries).encode('utf-8')
        return {name: value for name, value in data.items() if value != self.raw[name]}

    def backup(self, reason='手動備份'):
        self.assert_unchanged()
        destination = self.backup_root / datetime.now().strftime('%Y%m%d-%H%M%S-%f')
        destination.mkdir(parents=True)
        for name, data in self.raw.items():
            if data is not None:
                (destination / name).parent.mkdir(parents=True, exist_ok=True)
                (destination / name).write_bytes(data)
        manifest = {'version': VERSION, 'reason': reason, 'user_dir': str(self.root),
                    'time': datetime.now().isoformat(timespec='seconds'),
                    'hashes': {name: digest(data) for name, data in self.raw.items() if data is not None},
                    'absent': [name for name, data in self.raw.items() if data is None]}
        (destination / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
        return destination

    def commit_bytes(self, changes, reason):
        self.assert_unchanged()
        if not changes:
            return None
        backup = self.backup(reason)
        staged, written = {}, []
        try:
            for name, value in changes.items():
                if name not in self.raw:
                    raise SettingsError('拒絕寫入個人設定範圍以外的檔案。')
                if value is None:
                    continue
                (self.root / name).parent.mkdir(parents=True, exist_ok=True)
                handle, path = tempfile.mkstemp(prefix='.flypy-settings-', suffix='.tmp', dir=(self.root / name).parent)
                staged[name] = Path(path)
                with os.fdopen(handle, 'wb') as stream:
                    stream.write(value)
                    stream.flush()
                    os.fsync(stream.fileno())
            self.assert_unchanged()
            for name, path in staged.items():
                os.replace(path, self.root / name)
                written.append(name)
            for name, value in changes.items():
                if value is None:
                    (self.root / name).unlink(missing_ok=True)
                    written.append(name)
        except Exception:
            for name in reversed(written):
                if self.raw[name] is None:
                    (self.root / name).unlink(missing_ok=True)
                else:
                    self.atomic_write(self.root / name, self.raw[name])
            raise
        finally:
            for path in staged.values():
                path.unlink(missing_ok=True)
        self.load()
        return backup

    @staticmethod
    def atomic_write(path, data):
        handle, temp = tempfile.mkstemp(prefix='.flypy-restore-', dir=path.parent)
        try:
            with os.fdopen(handle, 'wb') as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temp, path)
        finally:
            Path(temp).unlink(missing_ok=True)

    def save(self, appearance, words, phrases):
        return self.commit_bytes(self.build(appearance, words, phrases), '套用設定前')

    def list_backups(self):
        if not self.backup_root.exists():
            return []
        return sorted([p for p in self.backup_root.iterdir() if p.is_dir() and (p / 'manifest.json').is_file()], reverse=True)

    def restore(self, source):
        source = Path(source).resolve()
        if source.parent != self.backup_root.resolve():
            raise SettingsError('只能還原此工具建立的個人設定備份。')
        manifest = json.loads((source / 'manifest.json').read_text(encoding='utf-8'))
        names = set(manifest['hashes']) | set(manifest.get('absent', []))
        if not set(FILES) <= names or not names <= set(self.raw):
            raise SettingsError('備份檔案清單不相容，未還原。')
        data = {name: (source / name).read_bytes() for name in manifest['hashes']}
        for name, value in data.items():
            if digest(value) != manifest['hashes'].get(name):
                raise SettingsError(f'備份完整性檢查失敗：{name}，未還原。')
            if name.endswith('.custom.yaml'):
                document = yaml_parser().load(value.decode('utf-8-sig'))
                if not isinstance(document, dict) or not isinstance(document.get('patch'), dict):
                    raise SettingsError(f'備份設定格式不正確：{name}')
        for name, chinese in [('flypy_personal.dict.yaml', True), ('flypy_phrases.txt', False)]:
            Table(name, data[name].decode('utf-8-sig'), chinese)
        data.update({name: None for name in manifest.get('absent', [])})
        return self.commit_bytes({k: v for k, v in data.items() if v != self.raw[k]}, '還原前的安全備份')

    def assert_active_user_dir(self):
        # Official WeaselDeployer reads the registry, ignoring --user-dir.
        if os.name == 'nt':
            active, _ = discover_paths()
            if os.path.normcase(str(active.resolve())) != os.path.normcase(str(self.root.resolve())):
                raise SettingsError('這是設定副本，不是小狼毫目前使用的資料夾；已阻止部署或詞頻匯出，正式輸入法未改動。')

    def deploy(self):
        self.assert_active_user_dir()
        from quick_learning import prepare_io
        io_changes = prepare_io(self,{})
        if io_changes:
            self.commit_bytes(io_changes,'更新目前電腦的檔案路徑相容資料')
        if not self.weasel_root:
            raise SettingsError('找不到小狼毫程式位置；設定已儲存，請從開始選單重新部署。')
        server, deployer = (self.weasel_root / n for n in ['WeaselServer.exe', 'WeaselDeployer.exe'])
        if not server.is_file() or not deployer.is_file():
            raise SettingsError('小狼毫程式檔不存在，無法重新部署。')
        flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
        options = dict(creationflags=flags, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        # Official deployer suspends/resumes the existing server through IPC.
        result = subprocess.run([str(deployer), '/deploy'], timeout=180, **options)
        if result.returncode:
            raise SettingsError(f'部署程式回報失敗（{result.returncode}）。設定已備份，可用「備份與還原」恢復。')
        expected = self.appearance
        d = yaml_parser().load((self.root / 'build' / 'default.yaml').read_text(encoding='utf-8-sig'))
        w = yaml_parser().load((self.root / 'build' / 'weasel.yaml').read_text(encoding='utf-8-sig'))
        checks = [d['menu']['page_size'] == expected.page_size,
                  w['style']['font_point'] == expected.font_size,
                  w['style']['label_font_point'] == expected.label_size,
                  w['style']['comment_font_point'] == expected.comment_size,
                  w['style']['font_face'] == expected.font_face,
                  w['style']['horizontal'] == expected.horizontal,
                  d['ascii_composer']['switch_key']['Shift_L'] == expected.shift_left,
                  d['ascii_composer']['switch_key']['Shift_R'] == expected.shift_right]
        if not all(checks):
            raise SettingsError('部署後讀回的設定不相符，請查看部署記錄或還原備份。')


def discover_paths():
    import winreg
    user_dir = os.path.join(os.environ.get('APPDATA', str(Path.home() / 'AppData' / 'Roaming')), 'Rime')
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'Software\Rime\Weasel') as key:
            user_dir = winreg.QueryValueEx(key, 'RimeUserDir')[0] or user_dir
    except OSError:
        pass
    weasel = None
    for access in [winreg.KEY_READ | winreg.KEY_WOW64_32KEY, winreg.KEY_READ | winreg.KEY_WOW64_64KEY]:
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r'Software\Rime\Weasel', 0, access) as key:
                weasel = winreg.QueryValueEx(key, 'WeaselRoot')[0]
                break
        except OSError:
            continue
    return Path(user_dir), Path(weasel) if weasel else None


def refresh_flypy_patches(source, user_dir):
    """Refresh only generated spelling rules; retain all other personal patches."""
    source = Path(source)
    store = Store(user_dir)
    changes = {}
    def rules(path, name):
        # Read only algebra blocks. Upstream pin-candidate plain scalars can
        # contain literal tabs accepted by Rime but rejected by ruamel.yaml.
        lines = path.read_text(encoding='utf-8-sig').splitlines(keepends=True)
        selected, collecting = [], False
        for line in lines:
            if re.match(r'^[A-Za-z_][A-Za-z_0-9]*:', line):
                collecting = bool(re.match(r'^(algebra_common|algebra_double_pinyin_flypy):', line))
            if collecting:
                selected.append(line)
        document = yaml_parser().load(''.join(selected)) or {}
        node = document['algebra_double_pinyin_flypy']
        if name == 'melt_eng':
            if not isinstance(node, dict) or node.get('__include') != 'algebra_common' or not isinstance(node.get('__append'), list):
                raise SettingsError('上游英文小鶴規則結構已變更，請人工檢查。')
            value = list(document['algebra_common']) + list(node['__append'])
        else:
            value = list(node) if isinstance(node, list) else []
        if len(value) < 10 or not all(isinstance(v, str) for v in value):
            raise SettingsError('上游小鶴規則格式不相容；尚未寫入。')
        return value
    for name in ('melt_eng', 'radical_pinyin'):
        new = rules(source / f'{name}.schema.yaml', name)
        old = rules(store.root / f'{name}.schema.yaml', name)
        filename = f'{name}.custom.yaml'
        raw = store.raw[filename]
        document = yaml_parser().load(raw.decode('utf-8-sig')) if raw else {'patch': {}}
        existing = get_patch(document, 'speller/algebra')
        # If edited in the new settings UI, retain the user's deliberate rule set.
        if existing is not None and existing != old:
            continue
        if existing != new:
            set_patch(document, 'speller/algebra', new)
            changes[filename] = dump_yaml(document).encode('utf-8')
    return store.commit_bytes(changes, '更新雾凇拼寫規則前')

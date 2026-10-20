"""Source-aware catalogue of the installed Rime configuration, saved as patches."""
from __future__ import annotations
import copy
import re
from dataclasses import dataclass
from settings_core import SettingsError, dump_yaml, get_patch, set_patch, yaml_parser
from setting_help import info

SCOPES = {'weasel': '小狼毫介面', 'default': '全域與按鍵',
          'double_pinyin_flypy': '小鶴雙拼', 'melt_eng': '英文方案',
          'radical_pinyin': '拆字反查'}
CATEGORIES = ['全部', '介面與配色', '按鍵與選字', '繁簡與標點', '詞庫與排序', '日期與工具', '進階結構', '常用設定']
LABELS = {
 'style/color_scheme': '淺色模式配色', 'style/color_scheme_dark': '深色模式配色',
 'style/font_point': '候選字級', 'style/label_font_point': '數字字級',
 'style/comment_font_point': '註解字級', 'style/font_face': '候選字體',
 'style/horizontal': '橫向排列候選', 'style/inline_preedit': '在應用程式內顯示編碼',
 'style/display_tray_icon': '顯示輸入法狀態圖示', 'style/layout/corner_radius': '候選視窗圓角',
 'style/layout/round_corner': '選取項目圓角', 'style/layout/spacing': '編碼與候選間距',
 'style/layout/candidate_spacing': '候選之間的間距', 'global_ascii': '跨應用程式共用中英狀態',
 'menu/page_size': '每頁候選數', 'switches': '預設繁簡、Emoji、中英及全半形',
 'ascii_composer': 'Shift、Caps Lock 與中英切換', 'key_binder/bindings': '快捷鍵與翻頁按鍵',
 'ascii_composer/good_old_caps_lock': 'Caps Lock 使用傳統大寫鎖定',
 'translator/enable_user_dict': '記憶個人詞頻', 'translator/enable_sentence': '自動組句與長句',
 'translator/enable_word_completion': '未完整輸入時補全詞語',
 'translator/initial_quality': '中文候選的相對優先度', 'translator/spelling_hints': '拼音提示長度',
 'melt_eng/enable_completion': '英文長詞自動補全', 'cn_en/enable_completion': '中英混輸長詞自動補全',
 'flypy_english/original_first': '英文候選先保留原始大小寫',
 'melt_eng/initial_quality': '英文候選的相對優先度', 'cn_en/initial_quality': '中英混輸優先度',
 'traditionalize/opencc_config': '繁體與台灣用語轉換規則', 'emoji/opencc_config': 'Emoji 對照表',
 'punctuator/half_shape': '中文半形模式標點表', 'punctuator/full_shape': '中文全形模式標點表',
 'date_translator': '日期、時間與星期的呼叫碼', 'lunar': '農曆呼叫碼',
 'lunar_template': '農曆輸出格式', 'recognizer/patterns': '網址、Email、反查與工具辨識',
 'engine/translators': '啟用的輸入與工具模組', 'engine/filters': '候選處理與過濾模組',
 'schema_list': '啟用的輸入方案', 'switcher/hotkeys': '輸入方案選單快捷鍵',
 'speller/algebra': '雙拼鍵位與拼寫規則（進階）', 'app_options': '各應用程式的個別設定',
 'pin_cand_filter': '固定優先候選表', 'reduce_english_filter': '降低英文干擾的規則',
}

def category(path):
    first = path.split('/')[0]
    if first in ('style', 'preset_color_schemes', 'app_options', 'global_ascii', 'show_notifications', 'show_notifications_time'):
        return CATEGORIES[1]
    if first in ('ascii_composer', 'key_binder', 'editor', 'menu', 'switcher', 'speller'):
        return CATEGORIES[2]
    if first in ('switches', 'traditionalize', 'punctuator', 'emoji'):
        return CATEGORIES[3]
    if first in ('translator', 'melt_eng', 'cn_en', 'custom_phrase', 'pin_cand_filter', 'reduce_english_filter', 'flypy_learning', 'flypy_english'):
        return CATEGORIES[4]
    if first in ('date_translator', 'lunar', 'lunar_template', 'recognizer', 'radical_lookup', 'radical_reverse_lookup', 'unicode', 'number_translator'):
        return CATEGORIES[5]
    return CATEGORIES[6]

@dataclass
class Setting:
    scope: str
    path: str
    value: object
    @property
    def label(self):
        return LABELS.get(self.path, info(self.path,self.value)[0])
    @property
    def description(self):
        return info(self.path,self.value)[1]
    @property
    def kind(self):
        return '開關' if isinstance(self.value, bool) else '整數' if isinstance(self.value, int) else '數值' if isinstance(self.value, float) else '群組 / 清單' if isinstance(self.value, (list, dict)) else '文字'

class Catalogue:
    def __init__(self, store):
        self.store, self.pending, self.items, self.effective = store, {}, [], {}
        for scope in SCOPES:
            name = f'{scope}.yaml' if scope in ('default', 'weasel') else f'{scope}.schema.yaml'
            path = store.root / 'build' / name
            if not path.is_file():
                continue
            document = yaml_parser().load(path.read_text(encoding='utf-8-sig')) or {}
            # Saving without deploying still needs to show the saved overrides.
            raw = store.raw.get(f'{scope}.custom.yaml')
            custom = yaml_parser().load(raw.decode('utf-8-sig')) if raw else {}
            for patch_path, patch_value in custom.get('patch', {}).items():
                if not isinstance(patch_path, str) or any(p.startswith('@') or p.startswith('__') for p in patch_path.split('/')):
                    continue
                node = document
                parts = patch_path.split('/')
                for part in parts[:-1]:
                    if not isinstance(node.get(part), dict):
                        node[part] = {}
                    node = node[part]
                node[parts[-1]] = copy.deepcopy(patch_value)
            self.effective[scope] = document
            self.walk(scope, '', document)

    def walk(self, scope, prefix, value):
        if prefix:
            self.items.append(Setting(scope, prefix, copy.deepcopy(value)))
        # Literal slash keys (e.g. punctuation /) are edited in the parent map.
        if isinstance(value, dict) and not any('/' in str(k) for k in value):
            for key, child in value.items():
                if str(key).startswith('__') or key in ('config_version', 'schema', 'uuid'):
                    continue
                self.walk(scope, f'{prefix}/{key}'.strip('/'), child)

    def stage(self, item, value):
        key = (item.scope, item.path)
        if item.value is not None and type(value) != type(item.value) and not (isinstance(item.value, float) and type(value) in (float, int)):
            # ruamel containers and scalar strings are subclasses of the builtin types.
            types = (dict, list, bool, int, float, str, type(None))
            if next((t for t in types if isinstance(value, t)), None) != next((t for t in types if isinstance(item.value, t)), None):
                raise SettingsError(f'此設定需要 {item.kind}，請保持原本的資料類型。')
        if isinstance(value, float) and (value != value or abs(value) == float('inf')):
            raise SettingsError('數值不能是 NaN 或無限大。')
        if item.path in ('flypy_learning/io_path_hex','flypy_learning/io_path_utf8_hex'):
            raise SettingsError('這是工具自動管理的 Windows 路徑相容資料，請勿手動修改。')
        if item.path == 'flypy_learning/max_word_length' and not 1 <= value <= 128:
            raise SettingsError('自動保存的最長字數請填 1～128。')
        if item.path == 'menu/page_size' and not 5 <= value <= 9:
            raise SettingsError('每頁候選數請填 5～9。')
        if item.path in ('style/font_point', 'style/label_font_point', 'style/comment_font_point'):
            low, high = (10, 40) if item.path == 'style/font_point' else (8, 30)
            if not low <= value <= high:
                raise SettingsError(f'字級請填 {low}～{high}。')
        if item.path == 'switches':
            if not isinstance(value, list) or not all(isinstance(s, dict) and isinstance(s.get('name'), str) and ('reset' not in s or s['reset'] in (0, 1)) for s in value):
                raise SettingsError('開關必須有 name，reset 必須是 0 或 1。')
        if item.path.startswith('engine/') and isinstance(value, list) and not all(isinstance(x, str) for x in value):
            raise SettingsError('引擎模組清單必須全部是文字。')
        for scope, path in self.pending:
            if scope == item.scope and path != item.path and (path.startswith(item.path + '/') or item.path.startswith(path + '/')):
                raise SettingsError('這個結構有其他尚未儲存的子項目變更。請先儲存或取消子項目變更。')
        if value == item.value:
            self.pending.pop(key, None)
        else:
            self.pending[key] = copy.deepcopy(value)

    def build(self, base):
        result = dict(base)
        docs = {}
        for (scope, path), value in self.pending.items():
            name = f'{scope}.custom.yaml'
            if name not in self.store.raw:
                raise SettingsError('這個設定檔不在可修改的範圍。')
            if name not in docs:
                data = result.get(name, self.store.raw[name])
                docs[name] = yaml_parser().load(data.decode('utf-8-sig')) if data else {'patch': {}}
            set_patch(docs[name], path, value)
        for name, doc in docs.items():
            result[name] = dump_yaml(doc).encode('utf-8')
        return {k: v for k, v in result.items() if v != self.store.raw[k]}

    def add(self, scope, path, text):
        if scope not in SCOPES or not re.fullmatch(r'[A-Za-z0-9_.@/+ -]+', path) or path.startswith('/') or '..' in path or path.startswith('__'):
            raise SettingsError('請使用有效的設定路徑，例如 style/layout/margin_x。')
        if any(i.scope == scope and i.path == path for i in self.items):
            raise SettingsError('此項目已存在，請從清單選取後編輯。')
        value = yaml_parser().load(text)
        if value is None:
            raise SettingsError('新增設定不能空白。')
        item = Setting(scope, path, None)
        self.items.append(item)
        self.pending[(scope, path)] = value
        return item

    def verify(self):
        for (scope, path), expected in self.pending.items():
            name = f'{scope}.yaml' if scope in ('default', 'weasel') else f'{scope}.schema.yaml'
            document = yaml_parser().load((self.store.root / 'build' / name).read_text(encoding='utf-8-sig'))
            node = document
            for part in path.split('/'):
                node = node.get(part) if isinstance(node, dict) else None
            if node != expected:
                raise SettingsError(f'部署後的設定不相符：{SCOPES[scope]}／{path}。請還原這次調整前的備份。')

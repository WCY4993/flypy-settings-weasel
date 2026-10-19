"""Portable regression checks: no access to an installed user's files."""
import copy
from dataclasses import replace
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch
from settings_core import Store, FILES, get_patch, set_patch, dump_yaml, SettingsError, refresh_flypy_patches
from taiwan_text import TaiwanConverter
from advanced_settings import Catalogue, Setting
from vocabulary import Index, Rules, Rule, RULE_FILE, LUA_FILE
from shortcut_help import manual_rows
from live_preview import documents, rgb

HERE=Path(__file__).parent

class PublicTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        for p in HERE.glob('*.custom.yaml'):shutil.copy2(p,self.root/p.name)
        for name in ['flypy_personal.dict.yaml','flypy_phrases.txt','flypy_tw.dict.yaml']:shutil.copy2(HERE/name,self.root/name)
        self.store=Store(self.root)
    def tearDown(self):self.temp.cleanup()
    def args(self):return self.store.appearance,copy.deepcopy(self.store.words.entries),copy.deepcopy(self.store.phrases.entries)
    def test_multiline_width_saved_and_range_checked(self):
        catalogue=Catalogue(self.store)
        item=Setting('weasel','style/layout/max_width',0)
        for bad in [-1,4001]:
            with self.assertRaises(SettingsError):catalogue.stage(item,bad)
        catalogue.stage(item,420)
        self.store.commit_bytes(catalogue.build({}),'test')
        self.assertEqual(get_patch(__import__('settings_core').yaml_parser().load((self.root/'weasel.custom.yaml').read_text(encoding='utf-8')),'style/layout/max_width'),420)
    def test_public_personal_tables_are_empty(self):
        self.assertEqual(self.store.words.entries,[]);self.assertEqual(self.store.phrases.entries,[])
    def test_noop_is_exact_and_has_no_backup(self):
        before={n:(self.root/n).read_bytes() for n in FILES};self.assertIsNone(self.store.save(*self.args()));self.assertEqual(before,{n:(self.root/n).read_bytes() for n in FILES});self.assertFalse(self.store.backup_root.exists())
    def test_add_save_backup_restore_preserves_learning(self):
        db=self.root/'rime_ice.userdb';db.mkdir();(db/'sentinel').write_bytes(b'unchanged')
        a,words,phrases=self.args();words.append(self.store.normalize_word('測試詞','ce shi ci',10000));backup=self.store.save(replace(a,font_size=18),words,phrases)
        self.assertEqual(self.store.words.entries[0].text,'测试词');self.assertEqual(self.store.appearance.font_size,18)
        self.store.restore(backup);self.assertEqual(self.store.words.entries,[]);self.assertEqual((db/'sentinel').read_bytes(),b'unchanged')
    def test_external_change_is_not_overwritten(self):
        p=self.root/'weasel.custom.yaml';p.write_text(p.read_text(encoding='utf-8')+'\n# external\n',encoding='utf-8')
        with self.assertRaises(SettingsError):self.store.save(*self.args())
    def test_partial_commit_rolls_back(self):
        import settings_core
        original=settings_core.os.replace;count=0
        def fail(a,b):
            nonlocal count
            count+=1
            if count==2:raise OSError('interrupted')
            return original(a,b)
        before=(self.root/'default.custom.yaml').read_bytes()
        with patch('settings_core.os.replace',side_effect=fail):
            with self.assertRaises(OSError):self.store.commit_bytes({'default.custom.yaml':b'patch: {}\n',RULE_FILE:b'# rule\n'},'test')
        self.assertEqual((self.root/'default.custom.yaml').read_bytes(),before);self.assertFalse((self.root/RULE_FILE).exists())
    def test_vocabulary_preserved_including_long_terms(self):
        c=TaiwanConverter()
        for a,b in [('设置项目','設置項目'),('软件工程','軟件工程'),('信息安全','信息安全'),('网络视频','網絡視頻'),('打印机','打印機'),('鼠标数据库','鼠標數據庫'),('头发','頭髮')]:self.assertEqual(c.convert(a),b)
    def test_explicit_regional_choice_remains_optional(self):
        self.assertEqual(TaiwanConverter(config='s2twp.json').convert('软件'),'軟體')
        self.assertEqual(TaiwanConverter().convert('软件'),'軟件')
    def test_parent_patch_removes_overlapping_flattened_keys(self):
        d={'patch':{'style/layout/corner_radius':8,'style/font_point':16}}
        set_patch(d,'style/layout',{'corner_radius':10});self.assertNotIn('style/layout/corner_radius',d['patch']);self.assertEqual(get_patch(d,'style/font_point'),16)
    @unittest.skipUnless(os.name=='nt','Windows deployment guard')
    def test_fixture_deploy_blocked_before_server_is_touched(self):
        with patch('settings_core.discover_paths',return_value=(self.root/'other',None)),patch('settings_core.subprocess.run') as run:
            with self.assertRaisesRegex(SettingsError,'設定副本'):self.store.deploy()
            run.assert_not_called()
    def test_bad_entry_and_range_rejected(self):
        with self.assertRaises(SettingsError):self.store.normalize_word('測試詞','ce shi',10000)
        a,w,p=self.args()
        with self.assertRaises(SettingsError):self.store.save(replace(a,font_size=-1),w,p)
    def test_preview_does_not_mutate_config(self):
        from types import SimpleNamespace
        cat=SimpleNamespace(effective={'weasel':{'style':{'font_point':16}}},pending={('weasel','style/font_point'):20});before=copy.deepcopy(cat.effective)
        self.assertEqual(documents(cat)['weasel']['style']['font_point'],20);self.assertEqual(cat.effective,before);self.assertEqual(rgb(0x0000ff),'#ff0000')
    def test_manual_follows_changed_shortcuts(self):
        d={'default':{'ascii_composer':{'switch_key':{'Shift_R':'noop'}}},'double_pinyin_flypy':{'key_binder':{'bindings':[{'accept':'Control+Shift+4','toggle':'traditionalization','when':'always'}]},'date_translator':{'date':'today'}}}
        rows=manual_rows(d);self.assertTrue(any('右 Shift' in r[1] and '不切換' in r[2] for r in rows));self.assertTrue(any(r[1]=='today' for r in rows));self.assertTrue(any('繁體' in r[2] for r in rows))
    def test_index_preserves_search_terms_and_english(self):
        (self.root/'cn_dicts').mkdir();(self.root/'cn_dicts/base.dict.yaml').write_text('---\nname: base\n...\n软件\truan jian\t100\n软体\truan ti\t90\n',encoding='utf-8')
        (self.root/'en_dicts').mkdir();(self.root/'en_dicts/en.dict.yaml').write_text('---\nname: en\n...\nHello\thello\t10\n',encoding='utf-8')
        index=Index(self.root);index.folder=self.root/'cache';index.path=index.folder/'index.sqlite3';index.rebuild()
        self.assertEqual(index.query('軟件')[0][0]['text'],'软件');self.assertEqual(index.query('軟體')[0][0]['text'],'软体');self.assertEqual(index.query('hello')[0][0]['text'],'Hello')
    def test_updater_handles_upstream_tabs_outside_algebra(self):
        source=self.root/'new';source.mkdir()
        for name in ('melt_eng','radical_pinyin'):
            rules=['derive/^x$/x/']*10
            doc={'algebra_common':rules,'algebra_double_pinyin_flypy':{'__include':'algebra_common','__append':rules}} if name=='melt_eng' else {'algebra_double_pinyin_flypy':rules}
            text=dump_yaml(doc)+'pin_cand_filter:\n  - d\t的\n'
            for target in [self.root,source]:(target/(name+'.schema.yaml')).write_text(text,encoding='utf-8')
        doc=self.store.read_yaml('radical_pinyin.custom.yaml');set_patch(doc,'speller/algebra',rules)
        (self.root/'radical_pinyin.custom.yaml').write_text(dump_yaml(doc),encoding='utf-8')
        refresh_flypy_patches(source,self.root)
        self.store.load()
        self.assertEqual(len(get_patch(self.store.read_yaml('radical_pinyin.custom.yaml'),'speller/algebra')),10)

if __name__=='__main__':unittest.main()

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

class PageNavigationTests(unittest.TestCase):
    def test_page_bounds_and_display_numbers(self):
        from settings_pages import vocabulary_page_number
        self.assertEqual(vocabulary_page_number(' 18 ',132367),17)
        self.assertEqual(vocabulary_page_number('1324',132367),1323)
        self.assertEqual(vocabulary_page_number('１',0),0)
        for value in ['', '0', '-1', '1325', '1.5', 'abc', '9'*5000]:
            with self.subTest(value=value[:20]),self.assertRaises(SettingsError):
                vocabulary_page_number(value,132367)

    def test_jump_cancels_pending_search_and_keeps_current_filters(self):
        from settings_pages import VocabularyPage
        from types import SimpleNamespace
        from unittest.mock import Mock
        page=SimpleNamespace(page_input=Mock(get=lambda:'18'),total_matches=132367,
                             timer='pending',page=0,after_cancel=Mock(),request=Mock())
        self.assertEqual(VocabularyPage.jump(page),'break')
        self.assertEqual(page.page,17)
        page.after_cancel.assert_called_once_with('pending')
        self.assertIsNone(page.timer)
        page.request.assert_called_once_with()

    def test_invalid_jump_preserves_current_page(self):
        from settings_pages import VocabularyPage
        from types import SimpleNamespace
        from unittest.mock import Mock
        page=SimpleNamespace(page_input=Mock(get=lambda:'0'),total_matches=201,
                             page=1,page_entry=Mock(),request=Mock())
        with patch('settings_pages.messagebox.showinfo') as info:
            self.assertEqual(VocabularyPage.jump(page),'break')
        self.assertEqual(page.page,1)
        page.request.assert_not_called()
        info.assert_called_once()

class PublicTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        for p in HERE.glob('*.custom.yaml'):shutil.copy2(p,self.root/p.name)
        for name in ['flypy_personal.dict.yaml','flypy_phrases.txt','flypy_tw.dict.yaml']:shutil.copy2(HERE/name,self.root/name)
        self.store=Store(self.root)
    def tearDown(self):self.temp.cleanup()
    def args(self):return self.store.appearance,copy.deepcopy(self.store.words.entries),copy.deepcopy(self.store.phrases.entries)
    def test_personal_variants_are_independent_after_reload(self):
        a,w,p=self.args()
        w += [self.store.normalize_word(t,'fen bu',10000) for t in ['分布','分佈']]
        self.store.save(a,w,p)
        self.assertEqual([e.text for e in self.store.words.entries],['分布','分佈'])
        self.store.save(a,self.store.words.entries[1:],p)
        self.assertEqual([e.text for e in self.store.words.entries],['分佈'])
    def test_learning_journal_replay_keeps_variants_and_partial_append(self):
        from quick_learning import records
        (self.root/'flypy_learning.tsv').write_text('t\tffbu\t分布\t1\t0\nt\tffbu\t分佈\t1\t1\nt\tffbu\t分布\t2\t2\ns\tffbu\t分布\t3\t0\nt\tffbu',encoding='utf-8')
        r=records(self.root)
        self.assertEqual(len(r),3)
        self.assertEqual(r[0],('分布','ffbu','選用 2 次；繁體'))
        self.assertEqual(r[1][0],'分佈')
    def test_learning_journal_is_indexed_without_duplicate_history(self):
        (self.root/'flypy_learning.tsv').write_text('t\tffbu\t分布\t1\t0\nt\tffbu\t分布\t2\t1\nt\tffbu\t分佈\t1\t2\n',encoding='utf-8')
        index=Index(self.root);index.folder=self.root/'cache';index.path=index.folder/'index.sqlite3';index.rebuild()
        r=index.query(kind='自動學習')[0]
        self.assertEqual({x['text'] for x in r},{'分布','分佈'})
        self.assertEqual(len(r),2)
        self.assertEqual({x['text'] for x in index.query('分布',kind='自動學習')[0]},{'分布','分佈'})
        self.assertEqual(index.query(exclude_personal=True)[0],[])
    def test_exact_rows_render_without_conversion(self):
        from quick_learning import row_text
        rules=Rules(self.store)
        self.assertEqual(row_text(rules,dict(text='分布',source='flypy_learning.tsv')),'分布')
        self.assertEqual(row_text(rules,dict(text='师范',source='flypy_personal.dict.yaml')),'師範')
        self.assertEqual(row_text(rules,dict(text='分佈',source='flypy_personal.dict.yaml')),'分佈')
        self.assertEqual(row_text(rules,dict(text='台灣',source='flypy_taiwan.dict.yaml')),'台灣')

    def test_taiwan_dictionary_upgrade_preserves_imports_and_personal_words(self):
        from quick_learning import prepare_io
        a,w,p=self.args()
        w.append(self.store.normalize_word('台','tai',10000))
        self.store.save(a,w,p)
        before=self.store.raw['flypy_personal.dict.yaml']
        changes=prepare_io(self.store,{})
        self.store.commit_bytes(changes,'Taiwan dictionary upgrade')
        self.assertEqual(self.store.raw['flypy_personal.dict.yaml'],before)
        from settings_core import yaml_parser
        imports=yaml_parser().load(self.store.raw['flypy_tw.dict.yaml'].decode('utf-8'))['import_tables']
        self.assertEqual(imports.count('flypy_taiwan'),1)
        self.assertIn('cn_dicts/base',imports)
        self.assertEqual(prepare_io(self.store,{}),{})

    def test_taiwan_dictionary_is_indexed_as_independent_spellings(self):
        (self.root/'flypy_taiwan.dict.yaml').write_text('---\nname: flypy_taiwan\n...\n台灣\ttai wan\t100\n臺灣\ttai wan\t80\n台\ttai\t100\n',encoding='utf-8')
        index=Index(self.root);index.folder=self.root/'cache';index.path=index.folder/'index.sqlite3';index.rebuild()
        rows=index.query(kind='台灣詞庫')[0]
        self.assertEqual({r['text'] for r in rows},{'台灣','臺灣','台'})

    def test_taiwan_source_retains_required_words_and_no_simplified_only_glyphs(self):
        from glyph_normalization import normalize_glyphs
        words={}
        for line in (HERE/'flypy_taiwan.dict.yaml').read_text(encoding='utf-8').splitlines():
            if '\t' in line:
                text,code,weight=line.split('\t')
                self.assertEqual(normalize_glyphs(text),text)
                words.setdefault(text,set()).add(code)
        for text,code in [('台灣','tai wan'),('臺灣','tai wan'),('網路','wang lu'),('資訊','zi xun'),('捷運','jie yun')]:
            self.assertIn(code,words[text])
    @unittest.skipUnless(os.name=='nt','Windows CRT path compatibility')
    def test_runtime_upgrade_preserves_learning_and_prepares_both_encodings(self):
        from quick_learning import prepare_io
        (self.root/'flypy_learning.tsv').write_bytes(b't\tsj\tword\t1\t0\n')
        before=(self.root/'flypy_learning.tsv').read_bytes()
        changes=prepare_io(self.store,{})
        self.store.commit_bytes(changes,'test upgrade')
        doc=self.store.read_yaml('double_pinyin_flypy.custom.yaml')
        self.assertEqual(bytes.fromhex(get_patch(doc,'flypy_learning/io_path_utf8_hex')).decode(),str(self.store.root))
        self.assertIn('lua_filter@*flypy_learning',get_patch(doc,'engine/filters'))
        self.assertEqual((self.root/'flypy_learning.tsv').read_bytes(),before)
        self.assertEqual(prepare_io(self.store,{}),{})
    def test_exact_traditional_override_survives_save_reload(self):
        rules=Rules(self.store);rules.put(Rule('分布','分布'))
        self.assertEqual(rules.display('分布'),'分布')
        changes=rules.build({},Catalogue(self.store));self.store.commit_bytes(changes,'test')
        again=Rules(self.store)
        self.assertEqual(again.display('分布'),'分布')
        self.assertEqual(again.rows['分布'].replacement,'分布')
        self.assertEqual(again.rows['分布'].traditional,'分布')
        again.put(Rule('分布','分佈'))
        self.assertEqual(again.display('分布'),'分佈')
    def test_explicit_characters_are_not_collapsed(self):
        rules=Rules(self.store)
        for target in ['臺灣','台灣','乾','幹','干','佈','布']:
            rules.put(Rule('測試',target,'pin'))
            self.assertEqual(rules.output(rules.rows['測試']),target)
        with self.assertRaises(SettingsError):rules.put(Rule('測試','布','pin',traditional='布\t'))
    def test_financial_override_keeps_simplified_financial_character(self):
        rules=Rules(self.store);rules.put(Rule('叁','參'))
        self.assertEqual(rules.rows['叁'].replacement,'叁')
        self.assertEqual(rules.display('叁'),'參')
    def test_general_financial_glyph(self):
        self.assertEqual(TaiwanConverter().convert('叁叄参'),'參參參')
    def test_public_personal_tables_are_empty(self):
        self.assertEqual(self.store.words.entries,[]);self.assertEqual(self.store.phrases.entries,[])
    def test_noop_is_exact_and_has_no_backup(self):
        before={n:(self.root/n).read_bytes() for n in FILES};self.assertIsNone(self.store.save(*self.args()));self.assertEqual(before,{n:(self.root/n).read_bytes() for n in FILES});self.assertFalse(self.store.backup_root.exists())
    def test_add_save_backup_restore_preserves_learning(self):
        db=self.root/'rime_ice.userdb';db.mkdir();(db/'sentinel').write_bytes(b'unchanged')
        a,words,phrases=self.args();words.append(self.store.normalize_word('測試詞','ce shi ci',10000));backup=self.store.save(replace(a,font_size=18),words,phrases)
        self.assertEqual(self.store.words.entries[0].text,'測試詞');self.assertEqual(self.store.appearance.font_size,18)
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
    def test_search_finds_the_replacement_name(self):
        (self.root/'cn_dicts').mkdir();(self.root/'cn_dicts/base.dict.yaml').write_text('---\nname: base\n...\n原名\tyuan ming\t100\n',encoding='utf-8')
        index=Index(self.root);index.folder=self.root/'cache';index.path=index.folder/'index.sqlite3';index.rebuild()
        self.assertEqual(index.query('新名',extra_terms=['原名'])[0][0]['text'],'原名')
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

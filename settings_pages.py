"""Categorized settings and a single vocabulary browser using the existing ttk UI."""
from __future__ import annotations
import copy
from dataclasses import replace
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
import queue
import threading
import tkinter as tk
from tkinter import ttk, messagebox, filedialog, colorchooser
from advanced_settings import Catalogue, CATEGORIES, SCOPES, Setting, category, LABELS
from settings_core import SettingsError, dump_yaml, yaml_parser, SHIFT_MODES
from vocabulary import Index, Rules, Rule, display, refresh_learned
from setting_help import info, shown_value, VALUES
from taiwan_text import CONVERSION_CHOICES
from live_preview import LivePreview, preview_kind

def position_dialog(dialog, owner, width=None, height=None):
    dialog.update_idletasks()
    width = min(width or dialog.winfo_reqwidth(), dialog.winfo_screenwidth()-80)
    height = min(height or dialog.winfo_reqheight(), dialog.winfo_screenheight()-100)
    x = max(20, min(owner.winfo_rootx() + (owner.winfo_width()-width)//2, dialog.winfo_screenwidth()-width-20))
    y = max(20, min(owner.winfo_rooty() + (owner.winfo_height()-height)//2, dialog.winfo_screenheight()-height-70))
    dialog.geometry(f'{width}x{height}+{x}+{y}')

def scroll_table(parent, columns):
    frame = ttk.Frame(parent)
    tree = ttk.Treeview(frame, columns=[x[0] for x in columns], show='headings', selectmode='browse', height=7)
    for key, text, width in columns:
        tree.heading(key, text=text)
        tree.column(key, width=width, minwidth=60)
    vertical = ttk.Scrollbar(frame, orient='vertical', command=tree.yview)
    horizontal = ttk.Scrollbar(frame, orient='horizontal', command=tree.xview)
    tree.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
    frame.rowconfigure(0, weight=1); frame.columnconfigure(0, weight=1)
    tree.grid(row=0, column=0, sticky='nsew')
    vertical.grid(row=0, column=1, sticky='ns'); horizontal.grid(row=1, column=0, sticky='ew')
    return frame, tree

class StructureEditor(ttk.Frame):
    """A visual editor for arbitrary YAML maps/lists without requiring YAML typing."""
    def __init__(self, parent, value, path='', changed=None):
        super().__init__(parent)
        self.value = copy.deepcopy(value)
        self.setting_path,self.changed=path,changed
        self.help_text=tk.StringVar(value='選取項目後會顯示用途；程式識別碼保留原文。')
        ttk.Label(self,textvariable=self.help_text,style='Muted.TLabel',wraplength=640).pack(side='bottom',fill='x',pady=(6,0))
        buttons = ttk.Frame(self); buttons.pack(side='bottom', fill='x', pady=(8, 0))
        for actions in [[('編輯值', self.edit), ('新增子項', self.add), ('移除', self.remove)], [('上移', lambda: self.move(-1)), ('下移', lambda: self.move(1)), ('完整 YAML…', self.raw)]]:
            row = ttk.Frame(buttons); row.pack(fill='x', pady=2)
            for text, action in actions:
                ttk.Button(row, text=text, command=action).pack(side='left', padx=(0, 4))
        frame = ttk.Frame(self); frame.pack(fill='both', expand=True)
        self.tree = ttk.Treeview(frame, columns=['value', 'type'], show='tree headings', height=7)
        self.tree.heading('#0', text='項目／按鍵'); self.tree.column('#0', width=210)
        self.tree.heading('value', text='設定值'); self.tree.column('value', width=300)
        self.tree.heading('type', text='類型'); self.tree.column('type', width=80)
        bar = ttk.Scrollbar(frame, orient='vertical', command=self.tree.yview)
        self.tree.configure(yscrollcommand=bar.set)
        bar.pack(side='right', fill='y'); self.tree.pack(fill='both', expand=True)
        self.tree.bind('<Double-1>', lambda e: self.edit())
        self.tree.bind('<<TreeviewSelect>>',lambda e:self.describe())
        self.render()

    def render(self):
        self.paths = {}; self.tree.delete(*self.tree.get_children())
        def walk(parent, key, value, path):
            label = '清單' if isinstance(value, list) else '群組' if isinstance(value, dict) else '開關' if isinstance(value, bool) else '數值' if isinstance(value, (int, float)) else '文字'
            preview = shown_value(value)
            iid = str(len(self.paths)); self.paths[iid] = path
            full_path=self.setting_path+'/'+ '/'.join(str(p) for p in path)
            name=info(full_path,value)[0] if path and not isinstance(path[-1],int) else str(key)
            self.tree.insert(parent, 'end', iid=iid, text=name, values=(preview, label), open=len(path) < 2)
            if isinstance(value, dict):
                for k, v in value.items(): walk(iid, k, v, path + (k,))
            elif isinstance(value, list):
                for n, v in enumerate(value): walk(iid, f'第 {n+1} 項', v, path + (n,))
        walk('', '設定內容', self.value, ())
        if self.changed:self.changed()

    def describe(self):
        path,value=self.selected()
        if path is not None:
            full_path=self.setting_path if path and isinstance(path[-1],int) else self.setting_path+'/'+ '/'.join(str(p) for p in path)
            self.help_text.set(info(full_path,value)[1]+'　原始名稱：'+str(path[-1] if path else self.setting_path))

    def selected(self):
        ids = self.tree.selection()
        if not ids: return None, None
        path = self.paths[ids[0]]; value = self.value
        for key in path: value = value[key]
        return path, value

    def parent_node(self, path):
        value = self.value
        for key in path[:-1]: value = value[key]
        return value

    def prompt(self, title, original=None, add=False, mapping=False):
        dialog = tk.Toplevel(self); dialog.title(title); dialog.transient(self.winfo_toplevel()); dialog.grab_set()
        frame = ttk.Frame(dialog, padding=20); frame.pack(fill='both', expand=True)
        key = tk.StringVar(); kind = tk.StringVar(value='文字' if original is None else '開關' if isinstance(original, bool) else '整數' if isinstance(original, int) else '小數' if isinstance(original, float) else '文字')
        value = tk.StringVar(value='開啟' if original is True else '關閉' if original is False else str(original) if original is not None else '')
        if mapping:
            ttk.Label(frame, text='項目名稱／按鍵').pack(anchor='w'); ttk.Entry(frame, textvariable=key, width=50).pack(fill='x', pady=8)
        ttk.Label(frame, text='資料類型').pack(anchor='w')
        options = ['文字', '開關', '整數', '小數'] + (['群組', '清單'] if add else [])
        box = ttk.Combobox(frame, textvariable=kind, values=options, state='readonly' if add else 'disabled', width=22); box.pack(anchor='w', pady=8)
        ttk.Label(frame, text='設定值（開關請填「開啟」或「關閉」；新群組／清單可留空）').pack(anchor='w')
        ttk.Combobox(frame, textvariable=value, values=['開啟', '關閉'], width=50).pack(fill='x', pady=8)
        result = []
        def submit():
            try:
                text = value.get(); label = kind.get()
                if label == '開關' and text not in ('開啟','關閉'): raise ValueError('開關請填「開啟」或「關閉」。')
                parsed = {} if label == '群組' else [] if label == '清單' else text == '開啟' if label == '開關' else int(text, 16) if label == '整數' and text.lower().startswith('0x') else int(text) if label == '整數' else float(text) if label == '小數' else text
                if mapping and not key.get(): raise ValueError('請填項目名稱。')
                result.append((key.get(), parsed)); dialog.destroy()
            except Exception as error: messagebox.showerror('請檢查內容', str(error), parent=dialog)
        ttk.Button(frame, text='確定', command=submit).pack(anchor='e', pady=(10,0))
        position_dialog(dialog, self.winfo_toplevel())
        dialog.bind('<Escape>', lambda e: dialog.destroy())
        self.wait_window(dialog)
        self.winfo_toplevel().grab_set()
        return result[0] if result else None

    def edit(self):
        path, value = self.selected()
        if path is None: return
        if isinstance(value, (list, dict)):
            iid = self.tree.selection()[0]; self.tree.item(iid, open=not self.tree.item(iid, 'open')); return
        result = self.prompt('編輯設定值', value)
        if result:
            if path: self.parent_node(path)[path[-1]] = result[1]
            else: self.value = result[1]
            self.render()

    def add(self):
        path, node = self.selected()
        if path is None: path, node = (), self.value
        if not isinstance(node, (dict,list)):
            messagebox.showinfo('新增項目', '請先選取要新增項目的群組或清單。', parent=self); return
        result = self.prompt('新增設定項目', add=True, mapping=isinstance(node,dict))
        if result:
            key, value = result
            if isinstance(node,dict):
                if key in node: messagebox.showerror('名稱重複', '這個項目已存在。', parent=self); return
                node[key] = value
            else: node.append(value)
            self.render()

    def remove(self):
        path, value = self.selected()
        if path and messagebox.askyesno('移除設定項目', '從這次設定草稿移除此項目？尚未儲存，不會立刻改動輸入法。', parent=self):
            del self.parent_node(path)[path[-1]]; self.render()

    def move(self, delta):
        path, value = self.selected()
        if not path: return
        parent = self.parent_node(path)
        if isinstance(parent,list):
            n = path[-1]; other = n + delta
            if 0 <= other < len(parent):
                parent[n], parent[other] = parent[other], parent[n]; self.render()

    def raw(self):
        dialog = tk.Toplevel(self); dialog.title('完整 YAML 規則'); dialog.transient(self.winfo_toplevel()); dialog.grab_set(); dialog.geometry('740x520')
        frame = ttk.Frame(dialog, padding=18); frame.pack(fill='both', expand=True)
        text = tk.Text(frame, font=('Consolas',11), undo=True, wrap='none')
        controls = ttk.Frame(frame); controls.pack(side='bottom', fill='x', pady=(10,0))
        text.pack(fill='both', expand=True); text.insert('1.0',dump_yaml(self.value))
        def submit():
            try:
                value = yaml_parser().load(text.get('1.0','end-1c'))
                if not isinstance(value,type(self.value)):
                    if not ((isinstance(value,dict) and isinstance(self.value,dict)) or (isinstance(value,list) and isinstance(self.value,list))): raise ValueError('請保持原本的群組／清單類型。')
                self.value = value; self.render(); dialog.destroy()
            except Exception as error: messagebox.showerror('規則格式不正確',str(error),parent=dialog)
        ttk.Button(controls,text='完成',command=submit).pack(side='right')
        position_dialog(dialog, self.winfo_toplevel(), 740, 520)
        self.wait_window(dialog); self.winfo_toplevel().grab_set()

class ValueDialog(tk.Toplevel):
    def __init__(self, owner, item, value, catalogue):
        super().__init__(owner)
        self.item, self.result, self.original, self.catalogue = item, None, value, catalogue
        self.title(item.label)
        self.transient(owner)
        self.geometry('760x570')
        self.minsize(600, 460)
        self.grab_set()
        frame = ttk.Frame(self, padding=22); frame.pack(fill='both', expand=True)
        ttk.Label(frame, text=item.label, style='Section.TLabel').pack(anchor='w')
        ttk.Label(frame, text=f'{SCOPES[item.scope]} → {item.path}', style='Muted.TLabel', wraplength=680).pack(anchor='w', pady=(8, 12))
        ttk.Label(frame,text=item.description,style='Muted.TLabel',wraplength=970).pack(anchor='w',fill='x',pady=(0,12))
        footer = ttk.Frame(frame); footer.pack(side='bottom', fill='x', pady=(12, 0))
        ttk.Button(footer, text='取消', command=self.destroy).pack(side='right')
        ttk.Button(footer, text='完成調整', command=self.submit).pack(side='right', padx=8)
        ttk.Label(footer, text='按主視窗的儲存後才會寫入。', style='Muted.TLabel').pack(side='left')
        content=ttk.Frame(frame);content.pack(fill='both',expand=True)
        frame=ttk.Frame(content);frame.pack(side='left',fill='both',expand=True)
        self.preview=None
        kind=preview_kind(item.scope,item.path)
        if kind:
            preview_frame=ttk.Frame(content,padding=(16,0,0,0));preview_frame.pack(side='right',fill='both',expand=True)
            ttk.Label(preview_frame,text='調整後預覽',style='Section.TLabel').pack(anchor='w',pady=(0,8))
            self.preview=LivePreview(preview_frame,kind)
            self.preview.pack(fill='both',expand=True)
            if item.path=='style/color_scheme':self.preview.mode.set('淺色情境')
            elif item.path=='style/color_scheme_dark':self.preview.mode.set('深色情境')
        self.value_options=None
        self.switch_vars = None
        self.var = tk.StringVar()
        self.editor = None
        self.structure = None
        self.bool_mode = type(value) is bool
        if item.path == 'switches' and isinstance(value, list):
            self.switch_vars = []
            for switch in value:
                if not isinstance(switch, dict) or 'name' not in switch:
                    continue
                states = switch.get('states', ['關閉', '開啟'])
                row = ttk.Frame(frame); row.pack(fill='x', pady=6)
                ttk.Label(row, text={'ascii_mode': '預設中英', 'traditionalization': '預設繁簡', 'ascii_punct': '預設標點', 'emoji': '預設 Emoji', 'full_shape': '全半形', 'search_single_char': '單字模式'}.get(switch['name'], switch['name']), width=15).pack(side='left')
                choices = ['沿用狀態（不強制重設）'] + [str(s) for s in states]
                index = switch.get('reset')
                variable = tk.StringVar(value=choices[index+1] if isinstance(index, int) and 0 <= index < len(states) else choices[0])
                ttk.Combobox(row, textvariable=variable, values=choices, state='readonly', width=31).pack(side='left')
                self.switch_vars.append((switch, variable, choices))
                variable.trace_add('write',lambda *_:self.update_preview())
            ttk.Label(frame, text='套用後，新建立的輸入狀態會採用這些預設值。', style='Muted.TLabel').pack(anchor='w', pady=12)
        elif self.bool_mode:
            self.var.set('開啟' if value else '關閉')
            ttk.Combobox(frame, textvariable=self.var, values=['開啟', '關閉'], state='readonly', width=25).pack(anchor='w')
        elif not isinstance(value, (list, dict)):
            self.var.set(str(value))
            options = None
            if item.path in ('style/color_scheme', 'style/color_scheme_dark'):
                themes=catalogue.effective.get('weasel', {}).get('preset_color_schemes', {})
                self.value_options={str(v.get('name',k))+'（'+k+'）':k for k,v in themes.items()}
            elif '/switch_key/' in item.path:
                self.value_options={shown_value(v):v for v in SHIFT_MODES.values()}
            elif item.path=='traditionalize/opencc_config':
                self.value_options=dict(CONVERSION_CHOICES)
            elif isinstance(value,str) and value in VALUES:
                groups={'style/layout/align_type':['top','center','bottom'],'style/antialias_mode':['default','cleartype','grayscale','aliased'],
                        'style/hover_type':['none','hilite','semi_light'],'style/preedit_type':['composition','preview','preview_all']}
                if item.path in groups:self.value_options={shown_value(v):v for v in groups[item.path]}
            if self.value_options:
                self.value_options.setdefault(shown_value(value),value)
                self.var.set(next(k for k,v in self.value_options.items() if v==value))
                options=list(self.value_options)
            widget = ttk.Combobox(frame, textvariable=self.var, values=options, width=55) if options else ttk.Entry(frame, textvariable=self.var, width=55)
            widget.pack(anchor='w', fill='x')
            widget.focus_set()
            if item.path.endswith('_color') and isinstance(value, int):
                ttk.Button(frame, text='選擇顏色', command=self.pick_color).pack(anchor='w', pady=14)
                ttk.Label(frame, text='保留小狼毫使用的 BGR / ABGR 色碼；選色器不會改掉原本透明度。', style='Muted.TLabel', wraplength=650).pack(anchor='w')
        else:
            ttk.Label(frame, text='展開群組後，雙擊項目即可修改；清單可以新增、移除或調整順序。', style='Muted.TLabel').pack(anchor='w', pady=(0, 8))
            self.structure = StructureEditor(frame, value, item.path, self.update_preview)
            self.structure.pack(fill='both',expand=True)
        self.bind('<Escape>', lambda e: self.destroy())
        self.var.trace_add('write',lambda *_:self.update_preview())
        self.update_preview()
        position_dialog(self, owner, 1100 if self.preview else 780, 700 if self.preview else 600)

    def current_value(self):
        if self.switch_vars is not None:
            value=copy.deepcopy(self.original);by_name={s['name']:s for s in value}
            for switch,variable,choices in self.switch_vars:
                index=choices.index(variable.get())-1
                if index<0:by_name[switch['name']].pop('reset',None)
                else:by_name[switch['name']]['reset']=index
            return value
        if self.structure:return self.structure.value
        if self.bool_mode:return self.var.get()=='開啟'
        if self.value_options:return self.value_options.get(self.var.get(),self.var.get())
        if isinstance(self.original,int):
            text=self.var.get().strip();return int(text,16) if text.lower().startswith('0x') else int(text)
        if isinstance(self.original,float):return float(self.var.get())
        return self.var.get()

    def update_preview(self):
        if not getattr(self,'preview',None):return
        try:
            value=self.current_value()
            config=self.master.preview_documents({(self.item.scope,self.item.path):value})
            forced=self.item.path.split('/')[1] if self.item.path.startswith('preset_color_schemes/') else None
            self.preview.show(config,self.catalogue.store.root,self.item.scope,self.item.path,forced)
        except (ValueError,TypeError,AttributeError,KeyError):
            pass

    def pick_color(self):
        try:
            old = int(self.var.get(), 0)
            initial = f'#{old & 255:02x}{(old >> 8) & 255:02x}{(old >> 16) & 255:02x}'
            rgb, _ = colorchooser.askcolor(initialcolor=initial, parent=self)
            if rgb:
                red, green, blue = map(int, rgb)
                self.var.set(str((old & 0xff000000) | blue << 16 | green << 8 | red))
        except ValueError:
            messagebox.showerror('色碼格式', '請先填整數或 0x 開頭的色碼。', parent=self)

    def submit(self):
        try:
            value = self.current_value()
            self.catalogue.stage(self.item, value)
        except Exception as error:
            messagebox.showerror('設定內容不正確', str(error), parent=self)
            return
        self.result = value
        self.destroy()

class AdvancedPage(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, padding=18)
        self.app = app
        self.search, self.scope = tk.StringVar(), tk.StringVar(value='全部範圍')
        ttk.Label(self, text='所有設定，依用途分類', style='Section.TLabel').pack(anchor='w')
        ttk.Label(self, text='讀取目前安裝版本的完整設定；只把你的調整存入個人覆寫檔。結構項目可開啟完整規則編輯。', style='Muted.TLabel', wraplength=950).pack(anchor='w', pady=(7, 12))
        row = ttk.Frame(self); row.pack(fill='x', pady=(0, 12))
        ttk.Label(row, text='搜尋').pack(side='left')
        ttk.Entry(row, textvariable=self.search).pack(side='left', fill='x', expand=True, padx=8)
        ttk.Combobox(row, textvariable=self.scope, values=['全部範圍'] + list(SCOPES.values()), state='readonly', width=18).pack(side='right')
        buttons = ttk.Frame(self); buttons.pack(side='bottom', fill='x', pady=(12, 0))
        ttk.Button(buttons, text='編輯選取', command=self.edit).pack(side='left')
        ttk.Button(buttons, text='取消未儲存調整', command=self.reset).pack(side='left', padx=8)
        ttk.Button(buttons, text='新增進階設定…', command=self.add).pack(side='left')
        self.count = ttk.Label(buttons, style='Muted.TLabel'); self.count.pack(side='right')
        self.help_text=tk.StringVar(value='選取設定後，這裡會說明用途。雙擊可調整；外觀與常用輸出功能附有預覽。')
        ttk.Label(self,textvariable=self.help_text,style='Muted.TLabel',wraplength=980).pack(side='bottom',fill='x',pady=(6,0))
        body = ttk.Frame(self); body.pack(fill='both', expand=True)
        self.categories = ttk.Treeview(body, show='tree', selectmode='browse', height=7)
        self.categories.column('#0', width=155, stretch=False)
        for name in ['常用設定'] + CATEGORIES[:-1]:
            self.categories.insert('', 'end', iid=name, text=name)
        self.categories.selection_set('常用設定'); self.categories.pack(side='left', fill='y', padx=(0, 14))
        frame, self.tree = scroll_table(body, [('name', '設定項目', 225), ('value', '目前值', 200), ('scope', '範圍', 135), ('note','用途說明',350), ('path', '原始名稱（查閱用）', 320)])
        frame.pack(side='left', fill='both', expand=True)
        self.tree.bind('<Double-1>', lambda e: self.edit())
        self.tree.bind('<<TreeviewSelect>>',lambda e:self.describe())
        self.categories.bind('<<TreeviewSelect>>', lambda e: self.render())
        self.search.trace_add('write', lambda *_: self.render()); self.scope.trace_add('write', lambda *_: self.render())

    def fill(self):
        self.catalogue = Catalogue(self.app.store)
        self.render()

    def render(self):
        if not hasattr(self, 'catalogue'):
            return
        self.tree.delete(*self.tree.get_children())
        query = self.search.get().strip().casefold()
        cat = next(iter(self.categories.selection()), '全部')
        self.visible = {}
        for index, item in enumerate(self.catalogue.items):
            if cat == '常用設定' and not query and item.path not in LABELS:
                continue
            if cat not in ('全部', '常用設定') and category(item.path) != cat:
                continue
            if self.scope.get() not in ('全部範圍', SCOPES[item.scope]):
                continue
            value = self.catalogue.pending.get((item.scope, item.path), item.value)
            if query and query not in f'{item.label} {item.description} {item.path} {value} {SCOPES[item.scope]}'.casefold():
                continue
            text = shown_value(value)
            if item.scope=='weasel' and item.path in ('style/color_scheme','style/color_scheme_dark'):
                theme=self.catalogue.effective.get('weasel',{}).get('preset_color_schemes',{}).get(value,{})
                text=str(theme.get('name',value))+'（'+str(value)+'）'
            pending = (item.scope, item.path) in self.catalogue.pending
            self.tree.insert('', 'end', iid=str(index), values=(('● ' if pending else '') + item.label, text[:160], SCOPES[item.scope], item.description,item.path))
            self.visible[str(index)] = item
        self.count.configure(text=f'顯示 {len(self.visible)}／{len(self.catalogue.items)} 項；待儲存 {len(self.catalogue.pending)} 項')

    def describe(self):
        selected=self.tree.selection()
        if selected and selected[0] in self.visible:
            item=self.visible[selected[0]]
            self.help_text.set(item.label+'：'+item.description+'　原始名稱：'+item.path)

    def edit(self):
        selected = self.tree.selection()
        if not selected:
            return
        item = self.visible[selected[0]]
        # These controls already have a live preview on the first page.
        redirects = {('weasel', 'style/font_point'): 'font_size', ('weasel', 'style/label_font_point'): 'label_size',
                     ('weasel', 'style/comment_font_point'): 'comment_size', ('weasel', 'style/font_face'): 'font_face',
                     ('weasel', 'style/horizontal'): 'layout', ('default', 'menu/page_size'): 'page_size',
                     ('default', 'ascii_composer/switch_key/Shift_L'): 'shift_left', ('default', 'ascii_composer/switch_key/Shift_R'): 'shift_right'}
        if item.scope=='weasel' and item.path=='style':
            self.app.tabs.select(self.app.look)
            self.app.status.set('這裡提供外觀總覽與即時預覽；更多細節可從全部設定的各個子項調整。')
            return
        if (item.scope, item.path) in redirects:
            self.app.tabs.select(self.app.look)
            self.app.status.set('這個項目可在左側直接調整，右側會同步預覽。')
            return
        if item.scope == 'double_pinyin_flypy' and item.path in ('menu/page_size', 'ascii_composer'):
            # A schema-specific override would shadow the global preview controls.
            messagebox.showinfo('全域設定', '候選數與中英按鍵請在「外觀與按鍵」或「全域與按鍵」範圍調整。', parent=self)
            return
        value = self.catalogue.pending.get((item.scope, item.path), item.value)
        dialog = ValueDialog(self.app, item, value, self.catalogue)
        self.app.wait_window(dialog)
        if dialog.result is not None:
            self.render(); self.app.fill_visual(); self.app.draw_preview(); self.app.mark_dirty()

    def reset(self):
        selected = self.tree.selection()
        if selected:
            item = self.visible[selected[0]]
            self.catalogue.pending.pop((item.scope, item.path), None)
            if item.value is None:
                self.catalogue.items.remove(item)
            self.render(); self.app.fill_visual(); self.app.draw_preview(); self.app.mark_dirty()

    def add(self):
        dialog = tk.Toplevel(self.app); dialog.title('新增進階設定'); dialog.transient(self.app); dialog.grab_set()
        frame = ttk.Frame(dialog, padding=22); frame.pack(fill='both', expand=True)
        scope, path = tk.StringVar(value=SCOPES['double_pinyin_flypy']), tk.StringVar()
        ttk.Label(frame, text='新增目前版本未列出的設定；請依官方文件填寫。', style='Muted.TLabel').pack(anchor='w')
        ttk.Combobox(frame, textvariable=scope, values=list(SCOPES.values()), state='readonly', width=45).pack(pady=10)
        ttk.Label(frame, text='設定路徑，例如 style/layout/margin_x').pack(anchor='w')
        ttk.Entry(frame, textvariable=path, width=60).pack(fill='x', pady=8)
        ttk.Label(frame, text='設定值（YAML 格式）').pack(anchor='w')
        editor = tk.Text(frame, height=8, width=62, font=('Consolas', 11)); editor.pack(pady=8)
        def submit():
            try:
                self.catalogue.add(next(k for k, v in SCOPES.items() if v == scope.get()), path.get().strip(), editor.get('1.0', 'end-1c'))
            except Exception as error:
                messagebox.showerror('無法新增', str(error), parent=dialog); return
            dialog.destroy(); self.render(); self.app.mark_dirty()
        ttk.Button(frame, text='加入待儲存調整', command=submit).pack(anchor='e')
        position_dialog(dialog, self.app)

class RuleDialog(tk.Toplevel):
    def __init__(self, owner, row, rules):
        super().__init__(owner)
        self.title('調整詞彙'); self.transient(owner); self.grab_set(); self.result = None
        original = rules.rows.get(row['text'], Rule(row['text']))
        self.rules = rules; self.original = original
        frame = ttk.Frame(self, padding=24); frame.pack(fill='both', expand=True)
        ttk.Label(frame, text=display(rules.store, row['text']), style='Section.TLabel').pack(anchor='w')
        ttk.Label(frame, text=f"來源：{row['source']}\n輸入碼：{row['code'] or '由字表自動注音'}\n權重／學習次數：{row['weight'] or '依原詞庫'}", style='Muted.TLabel', wraplength=600).pack(anchor='w', pady=12)
        ttk.Label(frame, text='替代顯示文字（空白表示保留原文）').pack(anchor='w')
        self.text = tk.StringVar(value=rules.output(original))
        ttk.Entry(frame, textvariable=self.text, width=50).pack(fill='x', pady=(6, 14))
        ttk.Label(frame, text='候選處理').pack(anchor='w')
        self.mode = tk.StringVar(value={'normal': '維持排序', 'pin': '固定首位', 'hide': '隱藏此詞'}[original.mode])
        ttk.Combobox(frame, textvariable=self.mode, values=['維持排序', '固定首位', '隱藏此詞'], state='readonly', width=30).pack(anchor='w', pady=(6, 14))
        ttk.Label(frame, text='規則套用於小鶴方案中相同文字的所有讀音與來源。\n固定首位會將前 256 項內符合完整輸入的詞放到最前面；多個固定詞依原詞頻排序。\n手填的繁體文字會原樣保留，不再自動改回異體字。\n原始詞庫與學習次數會保留；繁簡切換仍然有效。\n要改拼音、捷徑或個人權重，請用「複製為個人詞」。', style='Muted.TLabel', wraplength=600).pack(anchor='w')
        buttons = ttk.Frame(frame); buttons.pack(fill='x', pady=(20, 0))
        ttk.Button(buttons, text='取消', command=self.destroy).pack(side='right')
        ttk.Button(buttons, text='完成調整', command=self.submit).pack(side='right', padx=8)
        position_dialog(self, owner)
    def submit(self):
        text = self.text.get().strip()
        value = Rule(self.original.original, text, {'維持排序': 'normal', '固定首位': 'pin', '隱藏此詞': 'hide'}[self.mode.get()])
        try:
            self.rules.put(value)
        except SettingsError as error:
            messagebox.showerror('無法調整', str(error), parent=self); return
        self.result = value; self.destroy()

class VocabularyPage(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, padding=18)
        self.app, self.page, self.generation = app, 0, 0
        self.index = Index(app.store.root)
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix='Vocabulary')
        self.messages = queue.Queue()
        self.search = tk.StringVar()
        self.kind = tk.StringVar(value='全部'); self.enabled = tk.StringVar(value='全部')
        self.source = tk.StringVar(value='全部來源'); self.only_rules = tk.BooleanVar(value=False)
        ttk.Label(self, text='我的詞彙表', style='Section.TLabel').pack(anchor='w')
        ttk.Label(self, text='中文、英文、混輸、個人詞與學習記憶統一管理。來源不同的同一詞會分列，方便比較讀音與權重。', style='Muted.TLabel', wraplength=950).pack(anchor='w', pady=(6, 10))
        filters = ttk.Frame(self); filters.pack(fill='x')
        ttk.Label(filters, text='搜尋').pack(side='left')
        ttk.Entry(filters, textvariable=self.search, width=25).pack(side='left', fill='x', expand=True, padx=8)
        ttk.Combobox(filters, textvariable=self.kind, values=['全部', '中文', '英文', '中英混輸', '個人詞彙', '自動學習', '拆字反查'], width=11, state='readonly').pack(side='left', padx=5)
        ttk.Combobox(filters, textvariable=self.enabled, values=['全部', '已啟用', '未啟用'], width=9, state='readonly').pack(side='left')
        row = ttk.Frame(self); row.pack(fill='x', pady=8)
        self.source_box = ttk.Combobox(row, textvariable=self.source, values=['全部來源'], state='readonly', width=44); self.source_box.pack(side='left')
        ttk.Checkbutton(row, text='只看我的調整規則', variable=self.only_rules, command=self.request).pack(side='left', padx=12)
        ttk.Button(row, text='更新詞庫與學習記憶', command=self.refresh).pack(side='right')
        bottom = ttk.Frame(self); bottom.pack(side='bottom', fill='x', pady=(10, 0))
        row = ttk.Frame(bottom); row.pack(fill='x')
        for label, command in [('＋ 中文詞', lambda: self.add(True)), ('＋ 英文／捷徑', lambda: self.add(False)), ('編輯選取', self.edit), ('複製為個人詞', self.copy_word), ('移除／隱藏', self.remove), ('取消詞彙規則', self.clear_rule)]:
            ttk.Button(row, text=label, command=command).pack(side='left', padx=(0, 5))
        row = ttk.Frame(bottom); row.pack(fill='x', pady=(9, 0))
        self.count = ttk.Label(row, text='正在建立詞彙索引…', style='Muted.TLabel'); self.count.pack(side='left')
        ttk.Button(row, text='匯出全部 CSV', command=self.export).pack(side='right')
        ttk.Button(row, text='下一頁 ›', command=lambda: self.move(1)).pack(side='right', padx=6)
        ttk.Button(row, text='‹ 上一頁', command=lambda: self.move(-1)).pack(side='right')
        self.timestamp = ttk.Label(bottom, text='', style='Muted.TLabel'); self.timestamp.pack(anchor='w', pady=(5, 0))
        frame, self.tree = scroll_table(self, [('text', '詞彙（台灣繁體）', 250), ('code', '完整拼音／輸入碼', 230), ('weight', '權重／學習次數', 125), ('kind', '類型', 95), ('source', '來源', 260), ('active', '狀態／調整', 150)])
        frame.pack(fill='both', expand=True)
        self.tree.bind('<Double-1>', lambda e: self.edit())
        for var in [self.search, self.kind, self.enabled, self.source]:
            var.trace_add('write', self.schedule)
        self.timer = None; self.rows = {}; self.total_matches = 0
        self.after(120, self.poll)

    def fill(self):
        self.rules = Rules(self.app.store)
        self.cached_sources = None
        self.page = 0
        self.request(rebuild=True)

    def schedule(self, *_):
        self.page = 0
        if self.timer:
            self.after_cancel(self.timer)
        self.generation += 1
        self.timer = self.after(300, self.request)

    def personals(self):
        rows = []
        for table, name, chinese in [(self.app.word_page, 'flypy_personal.dict.yaml', True), (self.app.shortcut_page, 'flypy_phrases.txt', False)]:
            for entry in table.rows:
                rows.append(dict(id=name + '::' + entry.uid, entry_uid=entry.uid, text=entry.text, code=entry.code, weight=str(entry.weight), kind='個人詞彙', source=name, active=1, chinese=chinese))
        return rows

    def request(self, rebuild=False):
        self.timer = None
        if not hasattr(self, 'rules'):
            return
        self.generation += 1
        generation = self.generation
        params = (self.search.get(), self.kind.get(), self.enabled.get(), self.source.get(), self.page)
        local = self.personals(); only_rules = self.only_rules.get(); rules = copy.deepcopy(self.rules.rows)
        self.count.configure(text='正在搜尋…')
        def work():
            if generation != self.generation:
                return
            try:
                if rebuild or not self.index.path.is_file():
                    self.index.rebuild()
                if self.cached_sources is None:
                    self.cached_sources = self.index.source_counts()
                text, kind, enabled, source, page = params
                query = text.casefold().strip()
                variants = [query, self.index.to_source.convert(query), self.index.to_s.convert(query)]
                aliases=[key for key,rule in rules.items() if query and any(q in (rule.traditional or rule.replacement).casefold() for q in variants)]
                variants += aliases
                personal = [r for r in local if (kind in ('全部', '個人詞彙')) and enabled != '未啟用' and source in ('全部來源', r['source']) and (not query or any(q in (r['text']+' '+r['code']).casefold() for q in variants))]
                if only_rules:
                    all_rows = []
                    for key in rules:
                        original = self.index.exact(key)
                        if not original:
                            original = [dict(id='rule-'+key, text=key, code='', weight='', kind='個人規則', source='flypy_vocabulary_rules.tsv', active=1)]
                        all_rows.extend(original)
                    all_rows = [r for r in all_rows if kind in ('全部', r['kind']) and source in ('全部來源', r['source']) and (enabled == '全部' or bool(r['active']) == (enabled == '已啟用')) and (not query or any(q in (r['text']+' '+r['code']).casefold() for q in variants))]
                    rows, count = all_rows[page*100:page*100+100], len(all_rows)
                    _, _, total = self.index.query(size=0)
                else:
                    start = page * 100
                    # Keep staged personal edits visible without writing them to disk.
                    shown = personal[start:start+100]
                    db_start = max(0, start - len(personal))
                    fetched, count, total = self.index.query(text, kind, enabled, source, page=0, size=0, exclude_personal=True, extra_terms=aliases)
                    if len(shown) < 100:
                        fetched = self._slice_query(text, kind, enabled, source, db_start, 100-len(shown), aliases)
                    rows, count = shown + fetched, count + len(personal)
                counts = self.cached_sources
                self.messages.put((generation, True, (rows, count, total, counts)))
            except Exception as error:
                self.messages.put((generation, False, str(error)))
        self.pool.submit(work)

    def _slice_query(self, text, kind, enabled, source, offset, size, aliases=()):
        rows, _, _ = self.index.query(text, kind, enabled, source, size=size, exclude_personal=True, offset=offset, include_count=False, extra_terms=aliases)
        return rows

    def poll(self):
        try:
            while True:
                generation, ok, result = self.messages.get_nowait()
                if generation != self.generation:
                    continue
                if not ok:
                    self.count.configure(text='讀取失敗：' + result[:150]); continue
                rows, count, total, counts = result
                self.rows = {str(r['id']): r for r in rows}; self.total_matches = count
                self.tree.delete(*self.tree.get_children())
                for iid, r in self.rows.items():
                    rule = self.rules.rows.get(r['text'])
                    state = '已啟用' if r['active'] else '未啟用'
                    if rule:
                        state += '／' + {'normal': '改文字', 'hide': '隱藏', 'pin': '固定首位'}[rule.mode]
                    word = self.rules.display(r['text'])
                    self.tree.insert('', 'end', iid=iid, values=(word, r['code'] or '自動注音', r['weight'], r['kind'], r['source'], state))
                pages = max(1, (count+99)//100)
                self.count.configure(text=f'第 {self.page+1}／{pages} 頁 · 符合 {count:,} 筆 · 詞庫共 {total:,} 筆')
                if counts is not None:
                    self.source_box.configure(values=['全部來源'] + [r[0] for r in counts])
                folder = self.app.store.root / 'maintenance' / 'learned-export'
                info = folder / 'export-info.json'
                self.timestamp.configure(text='學習記憶快照：' + (datetime.fromtimestamp(info.stat().st_mtime).strftime('%Y-%m-%d %H:%M:%S') if info.exists() else '沿用 Rime 同步快照') + '；按「更新詞庫與學習記憶」可讀入後來記住的詞。')
        except queue.Empty:
            pass
        self.after(120, self.poll)

    def selected(self):
        selected = self.tree.selection()
        return self.rows.get(selected[0]) if selected else None

    def move(self, delta):
        next_page = self.page + delta
        if 0 <= next_page < max(1, (self.total_matches + 99)//100):
            self.page = next_page; self.request()

    def add(self, chinese):
        table = self.app.word_page if chinese else self.app.shortcut_page
        table.add(); self.request()

    def personal_edit(self, row):
        chinese = row['source'] == 'flypy_personal.dict.yaml'
        table = self.app.word_page if chinese else self.app.shortcut_page
        entry = next((e for e in table.rows if e.uid == row.get('entry_uid')), None)
        if entry:
            table.open_editor(entry); self.request()

    def edit(self):
        row = self.selected()
        if not row:
            return
        if row['source'] in ('flypy_personal.dict.yaml', 'flypy_phrases.txt') and isinstance(row['id'], str) and not row['id'].startswith('rule-'):
            self.personal_edit(row); return
        dialog = RuleDialog(self.app, row, self.rules)
        self.app.wait_window(dialog)
        if dialog.result:
            self.request(); self.app.mark_dirty()

    def copy_word(self):
        row = self.selected()
        if not row:
            return
        chinese = bool(row['code'] and ' ' in row['code'] and row['kind'] != '拆字反查') or row['kind'] == '中文'
        from flypy_settings import EntryDialog
        from settings_core import Entry
        table = self.app.word_page if chinese else self.app.shortcut_page
        # Opening with a draft pre-fills fields; a new ID keeps the original untouched.
        import uuid
        draft = Entry(uuid.uuid4().hex, row['text'], row['code'], 10000 if chinese else 1)
        dialog = EntryDialog(self.app, chinese, self.app.store, draft, table.rows)
        self.app.wait_window(dialog)
        if dialog.result:
            table.rows.append(dialog.result); table.render(); self.app.mark_dirty(); self.request()

    def remove(self):
        row = self.selected()
        if not row:
            return
        if row['source'] in ('flypy_personal.dict.yaml', 'flypy_phrases.txt') and isinstance(row['id'], str):
            table = self.app.word_page if row['source'] == 'flypy_personal.dict.yaml' else self.app.shortcut_page
            if messagebox.askyesno('移除個人詞', '移除這個個人詞，並隱藏其他來源的同字詞？\n可用「取消詞彙規則」恢復其他來源；儲存前可重新讀取取消。', parent=self):
                table.rows = [e for e in table.rows if e.uid != row.get('entry_uid')]
                self.rules.put(Rule(row['text'], '', 'hide'))
                table.render(); self.app.mark_dirty(); self.request()
        elif messagebox.askyesno('隱藏詞彙', '隱藏小鶴候選中所有來源、所有讀音的這個詞？\n原詞庫與學習次數會保留，可以隨時取消規則。', parent=self):
            previous = self.rules.rows.get(row['text'], Rule(row['text']))
            self.rules.put(replace(previous, mode='hide')); self.app.mark_dirty(); self.request()

    def clear_rule(self):
        row = self.selected()
        if row and row['text'] in self.rules.rows:
            self.rules.rows.pop(row['text']); self.app.mark_dirty(); self.request()

    def refresh(self):
        if self.app.dirty():
            messagebox.showinfo('請先儲存', '請先儲存目前調整，再更新詞庫與學習記憶。', parent=self); return
        if messagebox.askyesno('更新學習記憶', '將使用小狼毫官方功能匯出最新學習詞彙，並重建搜尋索引。\n過程會短暫暫停輸入法，完成後會自動重新啟動。\n請先完成正在輸入的文字。', parent=self):
            self.app.run_task('正在更新詞庫與學習記憶…', lambda: (refresh_learned(self.app.store), self.index.rebuild(True)) and None, '已更新內建詞庫索引與學習記憶。')

    def export(self):
        if self.app.dirty():
            messagebox.showinfo('請先儲存', '請先儲存目前調整，再匯出磁碟上的完整詞彙表。', parent=self)
            return
        target = filedialog.asksaveasfilename(parent=self, title='匯出所有詞彙', defaultextension='.csv', filetypes=[('CSV 詞彙表', '*.csv')], initialfile='小鶴完整詞彙表.csv')
        if target:
            self.app.run_task('正在匯出完整詞彙表…', lambda: self.index.export_csv(target, self.app.store), '已匯出全部詞彙；修改 CSV 不會直接更動輸入法。')

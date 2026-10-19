"""Native Windows editor. No network service, startup task or administrator access."""
from __future__ import annotations

import argparse
import copy
import ctypes
import hashlib
import os
from pathlib import Path
import queue
import sys
import threading
import tkinter as tk
from tkinter import messagebox, ttk
import tkinter.font as tkfont

from settings_core import Appearance, Entry, SettingsError, SHIFT_MODES, Store, VERSION, discover_paths
from settings_pages import AdvancedPage, VocabularyPage, position_dialog
from live_preview import LivePreview, documents
from setting_help import info
from shortcut_help import ShortcutHelpPage
from scroll_support import bind_settings_wheel

TITLE = '小鶴設定工具'
FONT_CHOICES = {
    '微軟正黑體 UI（建議）': 'Microsoft JhengHei UI, Segoe UI, Segoe UI Emoji',
    '微軟正黑體': 'Microsoft JhengHei, Segoe UI, Segoe UI Emoji',
    'Segoe UI（中文使用系統替代字體）': 'Segoe UI, Microsoft JhengHei UI, Segoe UI Emoji',
}
FIELD_NAMES = {'font_size': '候選字級', 'label_size': '數字字級', 'comment_size': '註解字級',
               'font_face': '候選字體', 'horizontal': '候選排列', 'page_size': '每頁候選數',
               'shift_left': '左 Shift', 'shift_right': '右 Shift'}


def configure_dpi():
    if os.name == 'nt':
        try:
            ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
        except (AttributeError, OSError):
            pass


class EntryDialog(tk.Toplevel):
    def __init__(self, owner, chinese, store, original, existing):
        super().__init__(owner)
        self.title(('編輯' if original else '新增') + ('中文詞彙' if chinese else '英文捷徑'))
        self.transient(owner)
        self.resizable(False, False)
        self.result = None
        self.chinese, self.store, self.original, self.existing = chinese, store, original, existing
        frame = ttk.Frame(self, padding=24)
        frame.pack(fill='both', expand=True)
        display = store.to_tw.convert(original.text) if original and chinese else original.text if original else ''
        self.text = tk.StringVar(value=display)
        self.code = tk.StringVar(value=original.code if original else '')
        self.weight = tk.StringVar(value=str(original.weight if original else 10000 if chinese else 1))
        ttk.Label(frame, text='詞彙（可直接填繁體）' if chinese else '要輸出的完整文字').grid(row=0, column=0, sticky='w')
        self.word_box = ttk.Entry(frame, textvariable=self.text, width=44)
        self.word_box.grid(row=1, column=0, columnspan=2, sticky='ew', pady=(6, 18))
        ttk.Label(frame, text='完整拼音（無聲調，音節用空格分開）' if chinese else '輸入捷徑（小寫字母，不含數字）').grid(row=2, column=0, sticky='w')
        ttk.Entry(frame, textvariable=self.code, width=44).grid(row=3, column=0, columnspan=2, sticky='ew', pady=(6, 8))
        ttk.Label(frame, text='例：遙測影像 → yao ce ying xiang' if chinese else '例：Google Scholar → googlescholar', style='Muted.TLabel').grid(row=4, column=0, columnspan=2, sticky='w', pady=(0, 18))
        ttk.Label(frame, text='初始權重（通常 10000）' if chinese else '候選順序（通常 1）').grid(row=5, column=0, sticky='w')
        ttk.Spinbox(frame, from_=1, to=100000000 if chinese else 99, textvariable=self.weight, width=12).grid(row=6, column=0, sticky='w', pady=(6, 18))
        buttons = ttk.Frame(frame)
        buttons.grid(row=7, column=0, columnspan=2, sticky='e')
        ttk.Button(buttons, text='取消', command=self.destroy).pack(side='left', padx=6)
        ttk.Button(buttons, text='加入' if not original else '完成編輯', command=self.submit).pack(side='left')
        self.bind('<Return>', lambda event: self.submit())
        self.bind('<Escape>', lambda event: self.destroy())
        position_dialog(self, owner)
        self.grab_set()
        self.after(80, self.word_box.focus_set)

    def submit(self):
        try:
            if self.chinese:
                value = self.store.normalize_word(self.text.get(), self.code.get(), self.weight.get(), self.original)
            else:
                value = self.store.make_entry(self.text.get(), self.code.get(), self.weight.get(), False, self.original)
            if any(e.uid != value.uid and e.text == value.text and e.code == value.code for e in self.existing):
                raise SettingsError('這個詞彙與輸入碼已經存在，請直接編輯原有詞條。')
        except (SettingsError, ValueError) as error:
            messagebox.showerror('請檢查詞條', str(error), parent=self)
            return
        self.result = value
        self.destroy()


class TablePage(ttk.Frame):
    def __init__(self, parent, app, chinese):
        super().__init__(parent, padding=18)
        self.app, self.chinese = app, chinese
        self.rows = []
        title = '你的中文專有名詞' if chinese else '長名稱，用短碼輸入'
        ttk.Label(self, text=title, style='Section.TLabel').pack(anchor='w')
        note = ('直接填繁體詞彙與完整拼音。工具會處理底層格式；中文詞條保留詞頻學習。'
                if chinese else '例如 gee → Google Earth Engine。這裡的固定短語會優先顯示，建議使用不易撞碼的縮寫。')
        ttk.Label(self, text=note, style='Muted.TLabel', wraplength=930).pack(anchor='w', pady=(6, 14))
        bar = ttk.Frame(self)
        bar.pack(fill='x', pady=(0, 10))
        ttk.Label(bar, text='搜尋').pack(side='left', padx=(0, 8))
        self.search = tk.StringVar()
        ttk.Entry(bar, textvariable=self.search, width=32).pack(side='left')
        self.count = ttk.Label(bar, style='Muted.TLabel')
        self.count.pack(side='right')
        self.search.trace_add('write', lambda *_: self.render())
        grid = ttk.Frame(self)
        grid.pack(fill='both', expand=True)
        self.tree = ttk.Treeview(grid, columns=('text', 'code', 'weight'), show='headings', selectmode='extended', height=7)
        for column, title, width in [('text', '詞彙（台灣繁體）' if chinese else '輸出文字', 300),
                                      ('code', '完整拼音' if chinese else '捷徑碼', 380),
                                      ('weight', '初始權重' if chinese else '順序', 100)]:
            self.tree.heading(column, text=title)
            self.tree.column(column, width=width, minwidth=80, anchor='w' if column != 'weight' else 'center')
        scroll = ttk.Scrollbar(grid, orient='vertical', command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side='left', fill='both', expand=True)
        scroll.pack(side='right', fill='y')
        self.tree.bind('<Double-1>', lambda event: self.edit())
        controls = ttk.Frame(self)
        # Reserve the action row before the expanding table at smaller sizes.
        grid.pack_forget()
        controls.pack(side='bottom', fill='x', pady=(14, 0))
        grid.pack(fill='both', expand=True)
        ttk.Button(controls, text='＋ 新增詞彙' if chinese else '＋ 新增捷徑', command=self.add).pack(side='left')
        ttk.Button(controls, text='編輯選取', command=self.edit).pack(side='left', padx=8)
        ttk.Button(controls, text='移除選取', command=self.remove).pack(side='left')
        ttk.Label(controls, text='表格變更在按下儲存後才會寫入。', style='Muted.TLabel').pack(side='right')

    def set_rows(self, rows):
        self.rows = copy.deepcopy(rows)
        self.search.set('')
        self.render()

    def render(self):
        selected = set(self.tree.selection())
        self.tree.delete(*self.tree.get_children())
        query = self.search.get().strip().casefold()
        for entry in self.rows:
            display = self.app.store.to_tw.convert(entry.text) if self.chinese else entry.text
            if query and query not in (display + ' ' + entry.text + ' ' + entry.code).casefold():
                continue
            self.tree.insert('', 'end', iid=entry.uid, values=(display, entry.code, entry.weight))
            if entry.uid in selected:
                self.tree.selection_add(entry.uid)
        self.count.configure(text=f'顯示 {len(self.tree.get_children())} ／共 {len(self.rows)} 筆')

    def add(self):
        self.open_editor(None)

    def edit(self):
        ids = self.tree.selection()
        if len(ids) != 1:
            messagebox.showinfo('編輯詞彙', '請先選取一筆詞條。', parent=self)
            return
        self.open_editor(next(e for e in self.rows if e.uid == ids[0]))

    def open_editor(self, entry):
        dialog = EntryDialog(self.app, self.chinese, self.app.store, entry, self.rows)
        self.app.wait_window(dialog)
        if dialog.result:
            if entry:
                self.rows[self.rows.index(entry)] = dialog.result
            else:
                self.rows.append(dialog.result)
            self.render()
            self.app.mark_dirty()

    def remove(self):
        ids = set(self.tree.selection())
        if not ids:
            return
        if messagebox.askyesno('移除詞條', f'將 {len(ids)} 筆詞條移出清單？\n按儲存前仍可用「重新讀取」取消，儲存時也會先備份。', parent=self):
            self.rows = [e for e in self.rows if e.uid not in ids]
            self.render()
            self.app.mark_dirty()


class App(tk.Tk):
    def __init__(self, store):
        super().__init__()
        self.store = store
        self.title(TITLE)
        self.geometry(f'{min(1120, self.winfo_screenwidth()-100)}x{min(820, self.winfo_screenheight()-110)}')
        self.minsize(930, 650)
        try:
            self.iconbitmap(str(Path(getattr(sys, '_MEIPASS', Path(__file__).parent)) / 'app.ico'))
        except tk.TclError:
            pass
        self.configure(background='#f6f7f9')
        self.option_add('*Font', ('Microsoft JhengHei UI', 11))
        style = ttk.Style(self)
        if 'vista' in style.theme_names():
            style.theme_use('vista')
        style.configure('.', font=('Microsoft JhengHei UI', 11))
        style.configure('Title.TLabel', font=('Microsoft JhengHei UI', 23, 'bold'))
        style.configure('Section.TLabel', font=('Microsoft JhengHei UI', 14, 'bold'))
        style.configure('Muted.TLabel', foreground='#647084', font=('Microsoft JhengHei UI', 10))
        style.configure('Treeview', rowheight=34, font=('Microsoft JhengHei UI', 11))
        style.configure('Treeview.Heading', font=('Microsoft JhengHei UI', 10, 'bold'))
        style.configure('TNotebook.Tab', padding=(17, 10))
        style.configure('TButton', padding=(10, 6))
        self.status = tk.StringVar(value='已讀取目前設定；尚未作任何修改。')
        self.events = queue.Queue()
        self.busy = None
        self.ready = False
        header = ttk.Frame(self, padding=(24, 18, 24, 10))
        header.pack(fill='x')
        ttk.Label(header, text=TITLE, style='Title.TLabel').pack(side='left')
        ttk.Label(header, text='雾凇 × 小鶴雙拼 · 台灣繁體', style='Muted.TLabel').pack(side='right', anchor='s', pady=8)
        directory = ttk.Frame(self, padding=(24, 0, 24, 14))
        directory.pack(fill='x')
        ttk.Button(directory, text='開啟資料夾', command=lambda: os.startfile(self.store.root)).pack(side='right')
        ttk.Label(directory, text=f'目前資料夾：{self.store.root}', style='Muted.TLabel', wraplength=740).pack(side='left', fill='x', expand=True, padx=(0, 12))
        # Footer is packed before expandable content, so controls remain visible at high DPI.
        footer = ttk.Frame(self, padding=(20, 12))
        footer.pack(side='bottom', fill='x')
        ttk.Label(footer, textvariable=self.status, style='Muted.TLabel', wraplength=560).pack(anchor='w', pady=(0, 10))
        ttk.Button(footer, text='重新讀取', command=self.reload).pack(side='left')
        ttk.Button(footer, text='儲存並重新部署', command=lambda: self.save(True)).pack(side='right')
        ttk.Button(footer, text='僅儲存', command=lambda: self.save(False)).pack(side='right', padx=8)
        self.tabs = ttk.Notebook(self)
        self.tabs.pack(fill='both', expand=True, padx=20)
        self.look = ttk.Frame(self.tabs, padding=18)
        self.tabs.add(self.look, text='外觀與按鍵')
        self.make_appearance()
        self.word_page = TablePage(self.tabs, self, True)
        self.shortcut_page = TablePage(self.tabs, self, False)
        # Personal row editors are reused behind the unified vocabulary view.
        self.advanced_page = AdvancedPage(self.tabs, self)
        self.tabs.add(self.advanced_page, text='全部設定')
        self.vocabulary_page = VocabularyPage(self.tabs, self)
        self.tabs.add(self.vocabulary_page, text='我的詞彙表')
        self.backups_page = ttk.Frame(self.tabs, padding=22)
        self.tabs.add(self.backups_page, text='備份與還原')
        self.make_backups()
        self.help_page = ShortcutHelpPage(self.tabs, self)
        self.tabs.add(self.help_page, text="快捷鍵對照表")
        self.fill()
        self.protocol('WM_DELETE_WINDOW', self.close)
        self.bind('<Control-s>', lambda event: self.save(False))
        self.after(100, self.poll)

    def make_appearance(self):
        self.look.columnconfigure(0, weight=0)
        self.look.columnconfigure(1, weight=1)
        self.look.rowconfigure(0, weight=1)
        left = ttk.Frame(self.look, padding=(0, 0, 16, 0))
        left.grid(row=0, column=0, sticky='nsew')
        left.rowconfigure(0, weight=1)
        left.columnconfigure(0, weight=1)
        control_canvas = tk.Canvas(left, highlightthickness=0, width=375, height=390, background=self.cget('background'))
        control_canvas.grid(row=0, column=0, sticky='nsew')
        control_scroll = ttk.Scrollbar(left, orient='vertical', command=control_canvas.yview)
        control_scroll.grid(row=0, column=1, sticky='ns')
        control_canvas.configure(yscrollcommand=control_scroll.set)
        controls = ttk.Frame(control_canvas, padding=(0, 0, 12, 8))
        control_window = control_canvas.create_window(0, 0, window=controls, anchor='nw')
        controls.bind('<Configure>', lambda event: control_canvas.configure(scrollregion=control_canvas.bbox('all')))
        control_canvas.bind('<Configure>', lambda event: control_canvas.itemconfigure(control_window, width=event.width))
        self.variables = {key: tk.StringVar() for key in ['font_size', 'label_size', 'comment_size', 'page_size', 'font_face', 'layout', 'shift_left', 'shift_right']}
        ttk.Label(controls, text='候選視窗', style='Section.TLabel').grid(row=0, column=0, columnspan=2, sticky='w', pady=(0, 14))
        for row, (key, label, low, high) in enumerate([
            ('font_size', '候選字級', 10, 40), ('label_size', '數字字級', 8, 30),
            ('comment_size', '註解字級', 8, 30), ('page_size', '每頁候選數', 5, 9)], 1):
            ttk.Label(controls, text=label).grid(row=row, column=0, sticky='w', pady=6)
            ttk.Spinbox(controls, from_=low, to=high, width=10, textvariable=self.variables[key]).grid(row=row, column=1, sticky='w', padx=(12, 0))
        ttk.Label(controls, text='排列方式').grid(row=5, column=0, sticky='w', pady=8)
        ttk.Combobox(controls, textvariable=self.variables['layout'], values=['直排', '橫排'], state='readonly', width=12).grid(row=5, column=1, sticky='w', padx=(12, 0))
        ttk.Label(controls, text='候選字體').grid(row=6, column=0, columnspan=2, sticky='w', pady=(8, 5))
        self.font_box = ttk.Combobox(controls, textvariable=self.variables['font_face'], values=list(FONT_CHOICES), width=33, state='readonly')
        self.font_box.grid(row=7, column=0, columnspan=2, sticky='ew')
        ttk.Separator(controls).grid(row=8, column=0, columnspan=2, sticky='ew', pady=20)
        ttk.Label(controls, text='單按 Shift 的行為', style='Section.TLabel').grid(row=9, column=0, columnspan=2, sticky='w', pady=(0, 10))
        for row, key, label in [(10, 'shift_left', '左 Shift'), (11, 'shift_right', '右 Shift')]:
            ttk.Label(controls, text=label).grid(row=row, column=0, sticky='w', pady=7)
            box = ttk.Combobox(controls, textvariable=self.variables[key], values=list(SHIFT_MODES), state='readonly', width=20)
            box.grid(row=row, column=1, sticky='w', padx=(12, 0))
        ttk.Label(controls, text='設定控制單按 Shift 的行為；\n按住 Shift 搭配字母仍可輸入大寫。', style='Muted.TLabel', wraplength=330).grid(row=12, column=0, columnspan=2, sticky='w', pady=(10, 0))
        ttk.Separator(controls).grid(row=13,column=0,columnspan=2,sticky='ew',pady=18)
        wrap_bar=ttk.Frame(controls)
        wrap_bar.grid(row=14,column=0,columnspan=2,sticky='ew',pady=(0,8))
        ttk.Label(wrap_bar,text='候選換行與外觀',style='Section.TLabel').pack(anchor='w')
        ttk.Button(wrap_bar,text='試用多行候選',command=self.multiline_candidates).pack(anchor='w',pady=6)
        ttk.Label(wrap_bar,text='橫排＋最大寬度 420 可自動換行。寬度 0 為單行；可調整下方寬度並看右側預覽。\n每頁仍顯示 5～9 詞，翻頁後也維持多行；不是逐行展開的捲軸模式。',style='Muted.TLabel',wraplength=330).pack(anchor='w')
        self.visual_variables={}
        keys=['style/layout/max_width','style/color_scheme','style/color_scheme_dark','style/layout/margin_x','style/layout/margin_y',
              'style/layout/candidate_spacing','style/layout/spacing','style/layout/hilite_padding','style/layout/border_width',
              'style/layout/corner_radius','style/layout/round_corner','style/layout/shadow_radius','style/label_format','style/inline_preedit']
        for row,path in enumerate(keys,15):
            variable=tk.StringVar();self.visual_variables[path]=variable
            ttk.Label(controls,text=info(path)[0],wraplength=145).grid(row=row,column=0,sticky='w',pady=5)
            if path.endswith(('color_scheme','color_scheme_dark')):
                widget=ttk.Combobox(controls,textvariable=variable,state='readonly',width=20)
                if not hasattr(self,'theme_boxes'):self.theme_boxes={}
                self.theme_boxes[path]=widget
            elif path.endswith('inline_preedit'):
                widget=ttk.Combobox(controls,textvariable=variable,values=['開啟','關閉'],state='readonly',width=12)
            elif path.endswith('label_format'):
                widget=ttk.Combobox(controls,textvariable=variable,values=['%s','%s.','(%s)'],width=12)
            else:widget=ttk.Spinbox(controls,from_=0,to=4000 if path.endswith('max_width') else 150,textvariable=variable,width=10)
            widget.grid(row=row,column=1,sticky='ew',padx=(10,0))
            variable.trace_add('write',lambda *_,p=path:self.visual_changed(p))
        bind_settings_wheel(control_canvas, controls, control_scroll)
        preview = ttk.Frame(self.look)
        preview.grid(row=0, column=1, sticky='nsew')
        ttk.Label(preview, text='即時預覽', style='Section.TLabel').pack(anchor='w')
        ttk.Label(preview, text='預覽不會改變目前正在使用的輸入法。', style='Muted.TLabel').pack(anchor='w', pady=(6, 12))
        self.live_preview=LivePreview(preview)
        self.live_preview.pack(fill='both',expand=True)
        self.canvas=self.live_preview.canvas
        ttk.Label(preview,text='預覽會套用尚未儲存的調整；可切換淺／深色情境。\n更多細節可到「全部設定 → 介面與配色」雙擊調整。',style='Muted.TLabel',wraplength=440).pack(anchor='w',pady=(10,0))
        for variable in self.variables.values():
            variable.trace_add('write', self.changed)

    def make_backups(self):
        page = self.backups_page
        ttk.Label(page, text='放心調整，隨時回到先前設定', style='Section.TLabel').pack(anchor='w')
        ttk.Label(page, text='每次儲存或還原前，都會自動備份個人設定、詞彙與調整規則。\n這裡的還原不會動到上游詞庫，也不會回退你的使用者詞頻。', style='Muted.TLabel', wraplength=900).pack(anchor='w', pady=(10, 20))
        row = ttk.Frame(page)
        row.pack(fill='x')
        ttk.Button(row, text='備份目前設定', command=self.backup).pack(side='left')
        ttk.Button(row, text='開啟備份資料夾', command=self.open_backups).pack(side='left', padx=10)
        ttk.Separator(page).pack(fill='x', pady=22)
        ttk.Label(page, text='選擇要還原的時間').pack(anchor='w')
        self.backup_choice = tk.StringVar()
        self.backup_box = ttk.Combobox(page, textvariable=self.backup_choice, state='readonly', width=78)
        self.backup_box.pack(anchor='w', pady=(8, 12))
        ttk.Button(page, text='還原選取備份並重新部署', command=self.restore).pack(anchor='w')
        ttk.Separator(page).pack(fill='x', pady=22)
        ttk.Label(page, text='其他常用操作', style='Section.TLabel').pack(anchor='w', pady=(0, 8))
        ttk.Label(page, text='Shift：中英切換　｜　Ctrl＋Shift＋4：繁簡切換　｜　F4：功能選單\n完整更新與詞頻備份仍可使用先前的 Rime 維護工具。', style='Muted.TLabel', wraplength=900).pack(anchor='w')
        ttk.Label(page, text=f'工具版本 {VERSION} · 設定只保存在這台電腦', style='Muted.TLabel').pack(anchor='w', pady=(20, 0))

    def fill(self):
        self.ready = False
        a = self.store.appearance
        for key in ['font_size', 'label_size', 'comment_size', 'page_size']:
            self.variables[key].set(str(getattr(a, key)))
        self.variables['layout'].set('橫排' if a.horizontal else '直排')
        self.font_options = dict(FONT_CHOICES)
        if a.font_face not in self.font_options.values():
            self.font_options['保留目前自訂字體'] = a.font_face
        self.font_box.configure(values=list(self.font_options))
        self.variables['font_face'].set(next(k for k, value in self.font_options.items() if value == a.font_face))
        self.mode_options = dict(SHIFT_MODES)
        for mode in [a.shift_left, a.shift_right]:
            if mode not in self.mode_options.values():
                self.mode_options[f'保留現有方式（{mode}）'] = mode
        for key in ['shift_left', 'shift_right']:
            self.variables[key].set(next(k for k, value in self.mode_options.items() if value == getattr(a, key)))
        self.word_page.set_rows(self.store.words.entries)
        self.shortcut_page.set_rows(self.store.phrases.entries)
        self.advanced_page.fill()
        self.fill_visual()
        self.vocabulary_page.fill()
        self.refresh_backups()
        self.ready = True
        self.draw_preview()

    def changed(self, *_):
        if self.ready:
            self.mark_dirty()
        self.draw_preview()

    def mark_dirty(self):
        self.status.set('有尚未儲存的調整；按「儲存並重新部署」才會套用到輸入法。')

    def collect(self):
        try:
            a = Appearance(
                **{key: int(self.variables[key].get()) for key in ['font_size', 'label_size', 'comment_size', 'page_size']},
                font_face=self.font_options[self.variables['font_face'].get()],
                horizontal=self.variables['layout'].get() == '橫排',
                shift_left=self.mode_options[self.variables['shift_left'].get()],
                shift_right=self.mode_options[self.variables['shift_right'].get()])
        except (ValueError, KeyError) as error:
            raise SettingsError('請填完整的字級、候選數與選單設定。') from error
        return a, self.word_page.rows, self.shortcut_page.rows

    def dirty(self):
        try:
            a, words, phrases = self.collect()
            return (a != self.store.appearance or words != self.store.words.entries or phrases != self.store.phrases.entries
                    or bool(self.advanced_page.catalogue.pending)
                    or self.vocabulary_page.rules.rows != self.vocabulary_page.rules.original)
        except SettingsError:
            return True

    def draw_preview(self):
        if hasattr(self,'live_preview') and hasattr(self,'advanced_page') and hasattr(self.advanced_page,'catalogue'):
            try:self.live_preview.show(self.preview_documents(),self.store.root)
            except (SettingsError,ValueError,KeyError):pass
        return

    def preview_documents(self,extra=None):
        try:appearance=self.collect()[0]
        except SettingsError:appearance=self.store.appearance
        return documents(self.advanced_page.catalogue,appearance,self.store.appearance,extra)

    def fill_visual(self):
        previous=self.ready;self.ready=False
        config=self.preview_documents().get('weasel',{})
        themes=config.get('preset_color_schemes',{})
        self.theme_options={str(v.get('name',k))+'（'+k+'）':k for k,v in themes.items()}
        for path,var in self.visual_variables.items():
            value=config
            for part in path.split('/'):value=value.get(part) if isinstance(value,dict) else None
            if path in self.theme_boxes:
                options=dict(self.theme_options)
                if value not in options.values():options[str(value)]=value
                self.theme_boxes[path].configure(values=list(options))
                var.set(next(k for k,v in options.items() if v==value))
            elif path.endswith('inline_preedit'):var.set('開啟' if value else '關閉')
            else:var.set(str(value if value is not None else 0))
        self.ready=previous

    def visual_value(self,path):
        text=self.visual_variables[path].get()
        if path in self.theme_boxes:return self.theme_options.get(text,text)
        if path.endswith('inline_preedit'):return text=='開啟'
        if path.endswith('label_format'):return text
        value=int(text)
        if path.endswith('max_width') and not 0 <= value <= 4000:
            raise SettingsError('候選換行寬度請填 0～4000；0 表示不限制。')
        return value

    def visual_changed(self,path):
        if not self.ready:return
        try:
            value=self.visual_value(path)
            item=next(i for i in self.advanced_page.catalogue.items if i.scope=='weasel' and i.path==path)
            self.advanced_page.catalogue.stage(item,value)
            if path=='style/color_scheme':self.live_preview.mode.set('淺色情境')
            elif path=='style/color_scheme_dark':self.live_preview.mode.set('深色情境')
            self.advanced_page.render();self.mark_dirty();self.draw_preview()
        except SettingsError as error:
            self.status.set(str(error))
        except (ValueError,StopIteration):
            self.status.set('請填完整數值；預覽暫時保留上一個有效設定。')
    def multiline_candidates(self):
        self.variables['layout'].set('橫排')
        self.visual_variables['style/layout/max_width'].set('420')

    def suggest(self):
        self.variables['font_size'].set('18')
        self.variables['layout'].set('直排')
        self.variables['shift_right'].set('不切換')

    def summary(self, appearance, words, phrases):
        lines = []
        for key, name in FIELD_NAMES.items():
            old, new = getattr(self.store.appearance, key), getattr(appearance, key)
            if old != new:
                if key == 'horizontal':
                    old, new = ('橫排' if old else '直排'), ('橫排' if new else '直排')
                elif key.startswith('shift_'):
                    old = next((k for k, v in self.mode_options.items() if v == old), old)
                    new = next((k for k, v in self.mode_options.items() if v == new), new)
                lines.append(f'• {name}：{old} → {new}')
        for label, before, after in [('中文詞彙', self.store.words.entries, words), ('英文捷徑', self.store.phrases.entries, phrases)]:
            before_map, after_map = {e.uid: e for e in before}, {e.uid: e for e in after}
            added = len(after_map.keys() - before_map.keys())
            removed = len(before_map.keys() - after_map.keys())
            edited = sum(before_map[k] != after_map[k] for k in before_map.keys() & after_map.keys())
            if added or removed or edited:
                lines.append(f'• {label}：新增 {added}、編輯 {edited}、移除 {removed} 筆')
        return '\n'.join(lines)

    def build_changes(self, appearance, words, phrases):
        try:
            for path in self.visual_variables:self.visual_value(path)
        except ValueError as error:raise SettingsError('外觀的間距與圓角請填整數。') from error
        changes = self.store.build(appearance, words, phrases)
        # Don't let a whole parent structure silently replace preview edits.
        mapping = {'font_size': ('weasel', 'style/font_point'), 'label_size': ('weasel', 'style/label_font_point'),
                   'comment_size': ('weasel', 'style/comment_font_point'), 'font_face': ('weasel', 'style/font_face'),
                   'horizontal': ('weasel', 'style/horizontal'), 'page_size': ('default', 'menu/page_size'),
                   'shift_left': ('default', 'ascii_composer/switch_key/Shift_L'), 'shift_right': ('default', 'ascii_composer/switch_key/Shift_R')}
        for field, (scope, path) in mapping.items():
            if getattr(appearance, field) != getattr(self.store.appearance, field):
                if any(s == scope and (p == path or path.startswith(p + '/')) for s, p in self.advanced_page.catalogue.pending):
                    raise SettingsError('外觀頁與全部設定正在修改同一組設定；請先儲存其中一處，再調整另一處。')
        changes = self.advanced_page.catalogue.build(changes)
        return self.vocabulary_page.rules.build(changes, self.advanced_page.catalogue)

    def save(self, deploy):
        if self.busy:
            return
        try:
            appearance, words, phrases = self.collect()
            changes = self.build_changes(appearance, words, phrases)
            self.store.assert_unchanged()
            summary = self.summary(appearance, words, phrases)
            advanced_count = len(self.advanced_page.catalogue.pending)
            rules = self.vocabulary_page.rules
            rule_count = sum(rules.rows.get(k) != rules.original.get(k) for k in rules.rows.keys() | rules.original.keys())
            if advanced_count:
                summary += f'\n• 分類設定：調整 {advanced_count} 項'
            if rule_count:
                summary += f'\n• 詞彙個人規則：調整 {rule_count} 筆'
            if changes and not messagebox.askyesno('確認這次調整', summary.strip() + '\n\n儲存前會自動備份。' + ('\n重新部署時請先完成目前的文字輸入。' if deploy else ''), parent=self):
                return
            if not changes and not deploy:
                self.status.set('設定沒有變更；未寫入任何檔案。')
                return
        except Exception as error:
            messagebox.showerror('未儲存', str(error), parent=self)
            return
        # Snapshot all inputs before entering the worker; no UI reads from a thread.
        appearance, words, phrases = copy.deepcopy((appearance, words, phrases))
        def task():
            backup = self.store.commit_bytes(changes, '套用設定與詞彙調整前')
            if deploy:
                self.store.deploy()
                self.advanced_page.catalogue.verify()
            return backup
        self.run_task('正在儲存並重新部署…' if deploy else '正在儲存設定…', task,
                      '已儲存並完成重新部署。' if deploy else '已儲存；按「儲存並重新部署」後才會套用。')

    def reload(self):
        if self.dirty() and not messagebox.askyesno('重新讀取', '捨棄這次尚未儲存的調整，重新讀取檔案？', parent=self):
            return
        try:
            self.store.load()
            self.fill()
            self.status.set('已重新讀取目前設定。')
        except Exception as error:
            messagebox.showerror('讀取失敗', str(error), parent=self)

    def refresh_backups(self):
        self.backup_options = {}
        for path in self.store.list_backups():
            try:
                import json
                metadata = json.loads((path / 'manifest.json').read_text(encoding='utf-8'))
                label = f"{metadata['time'].replace('T', ' ')}　｜　{metadata['reason']}　({path.name[-6:]})"
                self.backup_options[label] = path
            except (ValueError, KeyError, OSError):
                continue
        self.backup_box.configure(values=list(self.backup_options))
        self.backup_choice.set(next(iter(self.backup_options), '尚無設定備份'))

    def backup(self):
        try:
            path = self.store.backup()
            self.refresh_backups()
            self.status.set(f'已備份目前磁碟上的設定：{path.name}')
        except Exception as error:
            messagebox.showerror('備份失敗', str(error), parent=self)

    def open_backups(self):
        self.store.backup_root.mkdir(parents=True, exist_ok=True)
        os.startfile(self.store.backup_root)

    def restore(self):
        path = self.backup_options.get(self.backup_choice.get())
        if not path:
            messagebox.showinfo('還原設定', '目前沒有可還原的設定備份。', parent=self)
            return
        text = '以選取的備份取代目前個人設定與詞彙，並重新部署？\n\n還原前會再備份目前檔案；不會回退使用者詞頻。'
        if self.dirty():
            text += '\n尚未儲存的畫面調整將會捨棄。'
        if not messagebox.askyesno('還原個人設定', text, parent=self):
            return
        def task():
            backup = self.store.restore(path)
            self.store.deploy()
            return backup
        self.run_task('正在還原並重新部署…', task, '已還原設定並完成重新部署。')

    def run_task(self, label, task, success):
        self.busy = tk.Toplevel(self)
        self.busy.title('請稍候')
        self.busy.transient(self)
        self.busy.resizable(False, False)
        self.busy.protocol('WM_DELETE_WINDOW', lambda: None)
        content = ttk.Frame(self.busy, padding=28)
        content.pack()
        ttk.Label(content, text=label, style='Section.TLabel').pack(anchor='w')
        ttk.Label(content, text='部署完成前請暫停輸入文字。', style='Muted.TLabel').pack(anchor='w', pady=(8, 14))
        progress = ttk.Progressbar(content, mode='indeterminate', length=360)
        progress.pack()
        progress.start(12)
        position_dialog(self.busy, self)
        self.busy.grab_set()
        def worker():
            try:
                result = task()
                self.events.put((True, success, result))
            except Exception as error:
                self.events.put((False, str(error), None))
        threading.Thread(target=worker, daemon=True).start()

    def poll(self):
        try:
            ok, text, result = self.events.get_nowait()
        except queue.Empty:
            pass
        else:
            if self.busy:
                self.busy.grab_release()
                self.busy.destroy()
                self.busy = None
            try:
                self.store.load()
                self.fill()
            except Exception as error:
                ok, text = False, f'{text}\n重新讀取時出錯：{error}'
            if ok:
                self.status.set(text + (f'　備份：{result.name}' if result else ''))
            else:
                self.status.set('操作未完成；請查看錯誤說明，必要時還原備份。')
                messagebox.showerror('操作未完成', text + '\n\n若設定已儲存但部署失敗，可到「備份與還原」恢復。', parent=self)
        self.after(100, self.poll)

    def close(self):
        if self.busy:
            return
        if self.dirty() and not messagebox.askyesno('離開設定工具', '還有尚未儲存的調整，確定捨棄並離開？', parent=self):
            return
        self.destroy()


def main():
    if '--export-learned' in sys.argv:
        try:
            from rime_learning import export_all
            index = sys.argv.index('--export-learned')
            export_all(*sys.argv[index+1:index+4])
        except Exception:
            raise SystemExit(2)
        return
    if '--refresh-flypy-patches' in sys.argv:
        try:
            from settings_core import refresh_flypy_patches
            index = sys.argv.index('--refresh-flypy-patches')
            refresh_flypy_patches(*sys.argv[index+1:index+3])
        except Exception:
            raise SystemExit(2)
        return
    configure_dpi()
    parser = argparse.ArgumentParser()
    parser.add_argument('--user-dir', type=Path, help=argparse.SUPPRESS)
    parser.add_argument('--weasel-root', type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    try:
        user_dir, weasel_root = (args.user_dir, args.weasel_root) if args.user_dir else discover_paths()
        mutex = None
        if os.name == 'nt':
            kernel = ctypes.WinDLL('kernel32', use_last_error=True)
            kernel.CreateMutexW.restype = ctypes.c_void_p
            kernel.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p]
            name = 'Local\\FlypySettings-' + hashlib.sha256(str(user_dir.resolve()).casefold().encode('utf-8')).hexdigest()[:20]
            mutex = kernel.CreateMutexW(None, False, name)
            if not mutex:
                raise SettingsError('無法建立設定工具的執行鎖，請稍後重試。')
            if ctypes.get_last_error() == 183:
                raise SettingsError('這個資料夾的設定工具已開啟，請從工作列切回原視窗。')
        store = Store(user_dir, weasel_root)
    except Exception as error:
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror(TITLE, f'無法讀取目前的雾凇小鶴設定。\n\n{error}', parent=root)
        root.destroy()
        return
    app = App(store)
    app.mainloop()
    if mutex:
        kernel.CloseHandle.argtypes = [ctypes.c_void_p]
        kernel.CloseHandle(mutex)


if __name__ == '__main__':
    main()

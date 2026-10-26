"""Lazy, read-only input statistics in the existing ttk settings UI."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import tkinter as tk
from tkinter import ttk
from input_statistics import read_snapshot, ranking
from settings_pages import scroll_table


class StatisticsPage(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, padding=18)
        self.app = app
        self.snapshot = None
        self.future = None
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix='InputStatistics')
        heading = ttk.Frame(self)
        heading.pack(fill='x')
        ttk.Label(heading, text='輸入統計', style='Section.TLabel').pack(side='left')
        self.refresh_button = ttk.Button(heading, text='更新統計', command=self.refresh)
        self.refresh_button.pack(side='right')
        ttk.Label(self, text='只整理小鶴學習紀錄；開啟此分頁時才在背景讀取，不逐鍵監控。',
                  style='Muted.TLabel').pack(anchor='w', pady=(6, 12))
        cards = ttk.Frame(self)
        cards.pack(fill='x', pady=(0, 10))
        self.values = []
        for column, title in enumerate(('累計學習選用', '累計中文字數', '字詞種類', '活躍中文速度（估算）')):
            cards.columnconfigure(column, weight=1)
            card = ttk.LabelFrame(cards, text=title, padding=10)
            card.grid(row=0, column=column, sticky='nsew', padx=(0, 8))
            var = tk.StringVar(value='—')
            ttk.Label(card, textvariable=var, style='Section.TLabel').pack(anchor='w')
            self.values.append(var)
        self.details = tk.StringVar(value='選擇此分頁後載入；舊資料可計算排行，新資料才有日期與速度。')
        ttk.Label(self, textvariable=self.details, style='Muted.TLabel', wraplength=1040).pack(anchor='w', pady=(0, 10))
        pages = ttk.Notebook(self)
        pages.pack(fill='both', expand=True)
        popular, daily, help_page = (ttk.Frame(pages, padding=10) for _ in range(3))
        pages.add(popular, text='常用字詞')
        pages.add(daily, text='每日紀錄')
        pages.add(help_page, text='數據怎麼算')
        tools = ttk.Frame(popular)
        tools.pack(fill='x', pady=(0, 8))
        self.kind = tk.StringVar(value='所有字詞')
        box = ttk.Combobox(tools, textvariable=self.kind, state='readonly', width=25,
                           values=('所有字詞', '常用詞（兩字以上）', '常用字（含詞內用字）'))
        box.pack(side='left')
        box.bind('<<ComboboxSelected>>', lambda _event: self.render_ranking())
        ttk.Label(tools, text='顯示前 100 名；同字不同讀音／繁簡模式合併次數，不合併不同字形。', style='Muted.TLabel').pack(side='left', padx=12)
        frame, self.top = scroll_table(popular, [('rank', '排名', 70), ('text', '字／詞', 380),
                                                  ('count', '選用／出現次數', 170), ('length', '字數', 100)])
        frame.pack(fill='both', expand=True)
        ttk.Label(daily, text='從本次更新後開始累積；沒有日期的舊資料不會編造每日紀錄。', style='Muted.TLabel').pack(anchor='w', pady=(0, 8))
        frame, self.daily = scroll_table(daily, [('date', '日期', 170), ('commits', '選用次數', 150),
                                                ('chars', '中文字數', 150), ('new', '首次學習筆數', 160),
                                                ('manual', '改選比例', 140)])
        frame.pack(fill='both', expand=True)
        explanation = (
            '統計範圍\n'
            '・只涵蓋小鶴原本會保存的 1～12 字完整中文組字；不等於整台電腦的總輸入量。\n'
            '・不讀取其他程式或密碼欄位；英文、貼上文字與完整長句不列入這份中文學習統計。\n'
            '・常用字會把詞內每個字按選用次數加總；例如「今天」選了三次，今、天各增加三次。\n\n'
            '速度是估算，不是測驗成績\n'
            '・只用原有選詞保存時順帶記下的秒級時間；同一次寫入，不新增逐鍵檔案操作。\n'
            '・連續兩次上屏間隔超過 30 秒、重新部署或時鐘倒退時切開樣本。\n'
            '・每段需至少 10 秒且五次後續上屏才納入；用總字數除以總有效時間，避免平均值失真。\n'
            '・段首的第一個詞不計入速度；思考與選字時間可能包含在內，不能和標準打字測驗直接比較。\n\n'
            '日期與保存\n'
            '・每日紀錄、首次學習與改選比例從這次更新後才開始；沒有資料時顯示尚未累積。\n'
            '・統計附在你原有的 Rime 學習紀錄，跟隨既有備份；不送往分析服務或 GitHub。\n'
            '・只在切入分頁或按「更新統計」時讀取；不修改候選排序、字形偏好或你的學習次數。')
        help_scroll = ttk.Scrollbar(help_page, orient='vertical')
        help_scroll.pack(side='right', fill='y')
        help_text = tk.Text(help_page, wrap='word', height=12, relief='flat',
                            font=('Microsoft JhengHei UI', 11), padx=10, pady=8,
                            yscrollcommand=help_scroll.set)
        help_text.pack(fill='both', expand=True)
        help_scroll.configure(command=help_text.yview)
        help_text.insert('1.0', explanation)
        help_text.configure(state='disabled')
        self.notice = tk.StringVar(value='尚未載入統計。')
        ttk.Label(self, textvariable=self.notice, style='Muted.TLabel').pack(anchor='w', pady=(8, 0))
        app.tabs.bind('<<NotebookTabChanged>>', self.selected, add='+')
        self.bind('<Destroy>', self.destroyed, add='+')

    def selected(self, _event=None):
        if self.app.tabs.select() == str(self):
            self.refresh()

    def refresh(self):
        if self.future is not None:
            return
        self.refresh_button.configure(state='disabled')
        self.notice.set('正在背景整理學習紀錄…')
        self.future = self.pool.submit(read_snapshot, self.app.store.root)
        self.after(100, self.poll)

    def poll(self):
        if not self.future.done():
            self.after(100, self.poll)
            return
        try:
            self.snapshot = self.future.result()
            data = self.snapshot
            speed = data['speed_cpm']
            values = (f"{data['selections']:,} 次", f"{data['total_characters']:,} 字",
                      f"{data['unique_words']:,} 種", f'{speed:.0f} 字／分' if speed is not None else '尚未累積')
            for var, value in zip(self.values, values):
                var.set(value)
            longest = data['longest'] or '尚無資料'
            self.details.set(f"平均每次 {data['average_length']:.1f} 字｜最長學習詞：{longest}｜有效速度樣本：{data['speed_seconds']:,} 秒")
            self.render_ranking()
            self.daily.delete(*self.daily.get_children())
            for day, row in list(data['days'].items())[:366]:
                self.daily.insert('', 'end', values=(day, f"{row['commits']:,}", f"{row['characters']:,}",
                                                    f"{row['new']:,}", f"{100*row['manual']/row['commits']:.1f}%"))
            self.notice.set('已更新：' + datetime.now().strftime('%Y/%m/%d %H:%M:%S') + '；統計為唯讀，最多顯示最近 366 個有紀錄的日期。')
        except Exception as error:
            self.notice.set('無法讀取統計：' + str(error))
        finally:
            self.future = None
            self.refresh_button.configure(state='normal')

    def render_ranking(self):
        if self.snapshot is None:
            return
        self.top.delete(*self.top.get_children())
        for number, (text, count) in enumerate(ranking(self.snapshot, self.kind.get()), 1):
            self.top.insert('', 'end', values=(number, text, f'{count:,}', len(text)))

    def destroyed(self, event):
        if event.widget is self:
            self.pool.shutdown(wait=False, cancel_futures=True)

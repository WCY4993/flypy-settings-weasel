"""Read-only manual derived from the current settings, including staged edits."""
import tkinter as tk
from tkinter import ttk
from settings_core import SHIFT_MODES

KEYS={'Control':'Ctrl','grave':'`','numbersign':'3 / #','dollar':'4 / $','minus':'−','equal':'=','space':'Space','Return':'Enter','BackSpace':'Backspace','Page_Up':'Page Up','Page_Down':'Page Down','bracketleft':'[','bracketright':']','Shift_L':'左 Shift','Shift_R':'右 Shift','Caps_Lock':'Caps Lock','Control_L':'左 Ctrl','Control_R':'右 Ctrl','period':'.','asterisk':'*','plus':'+','slash':'/','Shift':'Shift'}
ACTIONS={'commit_text':'上屏目前候選後切換中英文','commit_code':'上屏原始編碼後切換中英文','clear':'清除未完成輸入後切換','inline_ascii':'暫時輸入英文','noop':'不切換','revert':'退回上一段組字／刪除輸入','back_syllable':'刪除上一個音節','delete_candidate':'刪除或降低目前學習候選的權重（對內建詞不一定有效）','commit_script_text':'上屏拼音編碼','commit_comment':'上屏候選註解','delete':'向後刪除','cancel':'取消未完成輸入','commit_raw_input':'上屏原始按鍵文字','confirm':'確認目前候選'}
OPTIONS={'traditionalization':'切換繁體／簡體','ascii_punct':'切換中文／英文標點','emoji':'切換 Emoji 候選','full_shape':'切換全形／半形','ascii_mode':'切換中文／英文','search_single_char':'切換單字模式'}
WHEN={'always':'小狼毫啟用時','composing':'正在組字時','has_menu':'有候選清單時','paging':'候選已翻頁時'}

def key_name(raw):
    raw=str(raw)
    if raw.startswith('KP_'): return '數字鍵盤 '+KEYS.get(raw[3:],raw[3:])
    return ' + '.join(KEYS.get(x,x) for x in raw.split('+'))

def manual_rows(documents):
    default=documents.get('default',{});schema=documents.get('double_pinyin_flypy',{})
    rows=[]
    def add(group,key,action,condition,note=''):rows.append((group,key,action,condition,note))
    for key,mode in default.get('ascii_composer',{}).get('switch_key',{}).items():
        if key.startswith('Control') and mode=='noop':continue
        note='只指單按後放開；按住 Shift 再打字仍可輸入大寫或符號。'
        if key=='Caps_Lock':note='大寫鎖定依 Windows 狀態；有未完成輸入時依此設定處理。'
        add('切換與選字',key_name(key),ACTIONS.get(mode,'原始行為：'+str(mode)),'中文模式',note)
    hotkeys=default.get('switcher',{}).get('hotkeys',[])
    menu=' 或 '.join(key_name(k) for k in hotkeys) or '未配置快捷鍵'
    add('切換與選字',menu,'開啟輸入方案與狀態選單','小狼毫啟用時','在選單中切換 Emoji、繁簡、全半形等狀態；以實際選單為準。')
    add('切換與選字','數字 1～9','選取對應編號的候選','有候選清單時','只會有目前每頁候選數所列的編號；0 的行為依實際選字設定。')
    bindings=schema.get('key_binder',default.get('key_binder',{}))
    for item in bindings.get('bindings',[]):
        if not isinstance(item,dict):continue
        action=OPTIONS.get(item.get('toggle')) if 'toggle' in item else None
        if 'send' in item:action='送出 '+key_name(item['send'])
        if 'select' in item:action='選擇狀態 '+str(item['select'])
        if 'set_option' in item:action='啟用 '+str(item['set_option'])
        if 'unset_option' in item:action='停用 '+str(item['unset_option'])
        add('翻頁與快捷鍵',key_name(item.get('accept','未指定')),action or '進階規則：'+str(item),WHEN.get(item.get('when'),str(item.get('when','依配置'))))
    for key,action in schema.get('editor',{}).get('bindings',{}).items():
        add('編輯輸入',key_name(key),ACTIONS.get(action,'原始行為：'+str(action)),'正在組字／選字時')
    for field,label in [('select_first_character','取目前候選的第一個字'),('select_last_character','取目前候選的最後一個字')]:
        code=bindings.get(field)
        if code:add('切換與選字',key_name(code),label,'有候選清單時','這是以詞取字，不是翻頁；實際翻頁鍵請參閱「翻頁與快捷鍵」。')
    add('工具操作','外觀與按鍵 → 試用多行候選','橫排候選自動換行','小鶴設定工具內','可調整候選換行寬度；0 為單行。先看即時預覽，再儲存並重新部署。每頁候選數不變。')
    names={'date':'今天日期','time':'目前時間','week':'今天星期','datetime':'日期與時間','timestamp':'Unix 時間戳','datezh':'中文日期','dateen':'英文日期'}
    for key,code in schema.get('date_translator',{}).items():
        if key in names:add('日期與工具',str(code),names[key],'中文模式，直接輸入這組字母','從候選清單選擇需要的格式。')
    if isinstance(schema.get('lunar'),str):add('日期與工具',schema['lunar'],'今天農曆','中文模式，直接輸入')
    patterns=schema.get('recognizer',{}).get('patterns',{})
    for name,example,action,note in [('number','R1234','數字轉中文／金額','R 要大寫；選取一般數字或大寫金額候選。'),('gregorian_to_lunar','N20261019','指定公曆轉農曆','N 要大寫；後接年月日。'),('unicode','U4e2d','Unicode 字元輸入','U 要大寫；後接十六進位字碼。'),('calculator','cC1+2','計算器','大小寫依範例；輸入算式後選取結果。'),('radical_lookup',str(schema.get('radical_lookup',{}).get('prefix','uU'))+'mumu','拆字反查','前綴大小寫須相同；例以 mu mu 拆查「林」。'),('punct','Vhelp','符號說明','V 要大寫；查看目前符號表。')]:
        if name in patterns:add('日期與工具',example,action,'中文模式',note+' 原始辨識規則：'+str(patterns[name]))
    add('日期與工具',menu+' → Emoji','開啟／關閉 Emoji 候選','輸入方案與狀態選單','開啟後輸入相關詞，例如「笑」，候選中可出現表情符號；未配置獨立 Emoji 快捷鍵時使用此選單。')
    add('工具操作','Ctrl + S','僅儲存設定','小鶴設定工具內','要套用到輸入法，請按「儲存並重新部署」。')
    add('工具操作','雙擊設定項目','開啟設定編輯視窗','全部設定分頁','適用項目會附預覽；複雜規則可展開編輯。')
    return rows

class ShortcutHelpPage(ttk.Frame):
    def __init__(self,parent,app):
        super().__init__(parent,padding=18);self.app=app;self.rows=[]
        ttk.Label(self,text='快捷鍵對照表',style='Section.TLabel').pack(anchor='w')
        ttk.Label(self,text='依目前設定整理，包含尚未儲存的調整；切回本頁會更新。中文模式的輸入碼須區分大小寫。',style='Muted.TLabel',wraplength=1000).pack(anchor='w',pady=(6,12))
        bar=ttk.Frame(self);bar.pack(fill='x',pady=(0,10))
        self.category=tk.StringVar(value='全部');self.search=tk.StringVar()
        ttk.Label(bar,text='分類').pack(side='left');ttk.Combobox(bar,textvariable=self.category,values=['全部','切換與選字','翻頁與快捷鍵','編輯輸入','日期與工具','工具操作'],state='readonly',width=18).pack(side='left',padx=8)
        ttk.Label(bar,text='搜尋').pack(side='left');ttk.Entry(bar,textvariable=self.search,width=28).pack(side='left',padx=8)
        ttk.Button(bar,text='更新對照表',command=self.refresh).pack(side='right')
        detail=ttk.LabelFrame(self,text='用法與注意事項',padding=12);detail.pack(side='bottom',fill='x',pady=(12,0))
        self.details=tk.StringVar(value='選取一列即可查看完整說明。')
        label=ttk.Label(detail,textvariable=self.details,wraplength=1000);label.pack(fill='x');detail.bind('<Configure>',lambda e:label.configure(wraplength=max(250,e.width-30)))
        frame=ttk.Frame(self);frame.pack(fill='both',expand=True)
        self.tree=ttk.Treeview(frame,columns=('category','key','action','condition'),show='headings',selectmode='browse')
        for col,title,width in [('category','分類',130),('key','按鍵／輸入碼',240),('action','功能',360),('condition','使用時機',210)]:self.tree.heading(col,text=title);self.tree.column(col,width=width,minwidth=100)
        vs=ttk.Scrollbar(frame,orient='vertical',command=self.tree.yview);hs=ttk.Scrollbar(frame,orient='horizontal',command=self.tree.xview)
        self.tree.configure(yscrollcommand=vs.set,xscrollcommand=hs.set);self.tree.grid(row=0,column=0,sticky='nsew');vs.grid(row=0,column=1,sticky='ns');hs.grid(row=1,column=0,sticky='ew');frame.rowconfigure(0,weight=1);frame.columnconfigure(0,weight=1)
        self.category.trace_add('write',lambda *_:self.render());self.search.trace_add('write',lambda *_:self.render());self.tree.bind('<<TreeviewSelect>>',self.describe)
        app.tabs.bind('<<NotebookTabChanged>>',lambda e:self.refresh() if app.tabs.select()==str(self) else None,add='+')
    def refresh(self):self.rows=manual_rows(self.app.preview_documents());self.render()
    def render(self):
        self.tree.delete(*self.tree.get_children());q=self.search.get().casefold()
        for i,row in enumerate(self.rows):
            if self.category.get()!='全部' and row[0]!=self.category.get():continue
            if q and q not in ' '.join(row).casefold():continue
            self.tree.insert('','end',iid=str(i),values=row[:4])
        self.details.set('選取一列即可查看完整說明。此頁只供查閱，不會真的送出按鍵或改動設定。')
    def describe(self,event=None):
        selected=self.tree.selection()
        if selected:
            row=self.rows[int(selected[0])];self.details.set(f'{row[1]}：{row[2]}。使用時機：{row[3]}。\n{row[4]}')

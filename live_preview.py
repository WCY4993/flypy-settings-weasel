"""Offline previews of effective (including unsaved) settings. Never sends keys."""
from __future__ import annotations
import copy
from datetime import datetime
import tkinter as tk
from tkinter import ttk
import tkinter.font as tkfont
from taiwan_text import TaiwanConverter

def assign(document, path, value):
    node = document
    parts = path.split('/')
    for part in parts[:-1]:
        if not isinstance(node.get(part), dict): node[part] = {}
        node = node[part]
    node[parts[-1]] = copy.deepcopy(value)

def documents(catalogue, appearance=None, original=None, extra=None):
    result = copy.deepcopy(catalogue.effective)
    for (scope, path), value in catalogue.pending.items():
        assign(result.setdefault(scope, {}), path, value)
    if appearance and original:
        mapping = {'font_size':('weasel','style/font_point'), 'label_size':('weasel','style/label_font_point'),
          'comment_size':('weasel','style/comment_font_point'), 'font_face':('weasel','style/font_face'),
          'horizontal':('weasel','style/horizontal'), 'page_size':('default','menu/page_size'),
          'shift_left':('default','ascii_composer/switch_key/Shift_L'), 'shift_right':('default','ascii_composer/switch_key/Shift_R')}
        for key, (scope,path) in mapping.items():
            if getattr(appearance,key) != getattr(original,key): assign(result.setdefault(scope,{}), path, getattr(appearance,key))
    for (scope,path), value in (extra or {}).items(): assign(result.setdefault(scope,{}),path,value)
    return result

def preview_kind(scope, path):
    if scope == 'weasel' and (path.startswith('style') or path.startswith('preset_color_schemes')): return 'appearance'
    if path.startswith(('traditionalize','switches','punctuator','date_translator','lunar','ascii_composer','key_binder','editor')): return 'example'
    return None

def system_is_dark():
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,r'Software\Microsoft\Windows\CurrentVersion\Themes\Personalize') as key:
            return winreg.QueryValueEx(key,'AppsUseLightTheme')[0] == 0
    except (OSError,ImportError): return False

def rgb(value, background='#eef1f5', fmt='abgr'):
    """Weasel BGR/ABGR -> RGB, composited against the preview background."""
    try: number = int(value,0) if isinstance(value,str) else int(value)
    except (ValueError,TypeError): return background
    number &= 0xffffffff
    if fmt == 'argb': red,green,blue = (number>>16)&255,(number>>8)&255,number&255
    elif fmt == 'rgba': red,green,blue = (number>>24)&255,(number>>16)&255,(number>>8)&255
    else: red,green,blue = number&255,(number>>8)&255,(number>>16)&255
    wide = getattr(value,'_width',0) or 0
    alpha = (number&255) if fmt=='rgba' else (number>>24)&255 if number>0xffffff or wide>=8 else 255
    bg = [int(background[n:n+2],16) for n in (1,3,5)]
    return '#'+''.join(f'{round(c*alpha/255+b*(1-alpha/255)):02x}' for c,b in zip((red,green,blue),bg))

def active_theme(config, mode='auto', forced=None):
    style = config.get('style',{})
    dark = system_is_dark() if mode=='auto' else mode=='dark'
    name = forced or style.get('color_scheme_dark' if dark else 'color_scheme', style.get('color_scheme','aqua'))
    return name, config.get('preset_color_schemes',{}).get(name,{})

def round_rect(canvas,x1,y1,x2,y2,radius,**options):
    radius = min(max(0,radius),max(0,(x2-x1)/2),max(0,(y2-y1)/2))
    if not radius: return canvas.create_rectangle(x1,y1,x2,y2,**options)
    points=[x1+radius,y1,x2-radius,y1,x2,y1,x2,y1+radius,x2,y2-radius,x2,y2,x2-radius,y2,x1+radius,y2,x1,y2,x1,y2-radius,x1,y1+radius,x1,y1]
    return canvas.create_polygon(points,smooth=True,splinesteps=20,**options)

def numerical(style,path,default,low=0,high=500):
    node=style
    try:
        for part in path.split('/'): node=node[part]
        return max(low,min(high,float(node)))
    except (KeyError,ValueError,TypeError): return default

class LivePreview(ttk.Frame):
    def __init__(self,parent,kind='appearance',changed=None):
        super().__init__(parent)
        self.kind,self.config,self.forced,self.root,self.path = kind,None,None,None,''
        self.selected=0;self.bounds=[]
        self.changed=changed
        header=ttk.Frame(self); header.pack(fill='x',pady=(0,8))
        self.mode=tk.StringVar(value='跟隨 Windows');self.comments=tk.BooleanVar(value=True)
        if kind=='appearance':
            ttk.Combobox(header,textvariable=self.mode,values=['跟隨 Windows','淺色情境','深色情境'],state='readonly',width=14).pack(side='left')
            ttk.Checkbutton(header,text='範例註解',variable=self.comments,command=self.redraw).pack(side='left',padx=8)
        self.note=ttk.Label(self,text='',style='Muted.TLabel',wraplength=410)
        self.note.pack(side='bottom',anchor='w',fill='x',pady=(8,0))
        panel=ttk.Frame(self);panel.pack(fill='both',expand=True)
        panel.rowconfigure(0,weight=1);panel.columnconfigure(0,weight=1)
        self.canvas=tk.Canvas(panel,background='#eef1f5',highlightthickness=0,width=400,height=280)
        vertical=ttk.Scrollbar(panel,orient='vertical',command=self.canvas.yview)
        horizontal=ttk.Scrollbar(panel,orient='horizontal',command=self.canvas.xview)
        self.canvas.configure(yscrollcommand=vertical.set,xscrollcommand=horizontal.set)
        self.canvas.grid(row=0,column=0,sticky='nsew');vertical.grid(row=0,column=1,sticky='ns');horizontal.grid(row=1,column=0,sticky='ew')
        self.canvas.bind('<Configure>',lambda e:self.redraw())
        self.canvas.bind('<Button-1>',self.choose_candidate)
        self.mode.trace_add('write',lambda *_:self.redraw())

    def show(self,config,root=None,scope=None,path='',forced=None):
        self.config,self.root,self.path,self.forced,self.scope=config,root,path,forced,scope
        self.redraw()

    def choose_candidate(self,event):
        x,y=self.canvas.canvasx(event.x),self.canvas.canvasy(event.y)
        for index,(left,top,width,height) in enumerate(self.bounds):
            if left<=x<=left+width and top<=y<=top+height:
                self.selected=index;self.redraw();return

    def redraw(self):
        if not self.config:return
        self.canvas.delete('all')
        if self.kind=='appearance': self.draw_appearance()
        else:self.draw_example()
        box=self.canvas.bbox('all') or (0,0,400,200)
        self.canvas.configure(scrollregion=(0,0,max(self.canvas.winfo_width(),box[2]+25),max(self.canvas.winfo_height(),box[3]+25)))

    def draw_appearance(self):
        config=self.config.get('weasel',{});style=config.get('style',{})
        mode={'跟隨 Windows':'auto','淺色情境':'light','深色情境':'dark'}[self.mode.get()]
        theme_name,theme=active_theme(config,mode,self.forced)
        fmt=theme.get('color_format','abgr');c=self.canvas
        color=lambda name,default:rgb(theme.get(name,default),'#eef1f5',fmt)
        back=color('back_color',0xffffff);border=color('border_color',0xd0d0d0)
        def font(key,default,size_key):
            face=str(style.get(key,default)).split(',')[0].split(':')[0].strip()
            return tkfont.Font(family=face,size=round(numerical(style,size_key,14,8,40)))
        body=font('font_face','Microsoft JhengHei UI','font_point')
        labels=font('label_font_face','Segoe UI','label_font_point')
        notes=font('comment_font_face','Microsoft JhengHei UI','comment_font_point')
        count=int(self.config.get('default',{}).get('menu',{}).get('page_size',8))
        samples=[('今天','jin tian'),('天氣','tian qi'),('學習','xue xi'),('工作','gong zuo'),('生活','sheng huo'),('閱讀','yue du'),('Hello',''),('世界','shi jie'),('朋友','peng you')][:max(1,min(9,count))]
        padding=numerical(style,'layout/hilite_padding',3,0,40)
        mx=numerical(style,'layout/margin_x',8,0,100);my=numerical(style,'layout/margin_y',8,0,100)
        gap=numerical(style,'layout/candidate_spacing',6,0,100)
        label_gap=numerical(style,'layout/hilite_spacing',5,0,100)
        border_width=numerical(style,'layout/border_width',1,0,20)
        minw=numerical(style,'layout/min_width',0,0,3000);minh=numerical(style,'layout/min_height',0,0,2000)
        maxw=numerical(style,'layout/max_width',0,0,4000)
        line=max(body.metrics('linespace'),labels.metrics('linespace'),notes.metrics('linespace'))
        ratio=numerical(style,'layout/linespacing',0,0,400)
        if ratio:line=max(line,body.cget('size')*ratio/100)
        line+=padding*2
        x0,y0=22,24
        x,y=x0+mx,y0+my
        preedit=not bool(style.get('inline_preedit',False))
        if preedit:y+=body.metrics('linespace')+numerical(style,'layout/spacing',10,0,100)
        cells=[];horizontal=bool(style.get('horizontal'));vertical=bool(style.get('vertical_text'))
        abbrev=int(numerical(style,'candidate_abbreviate_length',0,0,500))
        for i,(word,comment) in enumerate(samples):
            if abbrev and len(word)>abbrev:word=word[:max(1,abbrev-1)]+'…'
            format_text=str(style.get('label_format','%s'))
            label=format_text.replace('%s',str(i+1)).replace('%d',str(i+1))
            note=comment if self.comments.get() else ''
            width=labels.measure(label)+label_gap+body.measure(word)+padding*2
            if note:width+=label_gap+notes.measure(note)
            height=line
            if vertical:
                width=max(body.measure(ch) for ch in word)+padding*2+labels.measure(label)
                height=(len(word)+1)*body.metrics('linespace')+padding*2
            elif horizontal and maxw and x>x0+mx and x+width>x0+maxw-mx:
                x=x0+mx;y+=line+gap
            cells.append([x,y,width,height,label,word,note])
            if horizontal or vertical:x+=width+gap
            else:y+=height+gap
        window_right=max(x0+minw,max(cell[0]+cell[2] for cell in cells)+mx)
        window_bottom=max(y0+minh,max(cell[1]+cell[3] for cell in cells)+my)
        if vertical and not style.get('vertical_text_left_to_right',False):
            for cell in cells:cell[0]=window_right-mx-(cell[0]-x0-mx)-cell[2]
        radius=numerical(style,'layout/corner_radius',6,0,100)
        shadow=numerical(style,'layout/shadow_radius',0,0,50)
        if shadow:
            dx=numerical(style,'layout/shadow_offset_x',4,-100,100);dy=numerical(style,'layout/shadow_offset_y',4,-100,100)
            round_rect(c,x0+dx-shadow/3,y0+dy-shadow/3,window_right+dx+shadow/3,window_bottom+dy+shadow/3,radius,fill=color('shadow_color',0x55000000),outline='')
        round_rect(c,x0,y0,window_right,window_bottom,radius,fill=back,outline=border if border_width else '',width=border_width)
        if preedit:
            text='she zhi xiang mu' if style.get('preedit_type','composition')=='composition' else '設置項目'
            c.create_text(x0+mx,y0+my,text=text,font=body,anchor='nw',fill=color('text_color',0x222222))
        self.bounds=[]
        if self.selected>=len(cells):self.selected=0
        for i,(x,y,w,h,label,word,note) in enumerate(cells):
            if not horizontal and not vertical:w=window_right-mx-x
            self.bounds.append((x,y,w,h))
            selected=i==self.selected
            fill=color('hilited_candidate_back_color',0xe6d2ba) if selected else color('candidate_back_color',theme.get('back_color',0xffffff))
            round_rect(c,x,y,x+w,y+h,numerical(style,'layout/round_corner',4,0,100),fill=fill,outline=color('hilited_candidate_border_color',theme.get('hilited_candidate_back_color',0xe6d2ba)) if selected and 'hilited_candidate_border_color' in theme else '')
            text_color=color('hilited_candidate_text_color' if selected else 'candidate_text_color',0x222222)
            label_color=color('hilited_label_color' if selected else 'label_color',theme.get('hilited_candidate_text_color' if selected else 'candidate_text_color',0x666666))
            if vertical:
                c.create_text(x+padding,y+padding,text=label,font=labels,fill=label_color,anchor='nw')
                for n,char in enumerate(word):c.create_text(x+padding,y+padding+(n+1)*body.metrics('linespace'),text=char,font=body,fill=text_color,anchor='nw')
                continue
            yy=y+h/2
            c.create_text(x+padding,yy,text=label,font=labels,fill=label_color,anchor='w')
            text_x=x+padding+labels.measure(label)+label_gap
            align=style.get('layout',{}).get('align_type','center')
            body_y=y+padding if align=='top' else y+h-padding-body.metrics('linespace') if align=='bottom' else yy-body.metrics('linespace')/2
            c.create_text(text_x,body_y,text=word,font=body,fill=text_color,anchor='nw')
            mark=str(style.get('mark_text',''))
            if selected and mark:c.create_text(x-3,yy,text=mark,font=labels,fill=color('hilited_mark_color',theme.get('hilited_candidate_text_color',0x222222)),anchor='e')
            if note:c.create_text(text_x+body.measure(word)+label_gap,yy,text=note,font=notes,fill=color('hilited_comment_text_color' if selected else 'comment_text_color',0x888888),anchor='w')
        extra='直書為排列示意。' if vertical else ''
        self.note.configure(text=f'主題：{theme.get("name",theme_name)}。可點候選查看反白；超出畫面可捲動。{extra}Windows 陰影、字體平滑與螢幕邊緣定位以實際候選窗為準。')

    def draw_example(self):
        schema=self.config.get(self.scope or 'double_pinyin_flypy',{})
        path=self.path;now=datetime.now();lines=[]
        if path.startswith(('traditionalize','switches')):
            config=schema.get('traditionalize',{}).get('opencc_config','s2tw.json')
            if config not in ('flypy_s2twp.json','s2tw.json','s2twp.json'):
                self.canvas.create_text(16,16,text='自訂轉換表：'+config+'\n\n此預覽支援內建的三種轉換方式；其他自訂表請部署後在 Rime 實測。',anchor='nw',width=330,font=('Microsoft JhengHei UI',11))
                self.note.configure(text='自訂 OpenCC 對照表的實際輸出不在此模擬範圍內。');return
            convert=TaiwanConverter(self.root,config)
            enabled=next((s.get('reset',0) for s in schema.get('switches',[]) if s.get('name')=='traditionalization'),1)
            lines=['繁簡與用語範例（以預設狀態示意）','']
            for text in ['设置','项目','研究项目','软件','信息','网络','视频','打印']:
                lines.append(text+'  →  '+(convert.convert(text) if enabled else text))
            for switch in schema.get('switches',[]):
                if switch.get('name')=='emoji':lines+=['', 'Emoji 預設：'+('開啟 😊' if switch.get('reset',0) else '關閉，保留文字候選')]
        elif path.startswith(('date_translator','lunar')):
            d=schema.get('date_translator',{})
            examples={'date':now.strftime('%Y-%m-%d'),'time':now.strftime('%H:%M:%S'),'week':'星期'+'一二三四五六日'[now.weekday()],
              'datetime':now.astimezone().isoformat(timespec='seconds'),'datezh':f'{now.year}年{now.month}月{now.day}日','dateen':now.strftime('%B %d, %Y'),'timestamp':str(int(now.timestamp()))}
            lines=['輸入這些呼叫碼，可得到以下格式：','']
            for key,value in examples.items():lines += [str(d.get(key,key))+'  →  '+value]
            lines+=['','農曆呼叫碼：'+str(schema.get('lunar','lunar')),'農曆結果由 Rime 模組計算，此處只示意呼叫方式。']
        elif path.startswith('punctuator'):
            shape='full_shape' if 'full_shape' in path else 'half_shape'
            table=schema.get('punctuator',{}).get(shape,{})
            lines=['標點按鍵  →  輸出文字','']
            for key in [',','.','?','!',';',':','[',']','"',"'",'(',')']:
                value=table.get(key,key)
                if isinstance(value,dict):value=value.get('commit',value.get('pair',value))
                if isinstance(value,list):value=' ／ '.join(map(str,value))
                lines.append(key+'   →   '+str(value))
        else:
            from setting_help import shown_value,KEYS
            defaults=self.config.get('default',{})
            composer=schema.get('ascii_composer',defaults.get('ascii_composer',{}))
            lines=['按鍵行為示意（不會真的送出按鍵）','']
            if path.startswith('key_binder'):
                bindings=schema.get('key_binder',defaults.get('key_binder',{})).get('bindings',[])
                when={'always':'隨時','composing':'組字中','has_menu':'有候選時','paging':'翻頁時'}
                for binding in bindings[:16]:
                    if not isinstance(binding,dict):continue
                    action='切換 '+binding['toggle'] if 'toggle' in binding else binding.get('send','')
                    lines.append(str(binding.get('accept',''))+' → '+str(action)+'（'+when.get(binding.get('when'),str(binding.get('when','')))+'）')
            elif path.startswith('editor'):
                for key,action in schema.get('editor',{}).get('bindings',{}).items():lines.append(KEYS.get(key,key)+'：'+shown_value(action))
            else:
                for key,label in [('Shift_L','左 Shift'),('Shift_R','右 Shift'),('Caps_Lock','Caps Lock')]:lines.append(label+'：'+shown_value(composer.get('switch_key',{}).get(key,'noop')))
            lines+=['','示意內容不會操作你的電腦。']
        self.canvas.create_text(16,16,text='\n'.join(lines),anchor='nw',fill='#243447',font=('Microsoft JhengHei UI',11),width=max(280,self.canvas.winfo_width()-35))
        self.note.configure(text='這是尚未儲存設定的輸出示例；需按「儲存並重新部署」才會套用到輸入法。')

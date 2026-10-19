"""Human-facing Traditional Chinese names; original identifiers stay unchanged."""
import re

# Short label, followed by the effect rather than a literal word-for-word gloss.
HELP = {
 'style': ('候選視窗外觀', '設定輸入時看到的字體、配色和排列方式。'),
 'preset_color_schemes': ('配色主題庫', '各主題的色彩定義。編輯主題不會自動切換到它；可先預覽，再從淺／深色模式配色選取。'),
 'layout': ('視窗尺寸與間距', '調整候選窗的邊距、行距、圓角、邊框和陰影。尺寸為小狼毫使用的邏輯尺寸，實際會受螢幕縮放影響。'),
 'font_face': ('候選字體', '中文字體名稱；逗號後的字體用作缺字時的替代。保留系統內建字體即可。'),
 'font_point': ('候選字級', '候選文字大小，單位為點。右側預覽會同步顯示。'),
 'label_font_face': ('選字數字字體', '控制 1、2、3 等選字標號的字體。'),
 'label_font_point': ('選字數字大小', '控制候選前方數字的字級。'),
 'comment_font_face': ('候選註解字體', '控制候選右側拼音或反查提示的字體；沒有註解的候選不會顯示這段文字。'),
 'comment_font_point': ('候選註解大小', '控制拼音或反查提示字級。可在預覽勾選「範例註解」查看。'),
 'color_scheme': ('淺色模式配色', 'Windows 淺色模式下使用的主題；可在預覽切換淺色／深色情境比較。'),
 'color_scheme_dark': ('深色模式配色', 'Windows 深色模式下使用的主題；若與淺色主題相同，兩種情境會使用相同配色。'),
 'horizontal': ('候選橫向排列', '開啟時候選由左到右排列；關閉時一列顯示一個候選。這和中文字本身的直書是不同選項。'),
 'vertical_text': ('中文字直書', '把文字改為由上而下的直書排列。此功能較少用，預覽提供排列示意。'),
 'vertical_text_left_to_right': ('直書欄位由左往右', '只在直書模式生效；決定各候選欄位向左或向右接續。'),
 'vertical_text_with_wrap': ('直書允許換欄', '只在直書模式生效；過長文字可換到另一欄。'),
 'vertical_auto_reverse': ('貼近下緣時反轉候選順序', '候選窗因螢幕下緣而移到游標上方時，自動反轉候選的顯示方向；靜態預覽無法重現螢幕邊緣行為。'),
 'inline_preedit': ('在文字欄內顯示正在輸入的編碼', '開啟時把尚未選字的拼音顯示在應用程式文字欄；部分程式可能不支援。關閉時改在候選窗顯示。'),
 'preedit_type': ('未完成輸入的顯示方式', 'composition 顯示正在組合的編碼；preview 顯示預計上屏文字；preview_all 顯示更完整的預覽。保留識別碼供精確設定。'),
 'display_tray_icon': ('顯示工作列輸入法圖示', '控制小狼毫的通知區圖示；不改動 Windows 的輸入法清單。'),
 'global_ascii': ('跨程式共用中英狀態', '開啟後小狼毫共用中／英切換狀態；Windows 每個程式使用不同輸入法的選項仍由系統管理。'),
 'show_notifications': ('顯示狀態提示', '切換繁簡、全半形或方案時顯示提示。'),
 'show_notifications_time': ('狀態提示停留時間', '單位為毫秒；1000 毫秒等於 1 秒。'),
 'antialias_mode': ('字體邊緣平滑方式', 'default 使用系統預設；cleartype 為次像素平滑；grayscale 為灰階平滑；aliased 不做平滑。模擬預覽使用程式本身的字型繪製。'),
 'ascii_tip_follow_cursor': ('英文狀態提示跟隨游標', '切成英文時，讓狀態提示靠近輸入游標。'),
 'candidate_abbreviate_length': ('過長候選的縮短長度', '候選過長時縮短顯示；0 表示不縮短。只影響顯示，選取後仍輸出完整文字。'),
 'click_to_capture': ('滑鼠擷取相關行為', '這是小狼毫原生的進階 click_to_capture 選項；目前沒有足夠資訊保證各程式中的行為，建議保留原值。'),
 'fullscreen': ('全螢幕候選窗', '讓候選窗採用全螢幕顯示模式；預覽只示意內容，不會把整個桌面改成全螢幕。'),
 'label_format': ('選字數字格式', '例如 %s 顯示 1，%s. 顯示 1.，(%s) 顯示 (1)。%s 是數字的占位符，請保留。'),
 'mark_text': ('選中候選的標記', '在選中候選旁顯示的符號，例如 ▸；空白表示不另外顯示文字標記。'),
 'hover_type': ('滑鼠指向候選的反應', 'none 不額外反白；hilite 跟隨滑鼠反白；semi_light 使用較輕的提示效果。'),
 'mouse_hover_ms': ('滑鼠停留等待時間', '滑鼠停留多久後觸發指向行為，單位為毫秒。'),
 'paging_on_scroll': ('滑鼠滾輪翻頁', '在候選窗上滾動滑鼠滾輪時切換候選頁。'),
 'enhanced_position': ('候選窗位置微調', '啟用小狼毫的位置調整方式，改善候選窗與輸入位置的對齊；不同應用程式效果可能不同。'),
 'align_type': ('數字與文字的垂直對齊', 'top 靠上、center 置中、bottom 靠下。'),
 'margin_x': ('左右內邊距', '候選文字與視窗左右邊緣之間的空間。'),
 'margin_y': ('上下內邊距', '候選文字與視窗上下邊緣之間的空間。'),
 'spacing': ('編碼與候選的間距', '候選窗內的未完成編碼列與候選列表之間的距離；編碼顯示在應用程式內時不會顯示這段間距。'),
 'candidate_spacing': ('候選之間的距離', '直排時是列間距；橫排時是相鄰候選之間的空間。'),
 'hilite_spacing': ('選字數字與文字的距離', '調整候選前方數字和候選正文之間的空間。'),
 'hilite_padding': ('反白區塊內邊距', '選取背景超出文字邊緣的留白。'),
 'border_width': ('視窗邊框粗細', '0 表示不畫外框；數值越大邊框越粗。'),
 'corner_radius': ('候選視窗圓角', '候選窗外框的圓角半徑；0 為直角。'),
 'round_corner': ('選中候選圓角', '選中候選反白區塊的圓角半徑，和整個視窗的外框圓角分開設定。'),
 'shadow_radius': ('視窗陰影範圍', '0 表示不畫陰影。預覽以簡化陰影示意，Windows 的模糊效果可能不同。'),
 'shadow_offset_x': ('陰影左右偏移', '正值往右、負值往左。'),
 'shadow_offset_y': ('陰影上下偏移', '正值往下、負值往上。'),
 'min_width': ('視窗最小寬度', '即使候選很短，視窗仍維持至少這個寬度。'),
 'max_width': ('候選換行寬度', '橫排時超過此寬度便換行，形成多行候選區塊；420 可作起點，0 表示不限制而維持單行。依螢幕 DPI 縮放。每頁候選數不變，不支援移至下一行才展開的捲軸模式。'),
 'min_height': ('視窗最小高度', '即使候選很少，視窗仍維持至少這個高度。'),
 'max_height': ('視窗最大高度', '0 表示不限制；超過時的實際排列仍以小狼毫為準。'),
 'linespacing': ('字體行高比例', '相對於字級的百分比；0 使用字體預設行高。'),
 'baseline': ('文字基線比例', '相對於字級的基線調整；0 使用預設值。屬細部字型排版選項。'),
 'color_format': ('色碼排列格式', '指定色碼內的透明度與紅綠藍順序；預覽支援 abgr、argb、rgba。'),
 'name': ('顯示名稱', '供選單或主題清單辨識的名稱；不是程式內部識別碼。'),
 'author': ('作者資訊', '記錄原作者與來源，不影響候選輸入效果。'),
 'menu': ('候選選單', '候選頁大小與選字相關設定。'),
 'page_size': ('每頁候選數', '一頁顯示幾個候選。此工具限制為 5～9 個，兼顧閱讀與翻頁。'),
 'switches': ('預設輸入狀態', '控制中文／英文、繁簡、全半形和 Emoji 等模式；選「沿用狀態」表示不強制重設。'),
 'switcher': ('方案與功能選單', '控制切換方案時的選單與快捷鍵。'),
 'hotkeys': ('開啟方案選單的快捷鍵', '例如 F4、Control+grave。鍵名保留原文供 Rime 辨識。'),
 'caption': ('選單標題', '切換輸入方案時顯示的標題。'),
 'fold_options': ('收合功能選項', '將選單中的模式切換選項收合顯示。'),
 'abbreviate_options': ('縮短功能選項名稱', '使用較短的模式名稱，讓選單較精簡。'),
 'option_list_separator': ('選項分隔符號', '模式選項之間顯示的分隔文字。'),
 'save_options': ('記住哪些模式狀態', '列出的模式在切換方案或重新啟動後可保留上次狀態；清單內的名稱是 Rime 識別碼。'),
 'schema_list': ('可切換的輸入方案', '清單中的 schema 是方案識別碼；刪除會使該方案不再出現在選單。'),
 'ascii_composer': ('中英切換按鍵', '設定單按 Shift、Ctrl、Caps Lock 的反應；不影響按住 Shift 輸入大寫字母。'),
 'switch_key': ('各切換按鍵的動作', 'commit_text 上屏候選、commit_code 上屏原始編碼、clear 清除編碼、inline_ascii 暫時英文、noop 不切換。'),
 'good_old_caps_lock': ('傳統 Caps Lock 大寫鎖定', '讓 Caps Lock 保持一般大寫鎖定習慣；也需配合 Caps_Lock 對應動作。'),
 'Shift_L': ('左 Shift', '單按左 Shift 時執行的中英切換動作。'), 'Shift_R': ('右 Shift', '單按右 Shift 時執行的中英切換動作。'),
 'Control_L': ('左 Ctrl', '單按左 Ctrl 時執行的切換動作；noop 表示不切換。'), 'Control_R': ('右 Ctrl', '單按右 Ctrl 時執行的切換動作；noop 表示不切換。'),
 'Caps_Lock': ('Caps Lock 大寫鎖定鍵', '大寫鎖定鍵的切換動作。'),
 'key_binder': ('快捷鍵與翻頁', '設定按鍵組合對應的動作。'),
 'bindings': ('按鍵對應表', 'accept 是按下的鍵、send 是送出的鍵、toggle 是切換模式、when 是生效時機。'),
 'editor': ('輸入編輯按鍵', '控制 Enter、Space、Backspace、Delete 等按鍵在組字時的反應。'),
 'navigator': ('組字游標移動', '控制游標在尚未上屏的文字之間移動。'),
 'translator': ('主要中文候選引擎', '把拼音轉成中文候選，並套用個人學習詞頻。'),
 'melt_eng': ('英文候選', '讓中文模式中也能出現英文單字候選。'),
 'cn_en': ('中英文混合詞', '例如 X 光、科技產品名稱等混合詞的候選來源。'),
 'custom_phrase': ('個人捷徑詞', '以指定捷徑輸出完整文字；通常不會自動學習詞頻。'),
 'dictionary': ('使用的內建詞庫', '詞庫的內部名稱，不含 .dict.yaml 副檔名；需有對應檔案才能部署。'),
 'user_dict': ('個人詞庫名稱', '記錄學習詞頻或個人捷徑的資料名稱；任意改名可能使原學習資料暫時無法使用。'),
 'db_class': ('詞庫儲存類型', 'stabledb 是文字捷徑表；userdb 是可學習詞頻的資料庫。這是引擎識別碼，請保留原文。'),
 'enable_user_dict': ('學習個人詞頻', '記住常用詞與自己組合的詞句，之後逐漸調整排序。'),
 'enable_sentence': ('自動組成長句', '找不到完整詞時，允許組合多個詞形成句子。'),
 'enable_word_completion': ('中文詞語補全', '尚未完整輸入拼音時，也提供較長的完整詞。'),
 'enable_completion': ('候選補全', '未打完輸入碼時提供補全候選；英文或捷徑是否適用取決於對應引擎。'),
 'initial_quality': ('候選來源優先度', '調整這一來源與其他來源之間的排序比重；不是單一詞的使用次數。'),
 'spelling_hints': ('拼音提示長度', '在一定長度內顯示候選的拼音提示；0 表示不顯示。'),
 'always_show_comments': ('持續顯示候選註解', '控制候選提示是否一直顯示。'),
 'comment_format': ('註解文字處理規則', '以規則改寫或隱藏候選旁的註解；xform 表示替換文字，請保留規則語法。'),
 'preedit_format': ('組字編碼顯示規則', '把雙拼碼顯示為較容易辨識的拼音；只影響組字顯示，不會直接更改雙拼鍵位。'),
 'prism': ('拼音索引名稱', 'Rime 編譯雙拼拼寫規則所使用的索引名稱。進階選項，建議保留。'),
 'speller': ('拼音與雙拼輸入規則', '控制允許的字母、分隔符號及拼寫轉換。'),
 'alphabet': ('允許輸入的字元', '可進入拼音組字的字母與符號；順序可能影響索引，請謹慎調整。'),
 'initials': ('可作為起始的字元', '允許從哪些字母開始一段組字。'),
 'delimiter': ('音節分隔符號', '例如空格或單引號；用來分隔不同拼音音節。'),
 'algebra': ('拼寫轉換規則', 'xform 改寫編碼，derive 增加可用拼法，erase 排除拼法，xlit 替換字元；修改可能改變小鶴鍵位。'),
 'engine': ('輸入法處理流程', '依序處理按鍵、切分輸入、產生候選並過濾候選。'),
 'processors': ('按鍵處理模組', '清單順序決定按鍵由誰先處理；模組名稱為程式識別碼，不能直接翻譯後儲存。'),
 'segmentors': ('輸入切分模組', '判斷哪些文字是拼音、網址、符號或反查碼。'),
 'translators': ('候選產生模組', '決定中文、英文、日期、數字、反查等候選來源；名稱保留供引擎辨識。'),
 'filters': ('候選處理模組', '依序進行繁簡轉換、Emoji、排序、反查提示與去重複。改順序可能改變結果。'),
 'recognizer': ('輸入類型辨識', '判斷目前輸入屬於網址、Email、數字或工具呼叫碼。'),
 'patterns': ('辨識規則表', '使用正規表示式辨識各類輸入；保留原規則語法，避免網址或一般拼音被錯誤攔截。'),
 'url': ('網址辨識', '讓網址可直接輸入，不被當成普通中文拼音。'),
 'email': ('電子郵件辨識', '讓 Email 地址可直接輸入。'),
 'underscore': ('底線文字辨識', '辨識含底線的英文或識別名稱。'),
 'traditionalize': ('繁簡與用語轉換', '只改字形與指定用語，或使用完整台灣用語表；可透過預覽比較設置、項目等詞。'),
 'opencc_config': ('文字轉換對照表', 'OpenCC 設定檔名稱。完整台灣用語表會把部分原詞換成其他詞；保守模式保留設置、項目。'),
 'option_name': ('控制此功能的模式名稱', '對應 switches 中的內部識別碼；這不是顯示文字，不能隨意翻譯。'),
 'tags': ('套用的輸入類型', '列出的類型才會進行此步驟處理，例如 abc 是一般拼音候選。'),
 'tag': ('輸入類型標記', '供引擎辨識這段輸入的內部名稱，請保留原文。'),
 'tips': ('轉換提示方式', '控制繁簡或反查提示；none 表示不顯示提示。'),
 'emoji': ('Emoji 表情符號', '在開啟 Emoji 模式時，把對應詞加入表情候選。'),
 'inherit_comment': ('沿用原候選註解', '轉換後的候選是否保留原本的註解。'),
 'punctuator': ('標點與符號', '控制半形、全形模式下按鍵實際輸出的標點。'),
 'half_shape': ('半形模式標點表', '一般中文輸入時各符號鍵的輸出；中文逗號、句號也在這裡設定。'),
 'full_shape': ('全形模式標點表', '切到全形模式後各符號鍵的輸出。'),
 'digit_separators': ('數字內可保留的分隔符號', '例如小數點或時間冒號，避免數字中的符號被不必要地轉成中文標點。'),
 'symbols': ('特殊符號捷徑表', '呼叫碼對應一組符號候選；代碼需保留原樣才能使用。'),
 'date_translator': ('日期、時間與星期', '設定呼叫日期與時間候選的輸入碼；預覽會顯示呼叫方式與格式。'),
 'date': ('日期呼叫碼', '輸入這個字母組合後出現日期候選。'),
 'dateen': ('英文日期呼叫碼', '輸入後出現英文日期候選。'),
 'datezh': ('中文日期呼叫碼', '輸入後出現中文年月日。'),
 'datetime': ('日期加時間呼叫碼', '輸入後出現日期與時間候選。'),
 'time': ('時間呼叫碼', '輸入後出現時、分、秒等時間候選。'),
 'timestamp': ('時間戳記呼叫碼', '輸入後出現 Unix 時間戳記，常用於程式與資料處理。'),
 'week': ('星期呼叫碼', '輸入後出現星期幾的候選。'),
 'lunar': ('農曆呼叫碼', '呼叫上游成熟的農曆功能；日期結果由 Rime 農曆模組計算。'),
 'lunar_template': ('農曆文字格式', '花括號內是農曆模組的占位符，請保留名稱；可調整前後文字。'),
 'gregorian_to_lunar': ('西曆轉農曆辨識', '供農曆模組辨識日期輸入的規則。'),
 'number': ('數字轉中文辨識', '辨識金額或中文數字工具的輸入格式。'),
 'unicode': ('Unicode 字元反查', '以 Unicode 編碼找字；unicode 是模組識別名稱。'),
 'calculator': ('計算機輸入辨識', '辨識以工具前綴開始的算式。'),
 'radical_lookup': ('拆字查字', '由部件或拆字輸入找字，屬於反查工具。'),
 'radical_reverse_lookup': ('拆字結果拼音提示', '為拆字查到的字顯示拼音提示。'),
 'prefix': ('呼叫前綴', '在工具輸入前加上的字元，例如反查開頭的前綴。'),
 'search': ('反查呼叫鍵', '進入查字／反查的前綴或按鍵；原始鍵名須保持有效。'),
 'select_first_character': ('取候選詞第一個字', '以指定按鍵選取候選詞的第一個字。'),
 'select_last_character': ('取候選詞最後一個字', '以指定按鍵選取候選詞的最後一個字。'),
 'import_preset': ('沿用哪個預設表', '引用其他配置中的同類規則；名稱需有對應的上游設定。'),
 'pin_cand_filter': ('固定優先候選', '指定某個輸入碼優先出現哪些文字；不等於刪除其他候選。'),
 'reduce_english_filter': ('降低英文干擾', '避免短英文單字壓過常用中文候選。'),
 'words': ('要處理的詞表', '此模組使用的詞條清單；具體作用取決於上層模組。'),
 'mode': ('模組運作方式', '此值是上層模組的模式識別碼；保留原文以免改變含義，請參考該模組文件。'),
 'idx': ('候選位置索引', '模組用來指定候選位置的數值；屬進階排序設定。'),
 'app_options': ('各應用程式個別設定', '以執行檔名稱指定特例，例如 Firefox 的組字顯示方式。'),
 'accept': ('按下的按鍵', '使用 Rime 鍵名，如 Control+Shift+4。'),
 'send': ('改送出的按鍵', '將原按鍵改送為指定按鍵，如 Page_Down。'),
 'when': ('生效時機', 'always 隨時；composing 組字中；has_menu 有候選選單；paging 已翻頁。'),
 'toggle': ('切換的模式', '切換指定的 Rime 模式，識別碼需保留。'),
 'reset': ('重新進入時的預設值', '0 使用第一個狀態，1 使用第二個狀態；移除此欄表示沿用原狀態。'),
 'states': ('模式的顯示名稱', '依序為關閉和開啟時顯示的文字。'),
 'schema': ('方案識別碼', '對應 .schema.yaml 的內部名稱；不是顯示名稱。'),
 'commit': ('直接輸出的文字', '按下此符號鍵後，直接上屏這段文字。'),
 'pair': ('成對輸出的符號', '例如左右引號；兩個符號輪流出現。'),
 'ascii_mode': ('英文直接輸入', '開啟後直接輸出英文字元；關閉後使用中文組字。'),
 'ascii_punct': ('英文標點', '開啟時使用英文標點；關閉時使用中文標點對照。'),
 'traditionalization': ('繁體輸出', '開啟使用目前的繁體轉換；關閉輸出簡體。'),
}

COLOR_PARTS = {'back': '背景', 'text': '編碼文字', 'candidate_text': '候選文字',
 'candidate_back': '候選背景', 'candidate_shadow': '候選陰影', 'comment_text': '註解文字',
 'label': '選字數字', 'border': '視窗邊框', 'shadow': '視窗陰影',
 'hilited_text': '選中編碼文字', 'hilited_back': '選中編碼背景', 'hilited_shadow': '選中編碼陰影',
 'hilited_candidate_text': '選中候選文字', 'hilited_candidate_back': '選中候選背景',
 'hilited_candidate_border': '選中候選邊框', 'hilited_candidate_shadow': '選中候選陰影',
 'hilited_comment_text': '選中候選註解', 'hilited_label': '選中候選數字',
 'hilited_candidate_label': '選中候選數字', 'hilited_mark': '選中標記'}
KEYS = {'BackSpace':'退格鍵', 'Delete':'刪除鍵', 'Escape':'取消鍵', 'Return':'Enter 鍵', 'space':'空白鍵',
 'Left':'左方向鍵','Right':'右方向鍵','Control+BackSpace':'Ctrl＋退格鍵','Control+Delete':'Ctrl＋刪除鍵',
 'Control+Return':'Ctrl＋Enter 組合鍵','Control+Shift+Return':'Ctrl＋Shift＋Enter 組合鍵','Shift+Left':'Shift＋左方向鍵','Shift+Right':'Shift＋右方向鍵'}

def info(path, value=None):
    key = path.rsplit('/',1)[-1]
    if path.startswith('switches/') and key=='name':
        return '模式識別碼', '例如 traditionalization 表示繁體模式；這是內部名稱，請保留原文。'
    if 'punctuator/' in path and len(key)<=1:
        return '符號鍵「'+key+'」', '設定按下這個符號鍵後，輸出的文字、成對符號或候選清單。'
    if key in HELP:
        return HELP[key]
    if key.endswith('_color') and key[:-6] in COLOR_PARTS:
        label = COLOR_PARTS[key[:-6]] + '顏色'
        return label, label + '。色碼由小狼毫以 BGR／ABGR 解讀，可用選色器調整，不必手算色碼。'
    if key in KEYS:
        return KEYS[key], '控制這個按鍵在組字時的動作；動作識別碼會保留原文，旁邊附中文說明。'
    if key.startswith('algebra_'):
        plan = {'common':'共用','pinyin':'全拼','rime_ice':'雾凇全拼','double_pinyin':'自然碼雙拼',
                'double_pinyin_flypy':'小鶴雙拼','double_pinyin_abc':'智能 ABC 雙拼', 'double_pinyin_mspy':'微軟雙拼',
                'double_pinyin_sogou':'搜狗雙拼', 'double_pinyin_ziguang':'紫光雙拼', 'double_pinyin_jiajia':'拼音加加雙拼'}.get(key[8:],key[8:])
        return plan+'拼寫規則', '這是一組可供引用的拼寫規則；列在這裡不代表已啟用此雙拼方案。'
    if path.startswith('preset_color_schemes/') and path.count('/') == 1:
        return '配色主題：'+str(value.get('name',key) if isinstance(value,dict) else key), '主題識別碼為 '+key+'。名稱屬於原主題作者命名；預覽可查看它的實際顏色。'
    if key.endswith('.exe'):
        return '應用程式：'+key, '這是 Windows 執行檔名稱，必須保留原文才能辨識對應程式。'
    if re.fullmatch(r'V[A-Za-z0-9]+',key):
        return '符號捷徑：'+key, '在中文模式輸入 '+key+' 可叫出這一組符號；這是輸入碼，保留原文。'
    if key in ('punct','number','unicode'):
        return HELP[key] if key in HELP else ('標點辨識','辨識標點工具的輸入格式。')
    return '進階設定：'+key, '原始識別碼：'+key+'。目前沒有可靠的中文對照；保留原名供查閱，建議維持原值。'

VALUES = {'commit_text':'上屏候選後切換', 'commit_code':'上屏編碼後切換', 'clear':'清除編碼後切換',
 'inline_ascii':'暫時英文', 'noop':'不切換', 'revert':'退回上一段組字', 'back_syllable':'刪除上一個音節',
 'delete_candidate':'刪除使用者候選記憶', 'commit_script_text':'上屏編碼文字', 'commit_comment':'上屏候選註解',
 'delete':'刪除', 'cancel':'取消組字', 'commit_raw_input':'上屏原始輸入', 'confirm':'選取候選',
 'default':'系統預設', 'center':'置中', 'top':'靠上', 'bottom':'靠下', 'none':'不啟用',
 'composition':'顯示組字編碼', 'preview':'顯示預計上屏文字', 'preview_all':'顯示完整上屏預覽',
 'cleartype':'次像素平滑', 'grayscale':'灰階平滑', 'aliased':'不平滑', 'hilite':'跟隨滑鼠反白', 'semi_light':'輕度指向提示'}
MODULES={'ascii_composer':'中英切換','recognizer':'輸入類型辨識','key_binder':'快捷鍵','speller':'拼音組字','punctuator':'標點處理',
 'selector':'候選選取','navigator':'組字游標移動','express_editor':'組字編輯','ascii_segmentor':'英文切分','matcher':'特殊輸入辨識',
 'abc_segmentor':'拼音切分','punct_segmentor':'標點切分','fallback_segmentor':'其他文字切分','punct_translator':'標點候選',
 'script_translator':'中文詞語與組句','table_translator':'字碼對照候選','uniquifier':'移除重複候選',
 'melt_eng':'英文單字','custom_phrase':'個人捷徑','cn_en':'中英混輸','radical_lookup':'拆字查字','radical_pinyin':'拆字拼音',
 'date_translator':'日期與時間','lunar':'農曆','number_translator':'中文數字與金額','unicode':'Unicode 查字',
 'calc_translator':'計算機','force_gc':'Lua 記憶體回收','corrector':'拼音糾錯提示','autocap_filter':'英文大小寫',
 'pin_cand_filter':'固定優先候選','reduce_english_filter':'降低英文干擾','traditionalize':'繁簡轉換','emoji':'Emoji 候選',
 'search':'查字搜尋','select_character':'詞中取字','radical_reverse_lookup':'拆字拼音提示','flypy_vocabulary_filter':'個人詞彙調整'}

def shown_value(value):
    if value is True: return '開啟'
    if value is False: return '關閉'
    if isinstance(value,(dict,list)): return f'{len(value)} 個項目（展開編輯）'
    if isinstance(value,str) and value in VALUES: return VALUES[value]+'（'+value+'）'
    if isinstance(value,str):
        tail=value.rsplit('@',1)[-1].lstrip('*')
        if tail in MODULES:return MODULES[tail]+'（'+value+'）'
    return str(value)

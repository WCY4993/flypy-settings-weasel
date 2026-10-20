-- Local, exact-spelling learning. This is an Apple-inspired policy, not Apple's engine.
local M = {}
local states = {}
local glyph = require('flypy_number_style')
-- CRT file IO may use the Windows ANSI codepage, while Rime paths are UTF-8.
-- Try UTF-8 first (UTF-8-aware hosts), then a per-machine path prepared by the app.
function M.open(env,name,mode)
  local f,err=io.open(rime_api.get_user_data_dir()..'/'..name,mode)
  if f then return f end
  for _,key in ipairs({'flypy_learning/io_path_utf8_hex','flypy_learning/io_path_hex'}) do
    local hex=env.engine.schema.config:get_string(key) or ''
    if #hex>0 and #hex%2==0 and not hex:find('[^0-9a-fA-F]') then
      local path=hex:gsub('..',function(pair) return string.char(tonumber(pair,16)) end)
      f,err=io.open(path..'/'..name,mode)
      if f then return f end
    end
  end
  return nil,err
end
local function clean(code) return code:gsub("[' ]", "") end
local finals = {iu='q',ei='w',uan='r',ue='t',ve='t',un='y',uo='o',ie='p',ong='s',iong='s',ai='d',en='f',eng='g',ang='h',an='j',ing='k',uai='k',iang='l',uang='l',ou='z',ia='x',ua='x',ao='c',ui='v',['in']='b',iao='n',ian='m'}
local function encode(pinyin)
  local out = ''
  for p in pinyin:gmatch('%a+') do
    if p:match('^[aoe]') then
      out = out .. (#p == 2 and p or p:sub(1,1) .. (finals[p] or p))
    else
      local i = p:sub(1,2)
      if i ~= 'zh' and i ~= 'ch' and i ~= 'sh' then i = p:sub(1,1) end
      local f = p:sub(#i+1)
      out = out .. (({zh='v',ch='i',sh='u'})[i] or i) .. (finals[f] or f)
    end
  end
  return out
end
local function han(text)
  local n = 0
  for _, c in utf8.codes(text) do
    if not ((c >= 0x3400 and c <= 0x9fff) or (c >= 0x20000 and c <= 0x323af)) then return nil end
    n = n + 1
  end
  return n
end
local function bucket(env, mode, code)
  local key = mode .. ':' .. code
  env.words[key] = env.words[key] or {}
  return env.words[key]
end
local function remember(env, mode, code, text, count, manual)
  bucket(env,mode,code)[text] = {count=count, manual=manual}
end
function M.init(env)
  env.personal = {}
  env.glyph_env = {}; glyph.init(env.glyph_env)
  env.path = rime_api.get_user_data_dir() .. '/flypy_learning.tsv'
  env.state = states[env.path]
  local fresh = not env.state
  if fresh then env.state = {words={},clock=0}; states[env.path]=env.state end
  env.words = env.state.words
  if not env.state.tw_exact then
    env.state.tw_exact = {}
    local dictionary = M.open(env,'flypy_taiwan.dict.yaml','r')
    if dictionary then
      for line in dictionary:lines() do
        local text = line:match('^([^#\t]+)\t')
        if text then env.state.tw_exact[text] = true end
      end
      dictionary:close()
    end
  end
  env.to_s = Opencc('t2s.json')
  env.max_length = math.max(1, math.min(128, env.engine.schema.config:get_int('flypy_learning/max_word_length') or 12))
  local file = fresh and M.open(env,'flypy_learning.tsv','r')
  if file then
    for line in file:lines() do
      local mode,code,text,count,manual = line:match('^([ts])\t([a-z]+)\t([^\t]+)\t(%d+)\t(%d+)$')
      if code then
        count, manual = tonumber(count), tonumber(manual)
        remember(env,mode,code,text,count,manual)
        env.state.clock = math.max(env.state.clock,manual)
      end
    end
    file:close()
  end
  file = M.open(env,'flypy_personal.dict.yaml','r')
  if file then
    for line in file:lines() do
      local text,py = line:match('^([^#\t]+)\t([a-z ]+)\t')
      if text then
        if glyph.exact(text) ~= text then text = glyph.normalize(text,env.glyph_env) end
        local code = encode(py)
        env.personal[code] = env.personal[code] or {}
        env.personal[code][text] = true
      end
    end
    file:close()
  end
  env.selection = env.engine.context.select_notifier:connect(function(ctx)
    local seg = ctx.composition:back()
    if seg and seg.selected_index > 0 then env.manual = true end
  end)
  env.update = env.engine.context.update_notifier:connect(function(ctx)
    if ctx.input == '' then env.manual = false;env.default_input=nil;env.default_text=nil end
  end)
  env.connection = env.engine.context.commit_notifier:connect(function(ctx)
    local code, text = clean(ctx.input), ctx:get_commit_text()
    local n = han(text)
    -- A committed, punctuation-free 1..N-character composition; no dictionary whitelist.
    if not n or n < 1 or n > env.max_length or not code:match('^[a-z]+$') or #code ~= 2*n then return end
    local mode = ctx:get_option('traditionalization') and 't' or 's'
    local old = bucket(env,mode,code)[text] or {count=0,manual=0}
    local manual = old.manual
    local seg = ctx.composition:back()
    if env.manual or (seg and seg.selected_index > 0) or (env.default_input==ctx.input and env.default_text and env.default_text~=text) then
      env.state.clock=env.state.clock+1; manual=env.state.clock
    end
    env.manual = false
    local count = old.count + 1
    local f = M.open(env,'flypy_learning.tsv','a')
    if f then
      local ok = f:write(mode,'\t',code,'\t',text,'\t',count,'\t',manual,'\n')
      f:close()
      if ok then remember(env,mode,code,text,count,manual) end
    end
  end)
end
function M.fini(env)
  if env.connection then env.connection:disconnect() end
  if env.selection then env.selection:disconnect() end
  if env.update then env.update:disconnect() end
end
function M.func(input, env)
  local ctx = env.engine.context
  local segment = ctx.composition:back()
  local start = segment and segment.start or 0
  local mode = ctx:get_option('traditionalization') and 't' or 's'
  -- Candidate ranges use raw byte offsets, including explicit syllable separators.
  local code, ends = '', {}
  for offset=start+1,#ctx.input do
    local ch=ctx.input:sub(offset,offset)
    if ch:match('[a-z]') then code=code..ch;ends[#code]=offset
    elseif (ch=="'" or ch==' ') and #code>0 then ends[#code]=offset end
  end
  local words=env.words[mode..':'..code] or {}
  local rows, seen = {}, {}
  local function normalize(c)
    local text=c.text
    if mode=='s' then text=env.to_s:convert(text)
    else
      local genuine=c:get_genuine()
      if genuine and env.state.tw_exact[genuine.text] then text=genuine.text end
    end
    if text~=c.text then c=ShadowCandidate(c,c.type,text,c.comment) end
    return c
  end
  local function add(c, personal)
    c=normalize(c)
    local id=c.start..':'..c._end..':'..c.text
    if seen[id] then
      if personal then seen[id].personal=math.max(seen[id].personal or 0,personal) end
      return
    end
    local full=c.start==start and c._end==#ctx.input
    local record=full and words[c.text] or nil
    local row={c=c,rank=#rows+1,manual=record and record.manual or 0,count=record and record.count or 0,full=full,personal=personal}
    seen[id]=row;rows[#rows+1]=row
  end
  local preedit=''
  local function flush()
    for length=#code,2,-1 do
      local prefix=code:sub(1,length)
      local memory=env.words[mode..':'..prefix] or {}
      local personal=env.personal[prefix] or {}
      local ordered={}
      for text in pairs(memory) do ordered[#ordered+1]=text end
      for text in pairs(personal) do if not memory[text] then ordered[#ordered+1]=text end end
      table.sort(ordered)
      for _,text in ipairs(ordered) do
        local c=Candidate('flypy_exact',start,ends[length],text,'')
        -- An empty preedit lets the engine render the remaining segment correctly.
        if length==#code then c.preedit=preedit end
        add(c,personal[text] and 2 or 1)
      end
    end
    local latest=0
    for _,r in ipairs(rows) do latest=math.max(latest,r.manual) end
    table.sort(rows,function(a,b)
      local ap,bp=latest>0 and a.manual==latest,latest>0 and b.manual==latest
      if ap~=bp then return ap end
      if a.count~=b.count then return a.count>b.count end
      if a.full~=b.full then return a.full end
      return a.rank<b.rank
    end)
    if start==0 and env.default_input~=ctx.input then
      env.default_input=ctx.input;env.default_text=rows[1] and rows[1].c.text or nil
    end
    -- Keep two personal partials within reach without displacing the best full words.
    local partials,promoted={},{}
    for _,r in ipairs(rows) do
      if r.personal and not r.full then partials[#partials+1]=r end
    end
    table.sort(partials,function(a,b)
      if a.personal~=b.personal then return a.personal>b.personal end
      return a.rank<b.rank
    end)
    for i=1,math.min(2,#partials) do promoted[i]=partials[i] end
    for _,r in ipairs(promoted) do
      for i,item in ipairs(rows) do
        if item==r and i>3+#promoted then
          table.remove(rows,i);table.insert(rows,math.min(4+#promoted-1,#rows+1),r);break
        end
      end
    end
    for _,r in ipairs(rows) do yield(r.c) end
  end
  local n=0
  for c in input:iter() do
    n=n+1
    if n==1 then preedit=c.preedit end
    if n<=256 then add(c)
    else
      if n==257 then flush() end
      c=normalize(c)
      local id=c.start..':'..c._end..':'..c.text
      if not seen[id] then yield(c) end
    end
  end
  if n<=256 then flush() end
end
return M

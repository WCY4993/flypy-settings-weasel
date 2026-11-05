-- Persistent, exact-display candidate hiding using the app's vocabulary rules.
local M = {}
local states = {}
local learning = require('flypy_learning')
local filename = 'flypy_vocabulary_rules.tsv'
local function mark_hidden(state, text, hidden)
  state.hidden[text] = hidden or nil
  local first = text:sub(1, (utf8.offset(text, 2) or (#text+1))-1)
  if hidden then
    state.by_first[first] = state.by_first[first] or {}
    state.by_first[first][text] = true
  elseif state.by_first[first] then
    state.by_first[first][text] = nil
    if next(state.by_first[first]) == nil then state.by_first[first] = nil end
  end
end
local function init(env)
  local root = rime_api.get_user_data_dir()
  local state = states[root]
  if not state then
    state = {hidden={}, overrides={}, undo={}}
    states[root] = state
  end
  -- Reconcile on session/schema initialization so restoring rules in the app takes effect.
  local current = {}
  local f = learning.open(env, filename, 'rb')
  if f then
    for line in f:lines() do
      local original, text, mode, alias, tw = line:gsub('\r$', ''):match('^([^\t]+)\t([^\t]*)\t([^\t]+)\t([^\t]*)\t(.*)$')
      if original then current[original] = {text=text, mode=mode, tw=tw} end
    end
    f:close()
  end
  state.hidden = {}
  state.by_first = {}
  for text in pairs(state.overrides) do
    if not current[text] then current[text] = {text='', mode='normal', tw=''} end
  end
  state.has_pin = false
  for text, value in pairs(current) do
    state.overrides[text] = value
    if value.mode == 'hide' then mark_hidden(state, text, true) end
    if value.mode == 'pin' then state.has_pin = true end
  end
  env.state = state
  env.enabled = env.engine.schema.config:get_bool('flypy_quick_remove/enabled') ~= false
  env.restore_on_commit = env.engine.schema.config:get_bool('flypy_quick_remove/restore_on_commit') ~= false
end
local function append(env, line)
  -- Open only on a removal/undo command, never while ordinary keys are processed.
  local f = learning.open(env, filename, 'ab')
  if not f then return false end
  f:setvbuf('no')
  local ok = f:write('\n' .. line .. '\n')
  local closed = f:close()
  return ok ~= nil and closed ~= nil
end
local function rule(line)
  local _, text, mode, _, tw = line:match('^([^\t]+)\t([^\t]*)\t([^\t]+)\t([^\t]*)\t(.*)$')
  return {text=text or '', mode=mode or 'normal', tw=tw or ''}
end
local function previous_rule(env, text)
  local previous
  local f = learning.open(env, filename, 'rb')
  if f then
    for line in f:lines() do
      if line:match('^([^\t]+)\t') == text then previous = line:gsub('\r$', '') end
    end
    f:close()
  end
  return previous or text .. '\t\tnormal\t' .. text .. '\t'
end
local function refresh(ctx, prompt)
  ctx:refresh_non_confirmed_composition()
  local seg = ctx.composition:back()
  if seg then seg.selected_index = 0; seg.prompt = prompt end
end
function M.func(key, env)
  if key.keycode ~= 0xffff then return 2 end
  if key:release() then env.held = false; return 2 end
  if not key:ctrl() or key:alt() or key:super() then return 2 end
  local ctx = env.engine.context
  if not env.enabled or ctx:get_option('ascii_mode') or not ctx:is_composing() then return 2 end
  if not key:shift() and not ctx:has_menu() then return 2 end
  if env.held then return 1 end
  env.held = true
  if key:shift() then
    local entry = env.state.undo[#env.state.undo]
    if not entry then refresh(ctx, '沒有可復原的快捷移除'); return 1 end
    if previous_rule(env, entry.text) ~= entry.text .. '\t\thide\t' .. entry.text .. '\t' then
      env.state.undo[#env.state.undo] = nil
      refresh(ctx, '此詞規則已由其他操作修改，請在詞彙表管理'); return 1
    end
    if not append(env, entry.previous) then
      refresh(ctx, '復原未儲存，請檢查資料夾寫入權限'); return 1
    end
    env.state.undo[#env.state.undo] = nil
    mark_hidden(env.state, entry.text, false)
    env.state.overrides[entry.text] = rule(entry.previous)
    env.state.has_pin = false
    for _, value in pairs(env.state.overrides) do
      if value.mode == 'pin' then env.state.has_pin = true; break end
    end
    refresh(ctx, '已復原「' .. entry.text .. '」')
    return 1
  end
  local cand = ctx:get_selected_candidate()
  if not cand or cand.text == '' or cand.text:find('[\t\r\n%z]') then return 2 end
  local text = cand.text
  local previous = previous_rule(env, text)
  if not append(env, text .. '\t\thide\t' .. text .. '\t') then
    refresh(ctx, '移除未儲存，請檢查資料夾寫入權限'); return 1
  end
  mark_hidden(env.state, text, true)
  env.suffix = ''; env.last_commit = nil
  env.state.overrides[text] = {text='', mode='hide', tw=''}
  env.state.undo[#env.state.undo+1] = {text=text, previous=previous}
  refresh(ctx, '已隱藏「' .. text .. '」；Ctrl+Shift+Delete 復原')
  return 1
end
function M.init(env)
  init(env)
  env.commit = env.engine.context.commit_notifier:connect(function(ctx)
    if not env.restore_on_commit or next(env.state.hidden) == nil then
      env.suffix = ''; env.last_commit = nil; return
    end
    local text = ctx:get_commit_text()
    local now = os.time()
    -- Keep only a short, in-memory Chinese suffix within this input session.
    -- It permits separately committed characters to rebuild a hidden word.
    local chinese = text ~= ''
    for _, c in utf8.codes(text) do
      if not ((c >= 0x3400 and c <= 0x9fff) or (c >= 0x20000 and c <= 0x323af)) then chinese = false; break end
    end
    local previous_bytes = 0
    local joined = text
    if chinese then
      if not env.last_commit or now - env.last_commit > 10 or now < env.last_commit then env.suffix = '' end
      previous_bytes = #(env.suffix or '')
      joined = (env.suffix or '') .. text
      env.suffix = joined
      local n = utf8.len(env.suffix)
      if n > 32 then env.suffix = env.suffix:sub(utf8.offset(env.suffix, n-31)) end
      env.last_commit = now
    else
      env.suffix = ''; env.last_commit = nil
    end
    local restored = {}
    if env.state.hidden[text] then restored[text] = true end
    if chinese then
      for offset in utf8.codes(joined) do
        local first = joined:sub(offset, (utf8.offset(joined, 2, offset) or (#joined+1))-1)
        for word in pairs(env.state.by_first[first] or {}) do
          local last = offset + #word - 1
          if last > previous_bytes and joined:sub(offset, last) == word then restored[word] = true end
        end
      end
    end
    local lines = {}
    for word in pairs(restored) do lines[#lines+1] = word .. '\t\tnormal\t' .. word .. '\t' end
    if #lines == 0 then return end
    if not append(env, table.concat(lines, '\n')) then
      log.error('Flypy: could not save candidate restoration')
      return
    end
    for i=#env.state.undo,1,-1 do
      if restored[env.state.undo[i].text] then table.remove(env.state.undo,i) end
    end
    for word in pairs(restored) do
      mark_hidden(env.state, word, false)
      env.state.overrides[word] = {text='', mode='normal', tw=''}
    end
  end)
end
function M.fini(env)
  if env.commit then env.commit:disconnect() end
end
M.filter = {init=init, func=function(input, env)
  for cand in input:iter() do
    if not env.state.hidden[cand.text] then yield(cand) end
  end
end}
return M

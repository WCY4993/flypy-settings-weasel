-- Persistent, exact-display candidate hiding using the app's vocabulary rules.
local M = {}
local states = {}
local learning = require('flypy_learning')
local filename = 'flypy_vocabulary_rules.tsv'
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
  for text in pairs(state.overrides) do
    if not current[text] then current[text] = {text='', mode='normal', tw=''} end
  end
  state.has_pin = false
  for text, value in pairs(current) do
    state.overrides[text] = value
    state.hidden[text] = value.mode == 'hide' or nil
    if value.mode == 'pin' then state.has_pin = true end
  end
  env.state = state
  env.enabled = env.engine.schema.config:get_bool('flypy_quick_remove/enabled') ~= false
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
    env.state.hidden[entry.text] = nil
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
  env.state.hidden[text] = true
  env.state.overrides[text] = {text='', mode='hide', tw=''}
  env.state.undo[#env.state.undo+1] = {text=text, previous=previous}
  refresh(ctx, '已隱藏「' .. text .. '」；Ctrl+Shift+Delete 復原')
  return 1
end
M.init = init
M.filter = {init=init, func=function(input, env)
  for cand in input:iter() do
    if not env.state.hidden[cand.text] then yield(cand) end
  end
end}
return M

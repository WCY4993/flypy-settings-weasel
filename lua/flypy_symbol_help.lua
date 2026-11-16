local M = {}
local kind = 'flypy_symbol_help'
local group_property = 'flypy_symbol_help_group'
local groups = {['Va-Z'] = '字母變體', ['V0-9'] = '數字變體'}

local function is_help(code)
  return code == 'Vhelp' or code == 'Vlist'
end

local learning = require('flypy_learning')
local history_file = 'flypy_symbol_learning.tsv'
local histories = {}

local function history(env)
  local root = rime_api.get_user_data_dir()
  if histories[root] then return histories[root] end
  local state = {menus = {}, clock = 0}
  local file = learning.open(env, history_file, 'rb')
  if file then
    for line in file:lines() do
      local code, text, count, manual =
        line:match('^(V[%w%-]+)\t([^\t\r\n]+)\t(%d+)\t(%d+)$')
      if code then
        state.menus[code] = state.menus[code] or {}
        state.menus[code][text] = {count=tonumber(count), manual=tonumber(manual)}
        state.clock = math.max(state.clock, tonumber(manual))
      end
    end
    file:close()
  end
  histories[root] = state
  return state
end

local function record(env, code, text, manual)
  if text == '' or text:find('[\t\r\n%z]') then return end
  local state = history(env)
  local menu = state.menus[code] or {}
  local previous = menu[text] or {count=0, manual=0}
  if manual then state.clock = state.clock + 1 end
  local entry = {count=previous.count+1, manual=manual and state.clock or previous.manual}
  menu[text] = entry
  state.menus[code] = menu
  local file = learning.open(env, history_file, 'ab')
  if file then
    file:write(code, '\t', text, '\t', entry.count, '\t', entry.manual, '\n')
    file:close()
  end
end

local function is_symbol_code(code, config)
  return code:match('^V%w+$') and not is_help(code) and
    config:get_list('punctuator/symbols/' .. code) ~= nil
end

local function ranked(menu, candidates, iterator_state, initial)
  if not menu then
    for cand in candidates, iterator_state, initial do yield(cand) end
    return
  end
  local rows, latest = {}, 0
  for cand in candidates, iterator_state, initial do
    local score = menu[cand.text]
    local mark = score and score.manual or 0
    latest = math.max(latest, mark)
    rows[#rows+1] = {candidate=cand, order=#rows+1, count=score and score.count or 0, manual=mark}
  end
  table.sort(rows, function(a, b)
    local first_a, first_b = latest > 0 and a.manual == latest, latest > 0 and b.manual == latest
    if first_a ~= first_b then return first_a end
    if a.count ~= b.count then return a.count > b.count end
    return a.order < b.order
  end)
  for _, row in ipairs(rows) do yield(row.candidate) end
end

function M.init(env)
  local ctx = env.engine.context
  env.selection = ctx.select_notifier:connect(function(context)
    local input = context.input
    if not is_help(input) then return end
    local segment = context.composition:toSegmentation():get_at(0)
    local cand = segment and segment:get_selected_candidate()
    if not cand or cand.type ~= kind then return end
    local target = cand.text
    local current_menu = context:get_property(group_property)
    record(env, groups[current_menu] and current_menu or 'Vhelp', target, segment.selected_index > 0)
    context:clear()
    if groups[target] then
      env.group_active = true
      context:set_property(group_property, target)
      context:push_input(input)
    else
      context:push_input(target)
    end
  end)
  local config = env.engine.schema.config
  env.commit = ctx.commit_notifier:connect(function(context)
    local code = context.input
    if not is_symbol_code(code, config) then return end
    local seg = context.composition:back()
    local cand = seg and seg:get_selected_candidate()
    local text = context:get_commit_text()
    if cand and cand.text == text then
      record(env, code, text, seg.selected_index > 0)
    end
  end)
  env.update = ctx.update_notifier:connect(function(context)
    if env.group_active and not is_help(context.input) then
      env.group_active = false
      context:set_property(group_property, '')
    end
  end)
end

function M.fini(env)
  env.selection:disconnect()
  env.commit:disconnect()
  env.update:disconnect()
end

function M.func(key, env)
  if key.keycode ~= 0xff0d or key:release() or key:shift() or key:ctrl()
     or key:alt() or key:super() then return 2 end
  local ctx = env.engine.context
  if not is_help(ctx.input) then return 2 end
  local cand = ctx:get_selected_candidate()
  if not cand or cand.type ~= kind then return 2 end
  return ctx:confirm_current_selection() and 1 or 2
end

local function menu_entry(code, label, cand)
  -- Leave a trailing byte so librime keeps the composition open for the
  -- selection notifier, including when Weasel selects by candidate index.
  return Candidate(kind, cand.start, cand._end - 1, code, label)
end

local function help_candidates(input, config, group, length)
  local rows = {}
  for cand in input:iter() do
    if groups[group] then
      local keys = group == 'V0-9' and '0123456789' or
        'aAbBcCdDeEfFgGhHiIjJkKlLmMnNoOpPqQrRsStTuUvVwWxXyYzZ'
      for suffix in keys:gmatch('.') do
        local code = 'V' .. suffix
        if is_symbol_code(code, config) then
          rows[#rows+1] = menu_entry(code, groups[group], cand)
        end
      end
      break
    end
    local code, label = cand.text:match('^(V[%w%-]+)%((.+)%)$')
    if code and cand.start == 0 and cand._end == length and
       (groups[code] or is_symbol_code(code, config)) then
      rows[#rows+1] = menu_entry(code, groups[code] or label, cand)
    else
      rows[#rows+1] = cand
    end
  end
  return rows
end

M.filter = {func=function(input, env)
  local ctx = env.engine.context
  local code = ctx.input
  if code:sub(1,1) == 'V' then
    local config = env.engine.schema.config
    if is_help(code) then
      local group = ctx:get_property(group_property)
      local menu = groups[group] and group or 'Vhelp'
      local rows = help_candidates(input, config, group, #code)
      local index = 0
      ranked(history(env).menus[menu], function()
        index = index + 1
        return rows[index]
      end)
      return
    end
    if is_symbol_code(code, config) then
      ranked(history(env).menus[code], input:iter())
      return
    end
  end
  for cand in input:iter() do yield(cand) end
end}

return M

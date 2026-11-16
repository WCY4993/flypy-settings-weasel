local M = {}
local kind = 'flypy_symbol_help'
local group_property = 'flypy_symbol_help_group'
local groups = {['Va-Z'] = '字母變體', ['V0-9'] = '數字變體'}

local function is_help(code)
  return code == 'Vhelp' or code == 'Vlist'
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
    context:clear()
    if groups[target] then
      env.group_active = true
      context:set_property(group_property, target)
      context:push_input(input)
    else
      context:push_input(target)
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
  yield(Candidate(kind, cand.start, cand._end - 1, code, label))
end

M.filter = {func=function(input, env)
  local ctx = env.engine.context
  if not is_help(ctx.input) then
    for cand in input:iter() do yield(cand) end
    return
  end
  local config = env.engine.schema.config
  local group = ctx:get_property(group_property)
  if groups[group] then
    local keys = group == 'V0-9' and '0123456789' or 'aAbBcCdDeEfFgGhHiIjJkKlLmMnNoOpPqQrRsStTuUvVwWxXyYzZ'
    for cand in input:iter() do
      for suffix in keys:gmatch('.') do
        local code = 'V' .. suffix
        if config:get_list('punctuator/symbols/' .. code) then
          menu_entry(code, groups[group], cand)
        end
      end
      return
    end
    return
  end
  for cand in input:iter() do
    local code, label = cand.text:match('^(V[%w%-]+)%((.+)%)$')
    if cand.start ~= 0 or cand._end ~= #ctx.input then
      yield(cand)
    elseif code and groups[code] then
      menu_entry(code, groups[code], cand)
    elseif code and config:get_list('punctuator/symbols/' .. code) then
      menu_entry(code, label, cand)
    else
      yield(cand)
    end
  end
end}

return M

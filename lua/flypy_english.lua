-- Exact English spelling plus one case-normalized name; keep Chinese and shortcuts.
local M = {}
function M.init(env)
  local config = env.engine.schema.config
  env.original_first = config:get_bool('flypy_english/original_first') ~= false
  env.compact = not (config:get_bool('melt_eng/enable_completion') == true
      or config:get_bool('cn_en/enable_completion') == true
      or (env.engine.schema.schema_id == 'melt_eng'
          and config:get_bool('translator/enable_completion') == true))
end
function M.func(input, env)
  local code = env.engine.context.input
  local eligible = code:match('^[A-Za-z]+$')
  local folded = code:lower()
  local original, canonical = false, false
  for c in input:iter() do
    local text = c.text
    local full = eligible and c.start == 0 and c._end == #code
    local normalized = text:gsub(' ', ''):lower()
    -- Some dictionaries map several product versions to the exact same code.
    -- Completion=false alone cannot suppress these explicit dictionary entries.
    local extension = full and env.compact and normalized ~= folded
        and normalized:sub(1, #folded) == folded
    if not extension then
      if full and env.original_first and text:match('^[A-Za-z][A-Za-z ]*$')
          and normalized == folded then
        if not original then
          local literal = Candidate('flypy_english_literal', 0, #code, code, '')
          literal.preedit = c.preedit
          yield(literal); original = true
        end
        if text ~= code and (not env.compact or not canonical) then
          yield(c); canonical = true
        end
      else
        yield(c)
      end
    end
  end
end
return M

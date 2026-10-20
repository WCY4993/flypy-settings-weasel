-- Keep literal spelling alongside a fully matched English name; never promote above Chinese.
local M = {}
function M.init(env)
  env.original_first = env.engine.schema.config:get_bool('flypy_english/original_first') ~= false
end
function M.func(input, env)
  local code = env.engine.context.input
  local eligible = env.original_first and code:match('^[A-Za-z]+$')
  local original = false
  for c in input:iter() do
    local text = c.text
    if eligible and c.start==0 and c._end==#code and text:match('^[A-Za-z][A-Za-z ]*$')
        and text:gsub(' ',''):lower()==code:lower() then
      if not original then
        local literal=Candidate('flypy_english_literal',0,#code,code,'')
        literal.preedit=c.preedit
        yield(literal); original=true
      end
      if text~=code then yield(c) end
    else
      yield(c)
    end
  end
end
return M

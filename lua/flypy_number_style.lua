-- Normalize only the number translator's output; upstream Lua stays untouched.
local M = {}
local comments = {
  ["〔数字小写〕"] = "〔數字小寫〕",
  ["〔数字大写〕"] = "〔數字大寫〕",
  ["〔金额小写〕"] = "〔金額小寫〕",
  ["〔金额大写〕"] = "〔金額大寫〕",
}

function M.init(env)
  local pattern = env.engine.schema.config:get_string("recognizer/patterns/number") or "^R"
  env.prefix = pattern:sub(2, 2)
end

function M.func(input, env)
  local traditional = env.engine.context:get_option("traditionalization")
  for cand in input:iter() do
    -- Upstream number_translator uses the complete numeric input as type.
    local original_type = cand:get_genuine().type
    if env.prefix ~= "" and original_type:sub(1, 1) == env.prefix
        and original_type:sub(2, 2):match("%d") then
      local text = cand.text
      if traditional then text = text:gsub("叄", "參"):gsub("叁", "參") end
      local comment = comments[cand.comment] or cand.comment
      if text ~= cand.text or comment ~= cand.comment then
        cand = ShadowCandidate(cand, cand.type, text, comment)
      end
    end
    yield(cand)
  end
end

return M

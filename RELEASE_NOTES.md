2.2.1 修正 R＋數字候選的繁體字形與說明。

- 繁體模式的大寫「叄」改為「參」，包含整數、小數位與金額。
- 候選說明改為「數字小寫、數字大寫、金額小寫、金額大寫」；簡體輸出切換仍保留，介面說明維持繁體。
- 使用獨立 flypy_number_style.lua 候選過濾器，不修改上游 number_translator.lua；修正模組納入設定備份，更新雾凇時保留。
- 發布包包含程式、通用配置、完整原始碼、官方雾凇資料與 SHA-256；個人詞庫及捷徑保持空白。

現有本工具使用者如需保留個人資料，請先備份，再將 lua/flypy_number_style.lua 放入 Rime 的 lua 資料夾，並在自己的小鶴 engine/filters 中，把 lua_filter@*flypy_number_style 加在 simplifier@traditionalize 之後、uniquifier 之前，重新部署。不要拿整份通用 custom.yaml 蓋掉個人配置。全新安裝可直接使用 Install.ps1。

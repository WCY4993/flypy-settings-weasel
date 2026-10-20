# 台灣補充詞庫來源

資料來自 openvanilla/McBopomofo，固定 commit be6564acad6c4d3265c34a2e1a872d80f9db6068。
https://github.com/openvanilla/McBopomofo/tree/be6564acad6c4d3265c34a2e1a872d80f9db6068/Source/Data

保留 McBopomofo-MIT.txt 中的上游版權與 MIT 授權全文。上游 Data/README.md 說明 BPMFMappings.txt 最初由 BSD 授權的 libtabe tsi.src 簡化及修改而來；另附 libtabe-COPYING.txt 原始授權通知。

本工具自行將上游注音讀音對應為完整拼音，去除重複聲調，篩選純漢字，加入台灣繁體字形對應寫法，並以語料次數乘 100（上限 100,000,000）換算 Rime 詞頻。對應字形權重為原詞的 80%，不直接取代原詞；合併重複詞音時取最大權重。並未使用本機使用者字詞訓練公開詞庫。

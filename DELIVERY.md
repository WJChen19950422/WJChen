# CI76 v0.18 — R4 最新交付

請使用 `ci76-v018-delivery` 分支，下載 **R4**；執行後品牌列及視窗均應顯示 R4。
原有 main README 保留。

- **完整交付 ZIP**：[CI76_v0.18_R4_Source_and_QA.zip](delivery/CI76_v0.18_R4_Source_and_QA.zip)；點入後使用 GitHub 的 Download raw file 按鈕下載。
- [ZIP SHA-256](delivery/CI76_v0.18_R4_Source_and_QA.zip.sha256)
- [v0.18 執行與驗證方式](CI76_PC_Tool_v0_18_CONTROL_CENTER/README.md)
- [R4：使用者測試紀錄分析及修改理由](CI76_PC_Tool_v0_18_CONTROL_CENTER/qa_reports/FIELD_LATENCY_REPORT.md)
- [v0.18 變更紀錄](CI76_PC_Tool_v0_18_CONTROL_CENTER/CHANGELOG_v018.md)
- [測試輸出](CI76_PC_Tool_v0_18_CONTROL_CENTER/qa_reports/pytest.txt)
- [逐項 QA 狀態](CI76_PC_Tool_v0_18_CONTROL_CENTER/qa_reports/QA_RESULTS.md)
- [檔案修改摘要](CI76_PC_Tool_v0_18_CONTROL_CENTER/qa_reports/CHANGESET.md)
- [Linux Qt 截圖](CI76_PC_Tool_v0_18_CONTROL_CENTER/qa_captures)

也可按本分支的 **Code → Download ZIP**，下載整個分支。
`delivery` 保留先前版本；R4 是本次最新包。

ZIP 內保留原始 v0.17 與 v0.18。執行時進入
`CI76_PC_Tool_v0_18_CONTROL_CENTER`，安裝 Python 3.12 後雙擊
`START_PC_TOOL.bat`。首次啟動需要網路安裝依賴。

R4：慢 ACK 前先取得到期電流、perf_counter 量測、Qt PreciseTimer、50 ms 最新目標合併；保留 ACK／讀回、過載與原馬達安全限制。
使用者紀錄證明 prior 版本有約 57 ms 寫入 ACK 等待；R4 的改善幅度仍需實板重測，不能保證拖動期間每筆低於 50 ms。

完整套件為 180 tests、9 subtests 通過；Python compileall 通過。
MCU 韌體、UART Protocol、Checksum、Flash 與馬達安全限制未修改。
**Windows GUI／DPI 與 R4 硬體重測尚未完成。** Linux Qt 圖片不是 Windows 視覺驗收證據。

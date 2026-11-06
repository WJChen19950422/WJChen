# CI76 v0.18 交付

請使用 `ci76-v018-delivery` 分支。原有 main README 保留。

- **完整交付 ZIP**：[CI76_v0.18_CurrentOnly_Source_and_QA.zip](delivery/CI76_v0.18_CurrentOnly_Source_and_QA.zip)；點入後使用 GitHub 的 Download raw file 按鈕下載。
- [ZIP SHA-256](delivery/CI76_v0.18_CurrentOnly_Source_and_QA.zip.sha256)
- [v0.18 執行與驗證方式](CI76_PC_Tool_v0_18_CONTROL_CENTER/README.md)
- [v0.18 變更紀錄](CI76_PC_Tool_v0_18_CONTROL_CENTER/CHANGELOG_v018.md)
- [測試報告](CI76_PC_Tool_v0_18_CONTROL_CENTER/qa_reports/TEST_REPORT.md)
- [逐項 QA 狀態](CI76_PC_Tool_v0_18_CONTROL_CENTER/qa_reports/QA_RESULTS.md)
- [檔案修改摘要](CI76_PC_Tool_v0_18_CONTROL_CENTER/qa_reports/CHANGESET.md)
- [截圖資料夾](CI76_PC_Tool_v0_18_CONTROL_CENTER/qa_captures)

也可按本分支的 **Code → Download ZIP**，下載整個分支。

ZIP 內保留原始 v0.17 與 v0.18。執行時請進入
`CI76_PC_Tool_v0_18_CONTROL_CENTER`，安裝 Python 3.12 後雙擊
`START_PC_TOOL.bat`。首次啟動需要網路安裝依賴。

最新版（第二頁僅電流監控）驗證：164 tests、9 subtests 通過，Python compileall 通過。
MCU 韌體、UART Protocol、Checksum、Flash 與馬達安全限制未修改；worker 僅新增監控排程模式判定。
**Windows GUI／DPI 與 CI76 硬體尚未驗證。** 截圖是 Linux Qt 實際離屏渲染，
不是 Windows 實機驗收證據。

第二頁電流更新優化的行為與驗證限制見 [CURRENT_ONLY_REPORT](CI76_PC_Tool_v0_18_CONTROL_CENTER/qa_reports/CURRENT_ONLY_REPORT.md)。原初版 ZIP 仍保留於 delivery，請使用上述 CurrentOnly 最新版。

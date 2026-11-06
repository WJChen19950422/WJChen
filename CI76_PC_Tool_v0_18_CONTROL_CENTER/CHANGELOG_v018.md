# v0.18 — UI Refinement (2026-11-05)

- 集中 Midnight Tech Blue QSS + Fusion + QPalette，兩頁與 popup 同步；深色 Tooltip、焦點、停用狀態。
- MOTECK 純文字 fallback 與可選正式 PNG/SVG 載入；移除孤立 M 方塊。
- 緊湊品牌列／工具列／三欄表單；開始與取消學習緊接 STOP，保留 Esc 原 handler、確認與原限制。
- 第二頁整理為實際電流、限流編輯、狀態摘要三區；保留三種電流顯示模式與全域監控。
- QSettings 保存已驗證 Port、USB serial/VID/PID/HWID 與 opt-in Auto Connect；初次 OFF。
- 唯一安全配對才預選／單次自動連線；既有 worker 唯讀查 Device Code；錯誤／逾時關閉新連線；失敗不記錄、不重試、不自動寫入。
- Demo 確認／還原更新 MCU 狀態，保留第一頁整組未提交電流草稿；切頁取消未送目標。
- 失聯資料改 UNKNOWN／stale，忽略斷線後延遲樣本；未解決安全狀態時不自動還原參數。
- 新增真實 Qt 狀態與 UI 測試、worker 唯讀連線測試、Linux Qt 截圖／JSON、Windows 截圖操作工具與驗證報告。
- 調整兩項舊靜態 theme 測試：因 QSS 移至 theme.py，改檢查共用來源；非移除行為要求。
- 未修改 worker.py、protocol.py、transport.py、motion.py、monitoring.py、diagnostics.py、eventlog.py、Flash 與 firmware_review_only。
- Windows 實際 GUI／DPI 與 CI76 硬體尚未驗證；尚未達成完整 Windows 視覺驗收。

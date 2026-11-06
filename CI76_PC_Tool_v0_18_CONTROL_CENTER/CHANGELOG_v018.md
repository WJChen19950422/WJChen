# v0.18 — UI Refinement

## 初版交付 (2026-11-05)

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

## 第二頁電流更新優化 (2026-11-06)

- 依後續需求，第二頁待機的自動監控只送 0x10 電流查詢；第一頁與手動完整讀取保留。
- worker.py 的 _monitor 與 monitoring.py 的排程新增 current_only 分支；除此之外，序列埠驅動、命令編解碼、Checksum、Flash、限流讀回與馬達／學習控制流程不變。
- GUI 與 worker 共同把關：PC 控制／UART MODE／學習時回到原安全背景監控，不允許 stale UI 取消必要查詢。
- 暫停的非電流欄位顯示 UNKNOWN，不假裝維持即時正常；CSV 不重複填入舊的非電流資料。
- 單次電流逾時清空讀值，三次連續失敗才處理失聯；成功後重置計數，無自動重試連線。
- 新增排程、worker 安全覆寫、限流讀回、Qt 切頁、UNKNOWN 與逾時測試。硬體更新率與 Windows 實機驗證仍未執行。

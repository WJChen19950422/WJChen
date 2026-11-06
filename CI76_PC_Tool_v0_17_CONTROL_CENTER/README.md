# MOTECK CI76 Control Center v0.17 — LAB

Windows / Python 3.12 / PySide6 / CI76 Protocol 251110.

本版是以 `v0.16 DARK HUD LAB` 原始碼為基礎的**介面與測試流程修正版**；**不修改 STM32 韌體、UART Command、馬達控制或 Flash 儲存流程**。MOTECK 文字標誌以應用程式文字排版呈現，UI 所用青綠色是此 LAB 版的介面配色，不宣稱為官方 Logo／識別規範。

## v0.17 重點

- **整套深色 UI**：上方 MOTECK / CI76 品牌列、深色連線區與工作列、深色分頁／參數卡片／錯誤旗標。第一頁保留原本的三欄參數／監控架構與操作流程。
- **第二頁 GPU Monitoring 風格**：左右雙儀表分別顯示 `UART 0x10` 實際馬達電流與 `0x06 / 0x19` 設定／回讀限流值。每個儀表採**左側指針、右側大字**，另保留電流橫條與限流滑桿。
- **取消額外的 >2 A 勾選／確認流程**。Demo 操作範圍仍為 0–8 A，且**不得高於 MCU 的過載門檻**。設定必須以 `0x19` 讀回成功才算生效；不保證硬體對任意電流、負載或 Duty 都安全。
- **移除儀表本身的 Qt Tooltip**，避免滑鼠停留時遮住指針的黑色橫框；一般設定欄位的說明 Tooltip 保留並採深色樣式。
- **兩頁限流行為仍然獨立**：第一頁編輯後才按「寫入（暫存）」；第二頁拖動滑桿時約每 250ms 合併最新目標再傳送，且兩頁僅以 MCU 成功讀回的值確認硬體狀態。
- **保留**：單一自動監控開關、50–1500ms 輪詢、.config、行程學習按鈕、錯誤旗標、MotorCNT 歸零、故障統計、PC Log、客戶診斷，以及第一頁舊版韌體的短時 UART 控制測試功能。

## Windows 執行方式

解壓縮後雙擊 `START_PC_TOOL.bat`，或在資料夾 PowerShell 執行：

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe main.py
```

## 版面自動擷取

可在 Windows 已安裝套件的環境執行：

```powershell
.\.venv\Scripts\python.exe tools\layout_smoke.py
```

輸出 `CI76_v0_17_page1.png`、`CI76_v0_17_page2.png`，可檢查兩頁在預設 1260×840 視窗下的顯示（也能將視窗最大化）。

## 測試狀態

已執行無設備的 Python 單元／靜態檢查；**此環境無法安裝或執行 PySide6 GUI，也未連接 CI76**，因此 Windows 視覺、UART 實測、拖動滑桿的真實時延與 UI 滑順度需要在實機上驗證。若 GUI 有截斷或顏色不一致，請附 `layout_smoke.py` 生成的兩張截圖。

## 重要安全限制

- 設定的 **限流上限不是命令馬達固定輸出安培數**，也不是實測推力；不應以手或身體阻擋推桿感受力道。
- 使用者已表示新版韌體支援 0A，但本包不含新版 MCU 原始碼，0A 生效仍須 `0x19` 讀回並實板確認。
- **移除確認勾選不等於電路安全額定提升到 8A**；需配合既有過載門檻、馬達額定、供電與散熱測試。第一頁仍須由操作人員審核參數。
- CI76 之前的 `FW 0x0B01` 缺少已驗證的 UART 失聯停止機制；PC Tool 的 2 秒限時不是硬體保護。第一頁伸縮／學習功能只能在具有獨立馬達斷電手段的內部測試台上執行，不可將 I1 當成緊急停止。
- 之前的 `ctl.c` 存在 Hall/POT 無回授仍可能假學習成功問題，**本版未修正韌體**；請參考 `LEARNING_REPAIR_GUIDE.md`，量產前應完成修改與實板驗證。

詳見 `CHANGELOG_v017.md`。前一版的說明留在 `README_HISTORY_v016.md`。

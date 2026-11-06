# MOTECK CI76 Control Center v0.18 — LAB R4

Windows 10/11 · Python 3.12 · PySide6 6.7+ · pyserial 3.5+ · Protocol 251110

v0.18 是以隨附 v0.17 原始碼漸進修改的 UI 版本。原始 v0.17 資料夾完整保留。
MCU 韌體、UART Protocol、Checksum、封包、Flash 與既有馬達安全限制未修改。
電流更新優化版調整 worker 的監控排程及限流交易間的電流讀取；不改 UART 編碼、限流讀回與馬達安全限制。

## 執行

解壓縮完整資料夾後雙擊 `START_PC_TOOL.bat`。或在本資料夾 PowerShell 執行：

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe main.py
```

## 使用方式與 v0.18 行為

- 兩頁使用統一 Midnight Tech Blue 主題。Qt Fusion、完整深色 Palette、非原生 COM popup，降低 Windows 淺色控制項洩漏。深色訊息框、Tooltip、鍵盤焦點及停用狀態共用主題。
- MOTECK 使用文字標誌；沒有假造 Logo。正式資產的安裝方式見 `assets/README.md`。
- 第一頁：UART MODE、速度、伸出、縮回、STOP（Esc）、開始學習、取消學習依序排列。安全細節保留在 Tooltip 與原本確認對話框。三欄表單在小螢幕僅局部捲動；UART Log 預設收合。
- 第二頁：左側即時電流（UART 0x10）、右側 0–8 A 限流控制、下方狀態摘要。可選 Bar + Gauge／Bar only／Gauge only。沒有額外馬達操作鍵或自動監控開關。
- 第一頁限流是本機草稿，必須確認後按「寫入（暫存）」。第二頁每 50 ms 合併最新目標，放開滑桿可立即排入最新值；一次只允許一筆限流交易，忙碌期間不累積中間值，成功讀回才確認生效。Demo 成功讀回或還原會更新兩頁的 MCU 確認狀態，保留第一頁未送出草稿；第一頁明確重新讀取才會以讀回值取代草稿。
- 切離第二頁會取消尚未送出的 Demo 目標；不會取消已在 UART 執行的交易，也不會因切頁重新寫入。
- 0 A 可選但不是緊急停止。保留 MCU 過載門檻驗證與成功讀回要求，無額外 >2 A 確認流程。
- 自動監控仍是單一全域開關，目標週期 50–1500 ms；實際刷新時間依 UART 排程與延遲顯示，非保證 ADC 取樣速率。
- **第二頁待機時僅輪詢實際電流 `0x10`**，暫停位置、馬達／UART 狀態、感測器、故障旗標與運轉時間的背景查詢。這些狀態顯示「暫停更新／UNKNOWN」，不沿用舊的綠色正常判斷。切回第一頁即恢復完整監控，等待實際回覆後更新。
- PC 馬達控制、UART MODE、學習或停止確認期間仍保留安全監控；worker 會自行檢查狀態，不能以過期 UI 要求跳過。手動讀取、連線設備驗證、限流修改時的故障／狀態檢查與 `0x19` 讀回仍執行。
- 僅電流輪詢的單次逾時立即清空電流顯示；連續三次失敗才關閉／鎖定連線，避免偶發丟包造成立即斷線。沒有新增自動重連。

## COM 記憶及 Auto Connect

`QSettings("MOTECK", "CI76ControlCenter")` 僅保存安全偏好：Auto Connect 與上次驗證成功的 Port / USB 識別資料，不保存馬達命令、參數或寫入意圖。

1. 初次啟動 **自動連線預設關閉**。掃描與勾選本身不會開啟連線。
2. 若有唯一符合的上次裝置，預先選取；優先比對 USB serial + VID/PID，否則需相同 COM 與一致描述／HWID。僅 COM 號碼不足以自動判定。
3. 啟用自動連線後，下次啟動只嘗試一次，不逐一探測其他 Port；缺少、重複、被占用均等待手動操作。
4. 開啟 COM 後，沿用 SerialWorker 唯讀 identity 查詢。Device Code 必須為 `0x0B01`；Firmware Version 不必等於 `0x0B01`。
5. 只有驗證成功才更新紀錄。錯誤設備碼或驗證逾時會關閉新連線，不寫參數、不開 UART MODE、不清故障、不學習、不控制馬達。
6. 手動斷線後不會當次自動重連。USB／監控失敗會清除失效讀值；若仍有展示修改或安全操作未解決，不會偷偷還原或重播設定，需手動重新驗證／確認停止。

可辨識狀態包含 DISCONNECTED、CONNECTING、CONNECTED—VERIFYING、CI76 VERIFIED、PORT BUSY、IDENTITY MISMATCH、TIMEOUT / REMOVED。

## 測試與 GUI 擷取

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m compileall -q .
```

實際 Windows 螢幕先設定指定解析度與縮放，再執行：

```powershell
.\.venv\Scripts\python.exe tools\layout_smoke.py --screen 1920x1080 --scale 125
.\.venv\Scripts\python.exe tools\layout_smoke.py --screen 1366x768 --scale 100
.\.venv\Scripts\python.exe tools\layout_smoke.py --screen 1280x800 --scale 100
```

工具使用暫存偏好並停用自動連線，不開 UART；擷取兩頁、含明確標示的合成 COM 選單、Tooltip 及 JSON 測量。Windows 下會核對實際解析度／device pixel ratio，不符則拒絕當成該條件的截圖。

目前交付的 `qa_captures/Linux_OFFSCREEN_*` 是實際 Linux Qt 離屏截圖；縮放由 Qt 模擬。**不是 Windows 實機驗收證據**。Windows 兩頁／解析度／DPI、真實 COM hover 與 Tooltip、CI76 硬體通訊皆尚未驗證。完整紀錄見 `qa_reports/TEST_REPORT.md`、`QA_RESULTS.md`。

## 保留的安全限制

- FW 0x0B01 未證實 MCU UART 失聯自停；原有 PC 端最長 2 秒限制不等同硬體保護。I1、0 A、Esc 均不能取代獨立硬體馬達斷電。
- 學習是會移動馬達的操作，仍需原有確認與安全治具。未以自動測試觸發實體動作。
- 限流不是固定輸出電流、實測推力或 RPM；不應以身體阻擋推桿測試。
- 「寫入（暫存）」及讀回成功不代表 Flash 斷電保存已驗證。
- Hall/POT 無回授仍可能假學習成功是 MCU 問題，本版未修正；`firmware_review_only` 僅供參考，未修改或建置。

變更摘要見 `CHANGELOG_v018.md` 與 `qa_reports/CHANGESET.md`。

## 第二頁更新速度驗證

下載最新版電流優化交付包後，確認「自動監控」勾選、週期選 50 ms、第二頁顯示「僅更新實際電流」。在未啟用 UART MODE／PC 控制／學習時，短暫勾選「記錄輪詢封包」，UART TX 應僅有查詢 0x10（沒有手動讀取或限流修改時）。確認後關閉封包紀錄，觀察「電流實際刷新」的毫秒值。

舊版穿插其他查詢約每秒 4 次；移除它們能減少長回覆造成的停頓，但不保證 MCU 取樣率或實際更新速度提升幾倍。量測／硬體基準尚未執行；詳見 `qa_reports/CURRENT_ONLY_REPORT.md`。

## 滑桿連續監控優化版

- 畫面立即顯示滑桿目標；50 ms 是合併檢查週期，不是 MCU 已套用的保證速率。
- 限流寫入期間，由同一 worker 在完整 UART 請求的間隙穿插電流查詢；仍依序等待每筆 ACK，沒有同時發送多筆 UART 要求。
- 切頁、關閉自動監控或修改週期，會更新 worker 的監控偏好；不會在背景自行重連或重播待寫目標。
- 每次限流操作保留 Device Code、故障／馬達狀態、原電流參數、寫入 ACK 與讀回；移除原本未參與限流判斷的韌體版本重讀。
- UART 紀錄新增 DEMO TIMING，列出每個限流請求耗時及總耗時，可協助找出 MCU 回覆慢的命令。
- 限流是最大允許電流，並非實際電流／推力的線性控制。

模擬與測試詳見 `qa_reports/RESPONSIVE_TUNING_REPORT.md`；Windows／MCU 實測仍待完成。

## R4：實測紀錄導向的慢寫入前預讀

請確認視窗與品牌列顯示 `R4`。根據使用者紀錄，電流查詢回覆約 13–14 ms，
0x06 ACK 約 57 ms；部分 100 ms 停頓含慢寫入前已消耗的 31 ms。R4 在預計
跨過監控期限的慢寫入前先讀電流；以最後一次 ACK 耗時更新預估，剛取得
樣本時不重複讀。採 perf_counter 量測與 Qt PreciseTimer，保留單一 UART owner。

分析與限制見 `qa_reports/FIELD_LATENCY_REPORT.md`。R4 尚待 Windows／CI76 重測；
單筆 ACK 本身 57 ms 時，PC 無法保證寫入期間每筆電流都在 50 ms 內更新。

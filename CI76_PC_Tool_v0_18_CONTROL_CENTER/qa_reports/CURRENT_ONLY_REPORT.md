# 第二頁僅電流監控 — 2026-11-06 (Asia/Taipei)

## 要求與實作

使用者在初版交付後要求：第二頁先只回傳電流，降低更新等待。
此需求取代初版規格的第二頁待機背景查詢策略。PC 改成只發既有的 0x10
讀取要求，不需修改 MCU 韌體、UART Protocol、Checksum、單位或 Flash。

- `main.py`：第二頁且未進入 PC 馬達控制、UART MODE、學習、STOP 等待或安全 interlock 時，開啟 current_only；第一頁保留原完整監控。
- `monitoring.py`：只有 auto + fast_demo + current_only 同時成立才回傳 `[0x10]`。手動 Read Status 仍查完整資料。
- `worker.py`：只在 `_monitor` 排程選擇與回報加入此模式；以 worker 自身 motion / bench / learning / urgent queue 狀態再次把關。控制／學習時使用原安全監控，不讓過期 UI 狀態關閉必要查詢。
- 裝置驗證、限流操作時的 0x12/0x17 檢查及 0x19 讀回完全保留。只有使用者主動修改限流才會發送原本的參數寫入。
- 非電流的即時狀態在專用模式標示 PAUSED / UNKNOWN，清掉 CSV 中過期的非電流樣本；切回完整排程後只在實際成功讀取時恢復資料。
- 單次電流逾時立即清空顯示，連續三次失敗才執行原有安全斷線／鎖定處理。成功樣本重置次數。未新增背景連線重試。

## 檢查結果

修改前：145 passed, 9 subtests passed in 22.21s。
修改後完整套件：**164 passed, 9 subtests passed in 42.86s**，exit 0。

```
QT_QPA_PLATFORM=offscreen /workspace/ci76-venv/bin/python -m pytest -q
/workspace/ci76-venv/bin/python -m compileall -q .
```

完整輸出見 `pytest.txt` 與 `compileall.txt`。新增 19 個測試案例在
`tests/test_v018_current_only.py`：單一命令排程、手動／第一頁不受影響、worker
真正呼叫清單與零寫入、安全狀態覆寫、限流驗證與讀回、Qt 切頁與 UNKNOWN、
單次／連續逾時及恢復。既有 STOP、學習與 2 秒限制回歸測試全部通過。

開發過程的安全測試最初使用 UART MODE OFF 的假設備；原有 worker 正確觸發
自動 STOP，使後續輪詢回到 idle。測試治具改成 UART MODE ON，以驗證持續控制
時仍保留背景查詢；既有自動 STOP 行為未改動。

## 排程流量比較（非硬體速度量測）

相同 10 秒的名目 50 ms 時間點，共 200 次 scheduler 呼叫：

| 查詢 | 原先第二頁排程 | 僅電流排程 |
|---|---:|---:|
| 0x10 電流 | 200 | 200 |
| 0x11 位置 | 10 | 0 |
| 0x12 馬達狀態 | 10 | 0 |
| 0x13 系統／感測器 | 7 | 0 |
| 0x14 運轉時間 | 6 | 0 |
| 0x17 故障 | 7 | 0 |
| 合計 | 240 | 200 |

查詢總數少約 16.7%。本結果只證明排程不再插入其他讀取，**不是**實測更新率
提升 16.7%，也不代表可提升幾倍。原先每次額外查詢的 MCU 回覆延遲與逾時會
拖長電流更新間隔；移除它們主要減少這種停頓。MCU 電流取樣／發布速度、USB
UART 延遲與 Qt 週期仍限制實際刷新。

## 截圖與硬體限制

三個尺寸的 Linux Qt 截圖已重新產生；1920/125 兩頁皆無捲動，1366/100、
1280/100 的第二頁亦無捲動。Windows 實機 GUI／DPI 及 CI76 刷新率仍未驗證。
`integrity.json` 明確區分未改動模組與本次修改的 monitoring.py/worker.py。
MCU/firmware_review_only、protocol.py、transport.py 與 motion.py 保持原始位元組。

## 使用者實機驗證

1. 在新版開啟正確 COM，驗證 CI76 後讀取參數。
2. 保持 UART MODE OFF，沒有 PC 動作或學習；打開全域自動監控，週期選 50 ms，進入第二頁。
3. 確認底部顯示僅更新電流，其他狀態 PAUSED / UNKNOWN。
4. 短暫開「記錄輪詢封包」，未操作滑桿或手動讀取時，TX 只應出現 0x10 查詢。
5. 關閉封包紀錄，比較相同設定下的實際刷新 ms；封包紀錄本身可能增加 GUI 負擔。
6. 切回第一頁，確認完整監控恢復。故障欄位在重新讀回之前維持未知。

請提供觀察到的刷新 ms 與短段 UART Log；若仍慢，下一步應量測 MCU 回覆延遲，
而非直接縮短逾時或修改 checksum／通訊安全規則。

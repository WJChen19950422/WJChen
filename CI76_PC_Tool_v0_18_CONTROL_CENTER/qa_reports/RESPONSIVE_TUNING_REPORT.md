# 滑桿連續監控優化 — 2026-11-06 (Asia/Taipei)

## 原因與變更

使用者回報：第二頁只保留電流輪詢後，快速拖動仍看到約 250 ms 更新。
確認原本的 `demo_limit` 是一整筆前景工作：停止一般監控計時器，連續完成
7 個 UART 請求才恢復監控；因此 current-only 待機排程沒有解除寫入中的停頓。

本次調整：

- main.py：250 ms 合併改為 50 ms；滑桿畫面立即更新，sliderReleased 可 flush 最新值；仍只允許一筆 in-flight，另保留一個最新 pending 值，中間目標不排成長佇列。
- worker.py：在限流每個完整 UART 要求之間呼叫 _demo_checkpoint，優先服務 STOP、原有 deadline／heartbeat，再依全域週期穿插實際電流讀取。單一 worker、同時最多一筆 UART request。
- auto monitor OFF、離開第二頁、週期及 trace 偏好以新的完整 dict snapshot 傳入 worker；不在 Qt UI thread 做 UART I/O。退出第二頁仍取消未送目標，已送目標仍等待讀回。
- 保留 Device Code 0x71、故障 0x17、馬達狀態 0x12、原始電流 0x19、寫入 0x06 ACK、確認 0x19，以及過載門檻／還原機制。移除原本每次重讀卻未參與判斷的 Firmware Version 0x70；連線 identity 查詢仍讀韌體版號。
- inline 電流樣本不代表整筆限流工作結束；使用 monitor_inline 完成事件，不能扣除 pending 或重啟前景操作。維持 CSV 的成功樣本記錄。
- 每次成功限流操作新增 DEMO TIMING，包含各必要 UART 請求耗時和整筆耗時。

未修改 MCU 韌體、protocol.py、transport.py、Checksum、封包、Flash、motion.py
或 learning 的控制方法。worker.py 的調整範圍是監控與 Demo 限流排程。

## 模擬（不是硬體量測）

`responsive_simulation.json` 使用原已交付 commit 78b25ad 與目前 worker，將每筆
MCU 請求／回覆固定模擬為 20 ms，選 50 ms 監控週期：

| 項目 | 先前版本 | 本次版本 |
|---|---:|---:|
| 限流工作中的電流樣本時點 | 無 | 20、80、140、200 ms |
| 模擬中的相鄰電流樣本間距 | 寫入中暫停 | 60 ms |
| 限流工作總時間 | 140 ms | 200 ms |
| 同時 UART 請求數上限 | 1 | 1 |

穿插監控增加了必要的查詢時間，因此這個模擬中的**整筆設定完成更晚**，但
監控不必等到整筆完成才更新。50 ms 合併週期也減少了原本最多 250 ms 的
待送等待；它不代表 MCU 每秒一定套用 20 個限流目標。

單次 MCU 回覆若耗時 100 ms，就無法用 PC 排程保證每 50 ms 都有新樣本。
本次沒有縮短驗證逾時、取消 ACK 或讀回，也沒有同時發送兩個串列命令。
實際馬達電流受負載、速度與控制器影響，限流滑桿不是等比例的推力／電流命令。

## 測試與驗證

修改前完整套件：164 passed, 9 subtests passed in 49.85s。
修改後完整套件：**176 passed, 9 subtests passed in 56.12s**，exit 0；
編譯檢查 exit 0，詳見 `pytest.txt` 與 `compileall.txt`。
新增 12 個案例在 `tests/test_v018_responsive_tuning.py`：

- 模擬慢回覆下，在確認寫入前就收到多筆 current sample。
- 相鄰樣本間隔、每筆請求耗時紀錄、同時串列請求永遠只有一筆。
- 自動監控關閉、切離第二頁、交易中關閉監控、較慢使用者週期皆受尊重。
- 過載拒絕、錯誤讀回拒絕、保留還原快照；STOP 在下一筆參數寫入前處理。
- inline 更新不得結束 foreground／pending；滑桿放開送最新值、不重複排隊。
- GUI 偏好更新會傳給 worker。

既有兩頁草稿、0–8 A、學習、STOP/Esc、2 秒限制、設備驗證、自動連線與
current-only 安全背景排程回歸測試仍全部執行。

指令：

```
QT_QPA_PLATFORM=offscreen /workspace/ci76-venv/bin/python -m pytest -q
/workspace/ci76-venv/bin/python -m compileall -q .
```

Linux Qt 三尺寸截圖已重新產生並檢視第二頁：1920/125 兩頁無捲動，1366/100、
1280/100 第二頁無捲動，第一頁保留原局部捲動。Windows GUI／DPI 及 CI76
硬體速度仍未驗證，不能以模擬數字宣稱實機已達 60 ms。

## 建議的實板比較

使用最新 Responsive ZIP，勾選自動監控，週期 50 ms，關閉輪詢封包紀錄。
先不拉動觀察 current refresh ms，再連續拖動並觀察同一欄位；確認仍有樣本。
讀取 UART Log 中 DEMO TIMING（可從 Log 資料夾取得），提供幾筆各命令耗時。
這可以區分 MCU 0x71/0x17/0x19 回覆、寫入 ACK、讀回等待或 PC 顯示負擔，
避免把整筆設定耗時直接當成 UART baud rate 限制。

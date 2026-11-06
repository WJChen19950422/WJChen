# v0.11 變更摘要

- 新增 `current_limits.py`：第一頁／Demo 共用滑桿範圍 0～8 A。
- `main.py`：第二頁雙向綁定滑桿、數值框與第一頁限流欄位；250ms 節流自動寫入；顯示 MCU 讀回值；>2A 需確認。
- `lab_features.py`：改為允許 0～8 A，保留原本其它電流設定，阻止超過過載門檻的 Demo 寫入。
- `worker.py`：Demo 只要求 CI76 Device Code `0x0B01`，不再固定 FW version；高電流寫入須帶許可旗標。仍以 MCU ACK/讀回作判定。
- `protocol.py`：依使用者新版 FW 聲明，`current_limit` 最小值改成 0 A。
- 其它 UI 頁籤、馬達控制計時及 MCU 韌體未變。

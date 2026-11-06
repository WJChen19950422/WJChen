# CI76 自動學習「未接 Hall / POT 也顯示完成」的原因（2026-11-04 韌體）

檢查來源：`2026110405 LAC2_TEST.zip` 內 `LAC2_TEST/Core/Src/ctl.c`、`Core/Inc/ics.h`。

## 確認的程式路徑

1. `op.sensormode` 決定 `op.sen_hall` / `op.sen_pot`，但這是**模式設定**，不是實體回授在線驗證。Hall 模式 GPIO PC6/PC7 上拉，不代表有收過有效轉換。
2. `limit_reached()` 觀察 `m->pos` 是否變化；在 `ln.still_delta_ms >= 500` 時即回傳 `1`，即使無有效 Hall 脈衝、POT 電壓沒有變化。因此「感測器未接」被當成「到達行程極限」。
3. `learnHandler()` 的 `LEARN_BACK_OFF` 會在 `LEARN_BACK_MAX_MS` 到期後進入下一階段，即使回授位移 `moved` 未達到 `back_target_cnt`。
4. `LEARN_WAIT_AFTER_SLOW` 的最後 `learnstep == 2` 分支直接呼叫 `pos_soft()`，將 `testmode=3`、`pos.need_learn=0`、清除 `ERR_POS_FEEDBACK`，沒有先確認 `ln.pos_max-ln.pos_min` 是否為有效且足夠的行程。
5. `pos_memory()` 在下一次上電會檢查 `hardstroke < 50`，但這個條件**並未阻止本次學習當下顯示成功**。

## 建議修改原則（尚未修改韌體）

- **啟動前**：分辨 Hall/POT「已選擇」與「回授有效」。在學習運動期間一定要看到合理的 Hall 合法轉移／POT ADC 位移，不要使用靜止電平當感測器有效的證據。
- **每段找端點**：當靜止 500 ms 且本段有過足夠可信的位移時，才可考慮宣告到達端點。若超時且無位移，應轉入 `ERR_LEARN_FAIL` 與 `ERR_POS_FEEDBACK`，並停止 PWM。
- **退開階段**：`LEARN_BACK_MAX_MS` 到期但 `moved < back_target_cnt` 應視為失敗，不能當成成功退出端點。
- **提交結果前**：檢查有效行程 `abs(ln.pos_max-ln.pos_min)`，依 Hall 與 POT 實際刻度設定最小行程門檻；也要驗證上下端點順序、第二次下端點重複性。**先驗證，再清除 `pos.need_learn`/故障**。
- **出錯動作**：停止馬達輸出、保留 `pos.need_learn=1`、設定故障旗標、阻止位置模式；不應寫入無效的行程到 Flash。
- **驗證**：至少測試未接 Hall、拔掉單一 Hall 線、POT 開路／短路、正常 Hall/POT、行程中途掉訊號、碰端點、低電壓等情境。

> 注意：本專案壓縮檔中的 PC Tool v0.15 僅針對 GUI 更新，沒有把任何未驗證的韌體補丁燒入 MCU。PC Tool 本身目前只能取得百分比及錯誤旗標；不能可靠推斷 Hall A/B 是否實際有脈衝，不能將 MCU 的 `0x20` 清除當成有效學習的證明。

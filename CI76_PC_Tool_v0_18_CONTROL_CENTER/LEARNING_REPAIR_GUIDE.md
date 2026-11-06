# CI76 假學習成功：韌體修正、影響與測試計畫

> 依據：`2026110405 LAC2_TEST.zip` 的 `Core/Src/ctl.c` / `Core/Inc/ctl.h` / `Core/Inc/ics.h`。
> 這份說明針對 **2026-11-04 上傳版**，不是尚未提供的後續韌體版本。
> `firmware_review_only/ctl.c`、`ctl_learn_guard_review.patch` 是 **待審查參考修改**；沒有經過 MDK-ARM 編譯，也未經實體馬達或機構測試，請不要直接替換量產版本。

## 1. 為何會無 Hall/POT 學習完成？

1. `op.sensormode` 只是選擇 Hall / POT 的位置來源，**不是**檢查回授真的存在。Hall PC6/PC7 設定上拉時，即使沒有接線，GPIO 仍會讀到固定電平。
2. `limit_reached()` 只用 `m->pos` 是否連續約 500 ms 幾乎不變判斷端點，甚至在沒有明確電流峰值時也會回傳端點；拔掉感測器的「沒有位移」被誤當成到達端點。
3. `learnHandler()` 的 `LEARN_BACK_OFF` 用 `LEARN_BACK_MAX_MS=500` 作為超時。現有條件是「位移達標 **或** 超時」就進入下一步，這是邏輯漏洞。
4. `LEARN_WAIT_AFTER_SLOW` 中 `ln.learnstep==2` 直接 `pos_soft()`、切 `testmode=3`、`pos.need_learn=0`，並清 `ERR_POS_FEEDBACK`，**沒有**對 `ln.pos_min/max` 做最終驗證。
5. `pos_memory()` 的 `hardstroke < 50` 檢查是在下一次上電恢復學習資料時執行，不能阻止本次學習假成功。

## 2. 建議的漸進修正順序

### 修正 A：退開階段超時不能當作成功（立即修正）

檔案：`Core/Src/ctl.c` → `learnHandler()` → `case LEARN_BACK_OFF:`

原來是：

```c
if ((moved < back_target_cnt) &&
    ((now - phase_start_time) < LEARN_BACK_MAX_MS))
{
    return;
}
// 不管達標或超時，繼續下一階段
```

應改為：

```c
if (moved < back_target_cnt)
{
    if ((now - phase_start_time) < LEARN_BACK_MAX_MS)
        return;

    ln.error = 1;             // 位移未達標，學習失敗
    m->speCmd = 0;
    m->pwmReq = 0;
    m->pwm_x1024 = 0;
    learn_phase = LEARN_FAST_TO_LIMIT;
    last_step = 0xFF;         // 下次啟動學習重新初始化階段
    return;
}
// 只有真實位移達標才能走到下一階段
```

**注意**：`LEARN_BACK_COUNT_HALL=80`、`LEARN_BACK_COUNT_POT=20`，而 `LEARN_BACK_MAX_MS=500`。此處一改成超時即失敗，較慢推桿可能在 500 ms 走不到 80 Hall Count。**務必先實測正常推桿的退開耗時，再訂定每一類產品的合理上限；不可直接把 500 ms 當成量產允收時間。** 退開時應同時監控過流與限位，不能靠延長時間無限制運轉。

### 修正 B：失敗時停止、保留需學習狀態

檔案：`ctl.c` 主控制流程 `if (ln.error)` 的分支。

增加：

```c
pos.need_learn = 1;
sys.errBit0 |= ERR_POS_FEEDBACK;
m1.motor_en = 0;
m1.speCmd = 0;
m1.pwmReq = 0;
m1.pwm_x1024 = 0;
// 原本流程保留 ERR_LEARN_FAIL (0x40)
```

重新開始學習時，應在真正開始新交易的路徑 `ln.error=0`，並清理本次學習的階段狀態。**重新學習之前須排除原因；已存在的 ERR_LEARN_FAIL 可能擋住新學習，需依產品定義完成故障清除程序，不可隨意跳過故障檢查。**

### 修正 C：完成前的三道驗證

檔案：`learnHandler()` 的 `LEARN_WAIT_AFTER_SLOW` 分支。

1. **有效總行程：** 當 `ln.learnstep==1` 取得上端點時，驗證 `(ln.pos_max-ln.pos_min) >= MIN_STROKE_COUNTS`（本參考補丁暫沿用 `pos_memory()` 的 50 Count，但應依每款推桿 Hall 脈波數/POT ADC 刻度個別校正）。
2. **方向一致：** 舊程式的 `pos_soft()` 假設上端點位置大於下端點，若接反或 Hall 方向相反應拒絕成功並排查，而不是用 `abs()` 掩蓋方向反了。
3. **第二次下端點的重複性：** `ln.learnstep==2` 的位置必須在第一次下端點允許差距內，然後才能 `pos_soft()`、`testmode=3`、清 `ERR_POS_FEEDBACK`。參考補丁暫以 `max(20 Count, 總行程 5%)`，這只是設計初值，需依感測器分辨率/實際機構再定規格。

參考程式位於 `firmware_review_only/ctl_learn_guard_review.patch`。

## 3. 量產前還應增加的回授有效性判斷

以上參考補丁是 **防止最明顯假成功的最小安全修正**，不代表能可靠判別所有 Hall/POT 故障：

- **雙 Hall：** 只有 `00→01→11→10→00` 或反向合法的正交跳變，才能當作有效運動，需計算合法脈波數、非法跳變數及相鄰邊緣合理時間。只看 GPIO 固定高/低不算有效回授；應在「馬達確定要求運動」時追蹤限時無合法脈波，判定缺相/斷線。靜止或已到端點的無脈波不應單獨判故障，需要結合階段與端點條件。
- **POT：** 增加 ADC 合理電壓範圍、開路/短路、持續飽和、變化方向及連續性檢查，並確認濾波值相對於 ADC 雜訊具有可辨識的真實位移。漂浮的 POT ADC 可能產生雜訊，不能只靠 `abs(m->pos - start_pos)` 判定有效。
- **找端點過程：** 增加每個階段的最大允許時間、電流堵轉/機械端點輔助條件、反向退開後可回靠等聯合判斷。限位判斷不能只有「位置 500ms 不變」。開始時剛好在端點是重要例外，需靠後退運動與二次確認處理。
- **Flash 儲存：** 必須在全部檢查成功後才允許儲存本次有效行程；錯誤的上下限不得被存入。重新上電應仍顯示需學習。

## 4. 實測順序與預期結果

在測試台使用獨立馬達斷電、電流限制及可觀察的機械行程。不要用 I1 或拔 UART 當成緊急停止。**不要在手持馬達、可夾人的推桿、未知行程負載環境執行自動學習。**

| 編號 | 測試條件 | 預期行為 | 核對項目 |
|---|---|---|---|
| T01 | Hall 模式，不接 HA/HB，馬達可轉 | 學習失敗，不進位置模式 | 0x17 有 0x20/0x40；PWM 停止；未寫無效行程 |
| T02 | Hall 模式，只接 Hall A，不接 B | 學習失敗或明確缺相 | 合法正交跳變不足，不能假成功 |
| T03 | Hall 模式，A/B 接反或相位異常 | 方向錯誤或非法跳變應阻止提交 | 上下端點方向、錯誤旗標 |
| T04 | POT 模式，訊號開路、接 GND、接 VCC | 不得學習成功 | ADC 無效範圍/飽和，故障旗標 |
| T05 | 正常 Hall 推桿，起點在行程中間 | 學習完成、位置 0～100% 合理 | 完整行程及端點差 |
| T06 | 正常 Hall 推桿，起點就在下端點 | 可先退開後正確完成，不能誤失敗 | Back-off 時間/位移 |
| T07 | 正常 POT 推桿，起點在行程中間 | 學習完成並有可重複端點 | POT ADC 範圍/行程 |
| T08 | 學習途中斷開 Hall/POT | 停止、報錯、保持需學習 | 失去回授到輸出關閉的時間 |
| T09 | 正常推桿但運動很慢 | 不應因未調整的 500ms back-off 超時誤判 | 實際退開所需時間；調整門檻 |
| T10 | 學習中電源低壓或電流保護動作 | 停止且禁止提交有效行程 | `0x17`、PWM、斷電重啟 |
| T11 | 任一失敗後重上電 | 不可恢復錯誤學習結果 | `pos.need_learn`、`testmode`、Flash |
| T12 | 成功學習後重上電 | 有效行程可恢復，不需重學 | Flash、位置、回授 |

### 具體操作方法

1. **備份** 當前可正常工作的 Keil/MDK-ARM 專案及 `.bin`；記錄韌體版本與參數設定。
2. 將參考 `ctl.c` 與原始檔用 diff 比對，**逐行審查後**整合到你的最新分支，先編譯並檢查 warning；不要直接覆蓋量產專案。
3. 開啟 Debug/Watch 監控：`ln.learningmode`、`ln.learnstep`、`ln.error`、`ln.pos_min`、`ln.pos_max`、`m1.pos`、`m1.hall_pos`、`m1.potAvg`、`pos.need_learn`、`testmode`、`m1.speCmd`、`m1.pwmReq`、`sys.errBit0`。
4. 在實際 GPIO / ADC 上用示波器或邏輯分析儀核對 Hall A/B 合法跳變，或以萬用表/示波器核對 POT 電壓變化。**純軟體的 `m1.pos` 變化不等同於感測器確實正確接線。**
5. 先做 T01（無 Hall）和 T05（正常 Hall），分別檢查失敗與成功；再做 T02～T12，每項至少數次並保存 UART/Debug 紀錄。
6. 實際測量「無有效回授→禁止 PWM」的最長時間，並按產品機械速度/行程/限流決定 timeout、退開位移與最小行程門檻。

### PC Tool 可觀察的訊息

- `0x12`：推桿/學習狀態。即使顯示不在學習中，也不一定代表學習成功。
- `0x17`：錯誤旗標；如果同時設置 `0x20`（位置回授）與 `0x40`（學習失敗），Byte 0 理論為 `0x60`（還有其他故障時可能不同）。
- `0x11`：位置百分比；未完成學習時沒有可靠的位置物理意義。
- **建議以 Debug Watch 的 `pos.need_learn/testmode` 作最終軟體狀態判斷**；需要客戶端驗證時再增加明確的學習有效性狀態命令，而不是靠「沒有 0x20」就推定完成。

## 5. 參考補丁的驗證限制

參考補丁改善了無感測器學習假成功的主要路徑，但尚**未**加入完整的 POT 開短路/ADC 合理性、Hall 合法邊緣計數與全階段 Timeout。這些是下一輪韌體審查的必要項目。**目前尚無 MDK-ARM 編譯、MCU Flash、示波器或推桿台架驗證結果。**

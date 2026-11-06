# File-by-file changeset

Source deliverable: `CI76_PC_Tool_v0_18_CONTROL_CENTER`.
Original comparison source: separate `CI76_PC_Tool_v0_17_CONTROL_CENTER`, all 53
original archive entries verified byte-identical. Unified diffs of modified
existing files are in `qa_reports/diffs/`.

| File | Change |
|---|---|
| main.py | Apply shared theme on every entrypoint; compact brand/actions/layout; learning after STOP; safe COM preference state machine through existing worker; verified-only identity saving and write gate; mismatch/timeout close; stale readings; preserve first-page current draft on Demo readback/restore; three-zone Demo UI |
| theme.py (new) | Midnight Tech Blue tokens, complete QSS + QPalette + Fusion; explicit nonnative list popup, semantic highlight, approved asset loader / text fallback |
| settings_store.py (new) | Safe QSettings persistence and deterministic unique port matcher; no motion/parameter replay |
| monitoring.py | 後續電流更新優化：新增第二頁 current_only 排程；完整／安全監控沿用原排程 |
| worker.py | 後續電流更新優化：_monitor 選擇排程時加入權威狀態安全檢查與回報 current_only；不改讀寫編碼與馬達控制 |
| tests/test_v018_current_only.py (new) | 僅電流排程、worker 安全覆寫、寫入讀回、Qt 暫停欄位與逾時門檻測試 |
| hud_widgets.py | Consume shared colors; wrap gauge captions; empty Tooltip retained |
| tests/test_v018_ui.py (new) | Real Qt widget tests plus isolated preferences, recorded worker, fake-device worker read-only handshake, timer/cross-tab/stale-state checks |
| tests/test_v016_dark_hud.py | Theme source test follows extracted theme.py; validates removal of page-local palette |
| tests/test_v017_control_center.py | Brand/theme test inspects combined main.py/theme.py; all existing safety assertions retained |
| tools/layout_smoke.py | CLI resolution/scale/output selection; Windows actual-display check; isolated no-connect settings; real tab/popup/Tooltip PNGs and JSON; clearly tagged Linux offscreen evidence |
| README.md | v0.18 Windows setup, COM behavior, draft/confirmed semantics, captures, limitations and safety |
| CHANGELOG_v018.md (new) | Version changes and explicit Windows/hardware validation limitations |
| requirements-dev.txt (new) | Pytest tools; production requirements.txt unchanged |
| assets/README.md (new) | Approved logo asset placement and wordmark fallback policy |
| qa_captures/* (new) | Six Linux Qt tab screenshots, three popup and three Tooltip captures, three JSON reports |
| qa_reports/* (new) | Test log, compile result, layout logs, QA checklist, report, integrity hashes and diffs |

`START_PC_TOOL.bat` remains the supplied Python 3.12 launcher and is included;
no runtime dependency change was needed. It has not been executed on Windows.
`protocol.py`, `transport.py`, `motion.py`,
`diagnostics.py`, `eventlog.py`, `lab_features.py`, `config_io.py`,
`current_limits.py`, `ui_ranges.py`, all `firmware_review_only/*` are unchanged.
No UART command/checksum/Flash behavior or MCU learning source was modified.

The existing QThread is the sole serial owner. The UI adds no serial driver or
blocking serial I/O. Hardware tests and Windows captures remain unrun.

後續電流更新優化的詳細理由、限制與測試見 `CURRENT_ONLY_REPORT.md`。最終測試數量以 `pytest.txt` 為準。

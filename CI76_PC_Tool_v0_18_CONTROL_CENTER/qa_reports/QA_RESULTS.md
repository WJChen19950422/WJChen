# QA checklist results

PASS below means software/mock evidence unless explicitly stated otherwise.
No Windows or physical device acceptance is implied. `pytest.txt` is the final
suite result; test names are in `tests/test_v018_ui.py` unless noted.

| ID | Result | Evidence / remaining verification |
|---|---|---|
| A01 | PASS (Linux Qt) | Real CI76Window creation; all screenshot captures |
| A02 | PASS (mock) | auto_connect_once_read_only; real_worker_connect_identity_disconnect_are_read_only |
| A03 | PASS | preferences_default_off_and_verified_only; startup_default_and_preselect |
| A04 | PASS (mock) | QSettings round trip; verified-only update; hardware restart BLOCKED |
| A05 | PASS (mock) | missing_ambiguous; open_error_no_retry |
| A06 | PASS (mock) | identity_failure_closes_without_writes_or_saving |
| A07 | PASS (mock) | disconnect_clears_telemetry; monitor_loss; lost_link_with_modified_demo; USB hardware BLOCKED |
| A08 | PASS (mock) | manual Read All, verified connect/disconnect; real device BLOCKED |
| A09 | PASS (mock) | manual_readall_and_page1_write_require_explicit_confirmation; existing worker readback tests |
| A10 | PASS (mock) | debounce timer, in-flight coalescing, 0/8 UI edges; existing overload/readback tests |
| A11 | PASS | page1_draft_survives_demo_readback_and_restore; tab_change_cancels_unsent |
| A12 | PASS (software) | actual QTest Esc; existing tests/test_worker_motion.py and test_v08_lab.py |
| A13 | PASS (software) | button layout order; unchanged handler guards and baseline learning tests |
| A14 | PASS | protected source SHA-256 matches v0.17; integrity.json |
| A15 | BLOCKED (Windows) | Linux real captures dark and reviewed; Windows rendering not run |
| A16 | BLOCKED (Windows) | Linux popup captured/reviewed; native OS interaction not tested |
| A17 | PASS (fallback) | MOTECK text, no M icon; asset loader; official-logo DPI rendering not tested |
| A18 | PASS (Linux Qt) | layout index assertions and screenshots: STOP → Start Learning → Cancel |
| A19 | BLOCKED (Windows) | Linux 125% simulation: both tabs scroll range 0; JSON attached |
| A20 | BLOCKED (Windows) | Linux 1366×768: local content scroll 88, no horizontal scroll |
| A21 | BLOCKED (Windows) | Linux 1280×800: local content scroll 56, no horizontal scroll |
| A22 | BLOCKED (Windows) | empty gauge Tooltip tested; Linux painted meter inspected; real hover not run |
| A23 | PASS (software) | 9 actual flag labels, UNKNOWN after disconnect; decode tests |
| A24 | PASS (Linux Qt) | all_demo_view_modes_and_log_toggle; collapsed captures |
| A25 | PASS (software) | one global monitor, actual interval label retained; baseline scheduling tests |
| A26 | BLOCKED | No Windows host available; Linux_OFFSCREEN names and windows_acceptance=false |
| A27 | PASS | baseline 109+9; final regression suite all passed; pytest.txt |
| A28 | PASS | README, CHANGELOG_v018, CHANGESET, TEST_REPORT, source ZIP |

No failed test remains. BLOCKED items require actual Windows/device follow-up;
Windows visual acceptance is still outstanding. Original firmware bugs remain out
of scope and unchanged.

# v0.18 validation report — initial delivery 2026-11-05 (Asia/Taipei)

**Follow-up 2026-11-06:** Current-only tuning polling is now included.
The 145-test result below is historical; the final suite output is `pytest.txt`.
See `CURRENT_ONLY_REPORT.md` for the authorized monitoring/worker changes and final verification.

## Scope and environment

Linux x86_64 cloud container, Python 3.12.14, PySide6 6.12.0, pyserial 3.5,
pytest 9.2.0, pytest-subtests 0.15.0. Dependencies installed in
`/workspace/ci76-venv`. No physical serial port, CI76, actuator, or Windows host.
This is an implementation handoff with Windows visual acceptance still BLOCKED.
No firmware was built, flashed or modified; no physical motion test was executed.

## Baseline before edits

Working directory: `CI76_PC_Tool_v0_17_CONTROL_CENTER`.
Initial system Python lacked pytest; after installing the required environment:

```
/workspace/ci76-venv/bin/python -m pytest -q
109 passed, 9 subtests passed in 0.59s
exit 0
```

The original 53 ZIP entries still match the v0.17 folder byte-for-byte.
`integrity.json` records matching SHA-256 for the protected modules and firmware.
The original source remains in the separate v0.17 folder and the uploaded ZIP.

## Final regression gate

Working directory: `CI76_PC_Tool_v0_18_CONTROL_CENTER`.

```
QT_QPA_PLATFORM=offscreen /workspace/ci76-venv/bin/python -m pytest -q
```

Final result: **145 passed, 9 subtests passed in 25.11s**, exit 0.
Exact output is in `pytest.txt`. All tests exercise the full suite,
including existing protocol/checksum, fake-transport readback, 0/8 A bounds,
overload rejection, legacy 2-second limit, learning cancellation and STOP guards.
New tests use actual Qt widgets, isolated INI-format QSettings, and a recorded
worker; one test runs the existing SerialWorker connect/identity/disconnect path
against a fake client and asserts its complete read list and zero write list.
No physical COM is opened by the tests.

Added coverage: defaults/persistence/corrupt settings, unique USB serial matching,
COM renumbering, exact descriptor fallback, missing/duplicate/busy/removed ports,
one startup attempt, mismatch/timeout closure, no startup settings/mode/motion
writes, no reconnect after manual disconnect, manual Read All and confirmed group
write, Page 1 draft preservation after Demo readback/restore, pending target
cancellation, 250 ms timer/coalescing, in-flight target update, 0 and 8 A UI
edges, stale telemetry/nine flags, late sample rejection, modified Demo link loss,
STOP/Esc binding and learning order, theme palette, three display modes, Log
expand/collapse, wordmark fallback and empty gauge Tooltip.

Two baseline tests originally failed solely because they inspected QSS literals
inside main.py. They were updated to inspect the new shared theme.py and confirm
that page-local QSS was removed; existing behavior assertions were retained.

Compile check (exit 0):

```
/workspace/ci76-venv/bin/python -m compileall -q .
```

See `compileall.txt` for final exit status. The .bat launcher is retained unchanged;
it was inspected, not executed on Windows.

## Real Qt rendering evidence (Linux ONLY)

```
/workspace/ci76-venv/bin/python tools/layout_smoke.py --offscreen --screen 1920x1080 --scale 125
/workspace/ci76-venv/bin/python tools/layout_smoke.py --offscreen --screen 1366x768 --scale 100
/workspace/ci76-venv/bin/python tools/layout_smoke.py --offscreen --screen 1280x800 --scale 100
```

All exit 0. Actual rendered PNGs and JSON are in `qa_captures/`. Both pages at all
three sizes were inspected during development. Header/control strip stays visible;
content scrolls locally at the smaller sizes. No horizontal scrolling was observed.
Screenshots represent disconnected state; COM dropdown entries are synthetic
and explicitly labelled UI QA ONLY, with empty connection payloads.

| Requested display simulation | Logical window content (excluding OS chrome) | Page 1 vertical scroll | Page 2 vertical scroll | Horizontal |
|---|---|---:|---:|---:|
| 1920×1080 / 125% | 1536×816 | 0 | 0 | 0 |
| 1366×768 / 100% | 1366×720 | 88 | 0 | 0 |
| 1280×800 / 100% | 1280×752 | 56 | 0 | 0 |

The capture tool reserves 48 logical pixels for system/window chrome. Linux Qt
scale-factor simulation is not a measurement of Windows scaling, taskbar or
non-client area. Final captures have `windows_acceptance: false` in JSON.
The selected COM popup is electric blue with dark text. A readable dark Tooltip
was captured separately; gauge widgets have no Tooltip. First render found
scrolling at the larger size; parameter editor spacing was reduced and Demo
controls moved alongside live current, then captures were regenerated.

Offscreen plugin prints unsupported raise()/keyboard-grab notices and fontconfig
cache warning; capture files were still produced and reviewed. These warnings
further mean this cannot validate interactive Windows popup/focus/hover behavior.

## Remaining external verification — NOT RUN

- Actual Windows 10/11 UI at 1920×1080/125%, 1366×768/100%, 1280×800/100%.
- Interactive COM hover/keyboard selection, full Tooltip behavior and OS DPI logo
  scaling on Windows. No approved official logo was supplied, so fallback only.
- Connected-state Windows screenshots. No device attached; simulated tests are
  not hardware evidence.
- Physical manual connect/read all/monitor/unplug/reconnect, Auto Connect after
  restart, real 0x19 readback/latency, 0 A support and Flash power-cycle persistence.
- Any motor/learning bench test requires supervision and independent power cutoff;
  no automatic motion or learning is part of the provided screenshot tool.

Windows follow-up commands are documented in README. Do not classify the full
specification's Definition of Done or Windows visual acceptance as passed until
these screenshots and checks are actually completed. See QA_RESULTS.md for every
checklist item.

## 2026-11-06 responsive slider follow-up

Current-only idle polling alone did not resolve pauses during slider writes.
The responsive update now interleaves due telemetry between complete UART requests.
See RESPONSIVE_TUNING_REPORT.md and responsive_simulation.json. Final full-suite
counts are in pytest.txt; earlier timings/counts in this report are historical.

## R4 field-log follow-up

The user supplied UART logs identify actual long write-ACK windows. R4 adds
prewrite sampling and high-resolution timing; see FIELD_LATENCY_REPORT.md.
User logs validate the prior build behavior, not the newly changed R4 performance.
Final full-suite results are in pytest.txt.

# Paste this into Codex (start from extracted project directory)

You are implementing **CI76 PC Tool v0.18** against the provided `CI76_PC_Tool_v0_17_CONTROL_CENTER` source code. The owner has approved the **final** specification at `docs/CI76_v0.18_FINAL_SPEC.md`. Read that file **completely** before changing anything. The attached `reference/v017_page1_user_screenshot.png` is a genuine Windows screenshot of the current v0.17 first page; the current UI still appears light despite dark stylesheet declarations.

Your task is to **implement** v0.18, not to propose a new design. Locked decisions:

- Midnight Tech Blue / modern GPU-control-center style across **both** tabs.
- Remember the last successfully validated serial port; Auto Connect is optional, shown as a checkbox and **OFF by default**.
- First tab compact single-page design; only scroll when window/display scaling requires it.
- Official MOTECK logo only from an approved file in `assets/`; use a text wordmark fallback, not a fabricated logo.
- Place Start/Cancel Learning immediately after Stop (Esc) in the first-row controls; collapse safety/diagnostic copy into compact, accessible status areas.
- Strong COM popup selection highlight and accessible disabled/focus states.
- Keep original current-limits behavior: first page manual Apply, Demo page UART auto write/readback; remove >2 A special confirmation, but **keep overcurrent limits and all safety interlocks**.
- Preserve 50 ms monitoring target (not a guaranteed physical ADC rate).

## Execution order

1. Inspect `README.md`, `CHANGELOG_v017.md`, `main.py`, `worker.py`, `monitoring.py`, `current_limits.py`, `hud_widgets.py`, `dial.py`, `tools/layout_smoke.py` and existing tests.
2. Run `python -m pytest -q` on baseline. In original source it passes **109 tests + 9 subtests**. Note any environment differences.
3. Make incremental, reviewable UI and QSettings changes; avoid changing UART protocol, encoding, firmware, motor control, Flash behavior, or existing safety limits.
4. Implement isolated tests for Auto Connect selection and connection verification plus cross-tab state behavior. No actual motor control in automated tests.
5. Run full tests and `python -m compileall -q .`.
6. **On Windows**, run `tools/layout_smoke.py`, modify it if needed to capture both pages at requested viewport/scaling and visually inspect the actual PNGs. Do not claim visual verification from QSS/source inspection alone. If Windows/PySide6 unavailable, report this as a remaining QA blocker.
7. Provide edited source, `CHANGELOG_v018.md`, README updates, screenshot(s), test report, and concise notes on any remaining hardware-validation items.

## Important details

- Existing Auto Connect must use the same `SerialWorker` as manual connection. Identity read-only; Device Code `0x0B01` verifies CI76. Do not auto-connect blindly to every COM port.
- No UI startup action may write parameters, enable UART MODE, begin learning, or drive the motor.
- The known lack of MCU-side disconnect stop and the false-learning-success issue are **not** to be fixed in this UI task; keep protections and document them.
- If a logo file is missing, use the approved wordmark fallback. Don't invent a logo and don't block implementation on the asset.
- Preserve the original project in a separately named v0.17 folder so the diff is easy to review; create a v0.18 output folder.

Work through to tests and deliverables; ask for clarification only if a decision cannot be safely resolved from the approved spec.

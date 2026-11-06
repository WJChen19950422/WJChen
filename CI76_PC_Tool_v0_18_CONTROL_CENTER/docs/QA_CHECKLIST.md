# CI76 v0.18 — QA checklist

**Priority:** P0 = regression/safety blocker, P1 = visual/UX blocker, P2 = polish.

| ID | Priority | Check | Pass condition |
|---|---|---|---|
| A01 | P0 | Launch clean | Window opens; no widget exception |
| A02 | P0 | No startup writes | No setting, learning, UART MODE or motor action sent at startup |
| A03 | P0 | Auto Connect default | OFF for first launch |
| A04 | P0 | Remember port | Verified CI76 selection retained across launches |
| A05 | P0 | Missing / busy port | No hang, no serial brute-force, readable message |
| A06 | P0 | Device mismatch | Identity fails closed, controls locked |
| A07 | P0 | USB removed | Connection state stale/disconnected, values not falsely fresh |
| A08 | P0 | Manual connection | Connect, Read All, Disconnect still work |
| A09 | P0 | First tab current write | Requires button press and existing confirmations/readback |
| A10 | P0 | Demo current write | Slider debounces, writes/readbacks 0–8 A; overload protection retained |
| A11 | P0 | Cross-tab | Unsubmitted first-page draft not transmitted accidentally; no stale Demo replay |
| A12 | P0 | Stop / Esc | Existing event handler remains reachable, safety limits preserved |
| A13 | P0 | Learning | Buttons moved without changing action/guard logic |
| A14 | P0 | Protocol | No change in checksum, packet fields or MCU commands |
| A15 | P1 | Theme | Both pages dark, consistent; no white background leakage |
| A16 | P1 | COM selection | Bright selected/hover state with readable foreground |
| A17 | P1 | Brand | Official logo or readable wordmark, no fake logo |
| A18 | P1 | Control layout | Start/Cancel Learning directly after STOP (Esc) |
| A19 | P1 | 1920×1080 / 125% | First page ideally one screen; no clipping/overlap |
| A20 | P1 | 1366×768 / 100% | Local scroll allowed, actions reachable |
| A21 | P1 | 1280×800 / 100% | No hidden clickable controls |
| A22 | P1 | Gauge hover | No black rectangle over the dial |
| A23 | P1 | Fault state | Unknown never represented as healthy |
| A24 | P1 | Log panel | Collapsed by default; expand/collapse functional |
| A25 | P1 | Monitor | One global switch; actual refresh interval visible |
| A26 | P1 | Window screenshots | Two tabs/screens and DPI tested visually |
| A27 | P0 | Baseline tests | No regression from 109 tests + 9 subtests |
| A28 | P2 | Documentation | README + v018 changelog + diff summary completed |

**Reporting:** For each item mark PASS / FAIL / BLOCKED with screenshot or test-log reference. Physical motor motion and learning are not required in UI acceptance and must not be automatically executed.

# Solution 1 — Minimal trigger encoding fix (based on PyCodeFin.py)

## What was changed

**File:** `PyCodeFin_fixed.py`
**Base:** original `PyCodeFin.py`

### Changes (3 lines only)

| Location | Before | After |
|---|---|---|
| `TRIGGER_RESET_DELAY` constant | `0.03` (30 ms) | `0.05` (50 ms) |
| `send_trigger_on_flip()` — encoding | `str(code).encode("ascii")` | `bytes([code])` |
| `reset_trigger_after()` — reset byte | `b"0"` (byte value 48) | `bytes([0])` (byte value 0) |

## Why

The original code encoded trigger codes as ASCII text:
- `str(1).encode("ascii")` → `b"1"` → the byte whose value is **49** (ASCII for the character '1')

But Unicorn Recorder expects raw integer bytes:
- `bytes([1])` → the byte whose value is **1**

This mismatch explains why triggers were visible in the live view (the recorder received *something*) but were stored as 0 in the CSV (the integer value 49 was not recognized as a valid trigger code).

The same issue applies to the reset: `b"0"` = byte 48, but the reset signal should be `bytes([0])` = byte 0.

The reset delay was increased from 30 ms to 50 ms to match the working standalone test script from the README.

## Architecture preserved

Everything else is identical to `PyCodeFin.py`:
- `win.callOnFlip()` for flip-synchronized trigger onset (good timing)
- Background thread for the reset (non-blocking main loop)

## How to test

1. Replace `PyCodeFin.py` with `PyCodeFin_fixed.py` (or rename it).
2. Start Unicorn Recorder and begin recording **before** running the script.
3. Run the script and check the trigger column in the resulting EEG CSV.

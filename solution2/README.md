# Solution 2 — Non-blocking trigger + flip-synchronized onset + CSV flush (based on codfinalfinal)

## What was changed

**File:** `experiment.py`
**Base:** `codfinalfinal (1).py`

---

## Changes summary

### 1. Added `import threading`

Required for the background reset thread (see change 2).

---

### 2. `send_trigger()` — replaced blocking sleep with background thread

| | Before | After |
|---|---|---|
| Encoding | `str(code).encode()` — ASCII text bytes (e.g. b"1" = byte 49 for code 1) | `bytes([code])` — raw integer byte (byte 1 for code 1) |
| Reset encoding | `b"0"` — byte value 48 (ASCII '0') | `bytes([0])` — byte value 0 (integer 0) |
| Reset timing | `time.sleep(0.05)` on the **main thread** | `time.sleep(0.05)` on a **daemon background thread** |

**Why this matters:**

`time.sleep()` on the main thread blocks PsychoPy's Pyglet event loop for 50 ms on every single trial. PsychoPy relies on Pyglet's event loop to process OS-level window messages. When it is stalled:
- Unicorn Recorder's recording state can be disrupted (because the UDP keepalive / handshake mechanism also runs through the OS network stack, which Pyglet manages)
- PsychoPy's own CSV writer stops receiving callbacks, which is why the behavioral CSV appeared empty after the first trial

The background thread approach releases the main thread immediately. The 50 ms sleep and the reset sendto() happen entirely off the critical path.

---

### 3. `run_stimulus_for_duration()` — trigger scheduled via `win.callOnFlip()` before the first flip

| | Before | After |
|---|---|---|
| When trigger fires | After `win.flip()` returns (1 frame late, ~16 ms at 60 Hz) | At the hardware buffer swap via `win.callOnFlip()` |
| Blocking | Yes — `send_trigger()` contained `time.sleep()` | No — `send_trigger()` is now non-blocking |

`win.callOnFlip(send_trigger, marker_code)` registers the function to be called by PsychoPy at the moment the back buffer is presented to the display hardware. This is the standard PsychoPy pattern for EEG trigger timing and gives sub-millisecond accuracy relative to stimulus onset.

---

### 4. `save_trial()` — added `file_obj=None` parameter with immediate flush

```python
# Before
def save_trial(writer, row_dict, fieldnames):
    writer.writerow({k: row_dict.get(k, "") for k in fieldnames})

# After
def save_trial(writer, row_dict, fieldnames, file_obj=None):
    writer.writerow({k: row_dict.get(k, "") for k in fieldnames})
    if file_obj is not None:
        file_obj.flush()
```

Python's `csv.DictWriter` writes into a file object that has an OS-level I/O buffer. By default, rows accumulate in that buffer until either the buffer fills or the file is closed with the `with` block. If the experiment crashes, the window is force-closed, or PsychoPy calls `core.quit()` mid-experiment, the buffer is discarded and those rows are permanently lost.

`file_obj.flush()` forces the OS to move buffered bytes to the file on disk after every row write. The performance impact is negligible (one syscall per trial, roughly every 3 seconds).

All call sites — `run_oddball_practice`, `run_oddball_block`, `run_lpp_block` — were updated to accept and pass `file_obj`. The `main()` function passes `f` (the open file handle) at each call site. The header write is also followed by `f.flush()`.

---

### 5. Kept all improvements from `codfinalfinal (1).py`

- **`prepare_all_trials()`** — all trial lists built before the window opens, using a seeded `random.Random(participant_code)` for reproducible randomization
- **`preload_images_from_trials()`** — all `visual.ImageStim` objects created before the experiment starts, eliminating disk I/O latency during trials
- **`build_oddball_trials()` with `rng` parameter** — uses the seeded RNG instead of the global `random` module

---

## How to test

1. Start Unicorn Recorder and begin recording **before** running the script.
2. Run `experiment.py`.
3. After a few trials, verify:
   - The behavioral CSV in `data/` is updated after each trial (not only at the end).
   - The EEG CSV trigger column contains non-zero values (1, 2, 3, 4, or 5) at the correct sample positions.

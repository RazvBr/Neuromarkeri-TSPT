# Solution 3 — Dedicated trigger queue + worker thread (most robust)

## What was changed

**File:** `experiment.py`
**Base:** `codfinalfinal (1).py`

---

## Core architectural change: trigger queue + single worker thread

Solution 2 fixes the blocking `time.sleep()` on the main thread by spawning a new daemon thread for every trigger reset. Solution 3 goes further: a **single long-lived worker thread** owns all UDP sends and all sleeping, started once at module load time.

### The queue approach

```python
import queue

_trigger_queue = queue.Queue()

def _trigger_worker():
    while True:
        code = _trigger_queue.get()
        if code is None:          # sentinel: exit cleanly
            _trigger_queue.task_done()
            break
        sock.sendto(bytes([code]), endpoint)   # onset pulse
        time.sleep(TRIGGER_PULSE_DUR)          # 50 ms hold — NOT on main thread
        sock.sendto(bytes([0]), endpoint)      # reset pulse
        _trigger_queue.task_done()

_trigger_thread = threading.Thread(target=_trigger_worker, daemon=True)
_trigger_thread.start()

def send_trigger(code):
    _trigger_queue.put(code)   # O(1), non-blocking, returns immediately
```

`send_trigger()` now does nothing except `queue.put()`, which returns in microseconds. The main thread is never blocked.

---

## Why the queue is more robust than solution 2's per-trigger thread approach

### 1. No overlapping reset threads

In solution 2, each call to `send_trigger()` spawns a new `threading.Thread`. If two triggers arrive within 50 ms of each other (unlikely but not impossible — e.g. a practice feedback screen is shown immediately after a trigger), two threads are both alive at the same time, both calling `time.sleep(0.05)` and then `sock.sendto(bytes([0]))`. The second reset fires before the first trigger's 50 ms has elapsed.

With the queue, triggers are strictly serialised: the worker processes one code at a time, in order. The second trigger only starts after the first trigger's full onset + sleep + reset cycle completes.

### 2. Thread creation overhead eliminated

On Windows, `threading.Thread().start()` has measurable latency (typically 1–5 ms) due to OS thread creation. In solution 2 this happens once per trial (200 oddball trials + 90 LPP trials = 290 thread creations). In solution 3 the thread is created once at startup.

### 3. Clean shutdown

`cleanup_and_quit()` puts `None` (the sentinel value) into the queue before closing the socket. The worker thread sees the sentinel, calls `task_done()`, and exits its loop. The main thread calls `_trigger_thread.join(timeout=1.0)` to wait for the thread to finish. This prevents the scenario where the socket is closed while the worker thread is still mid-send or mid-sleep.

---

## All other changes (same as solution 2)

### Trigger encoding fixed

| | Before (codfinalfinal) | After |
|---|---|---|
| Onset encoding | `str(code).encode()` → byte 49 for code 1 | `bytes([code])` → byte 1 for code 1 |
| Reset encoding | `b"0"` → byte 48 | `bytes([0])` → byte 0 |

### Trigger scheduled at hardware flip via `win.callOnFlip()`

`win.callOnFlip(send_trigger, marker_code)` is registered before the first `win.flip()` in `run_stimulus_for_duration()`. PsychoPy calls `send_trigger()` at the exact moment the back buffer is swapped to the display. Because `send_trigger()` only calls `queue.put()`, the callback returns in microseconds — the flip timing is not affected.

### `save_trial()` flushes to disk after every row

```python
def save_trial(writer, row_dict, fieldnames, file_obj=None):
    writer.writerow({k: row_dict.get(k, "") for k in fieldnames})
    if file_obj is not None:
        file_obj.flush()
```

All call sites pass the open file handle `f`. The CSV header is also flushed immediately after `writeheader()`. This guarantees that every completed trial is on disk regardless of how the experiment terminates.

### Kept all improvements from `codfinalfinal (1).py`

- `prepare_all_trials()` — all trial lists built before the window opens with a seeded `random.Random(participant_code)` for reproducible randomization
- `preload_images_from_trials()` — all `visual.ImageStim` objects created before the experiment starts
- `build_oddball_trials()` with `rng` parameter — uses the seeded instance instead of the global `random` module

---

## Comparison of all three solutions

| Feature | solution1 | solution2 | solution3 |
|---|---|---|---|
| Correct byte encoding (`bytes([code])`) | Yes | Yes | Yes |
| Main thread never sleeps during trial | Yes (thread per reset) | Yes (thread per reset) | Yes (single queue worker) |
| Trigger at hardware flip (`callOnFlip`) | Yes (already in PyCodeFin.py) | Yes | Yes |
| No overlapping reset threads | No (one thread per trigger) | No (one thread per trigger) | Yes (serialised queue) |
| Zero thread creation overhead per trial | No | No | Yes |
| Clean socket shutdown before exit | No | No | Yes (sentinel + join) |
| `f.flush()` after every CSV row | No | Yes | Yes |
| Image preloading | No | Yes | Yes |
| Seeded reproducible randomization | No | Yes | Yes |

---

## How to test

1. Start Unicorn Recorder and begin recording **before** running the script.
2. Run `experiment.py`.
3. After a few trials, verify:
   - The behavioral CSV in `data/` is updated after each trial.
   - The EEG CSV trigger column contains non-zero integer values (1, 2, 3, 4, or 5) at the correct sample positions.
4. To verify serialisation: add a short `time.sleep(0.01)` before the oddball loop and confirm no duplicate or out-of-order triggers appear in the EEG recording.

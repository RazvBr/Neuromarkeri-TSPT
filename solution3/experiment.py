from psychopy import visual, core, event, gui, data
import csv
import queue    # FIX: dedicated trigger queue for the background worker thread
import random
import socket
import threading
import time
from pathlib import Path



# =========================================================
# SETĂRI GENERALE EXPERIMENT
# =========================================================

ODDBALL_STIM_DUR = 1.000
# Durata imaginii în oddball = 1000 ms

ODDBALL_ISI = 2.000
# Interval inter-trial în oddball = 2000 ms

LPP_FIX_DUR = 0.500
# Durata crucii de fixare înainte de imagine în LPP = 500 ms

LPP_STIM_DUR = 2.000
# Durata imaginii în LPP = 2000 ms

PRACTICE_N_TARGETS = 3
# Numărul de targeturi în practica oddball

ODDBALL_N_TARGETS = 40
# Numărul de targeturi în oddball real
# Cu raport 80/20 => 160 standard + 40 target = 200 trialuri total

QUIT_KEYS = ["escape"]
START_KEY = "space"
TARGET_KEY = "space"

BG_COLOR = "lightgrey"
TEXT_COLOR = "black"
FIX_COLOR = "black"

IMAGE_SIZE = (0.9, 0.7)
# Dimensiunea imaginilor pe ecran (în unități de tip "height")


# =========================================================
# CĂI FIȘIERE
# =========================================================

BASE_DIR = Path(__file__).parent.resolve()
# Folderul în care se află scriptul

DATA_DIR = BASE_DIR / "data"
# Folderul în care salvăm CSV-ul comportamental

STIM_DIR = BASE_DIR / "stimuli"
# Folderul cu stimuli

ODDBALL_STANDARD_IMAGE = STIM_DIR / "oddball" / "standard_checkerboard.jpg"
# Imaginea standard din oddball

ODDBALL_TARGET_IMAGE = STIM_DIR / "oddball" / "target_checkerboard.jpg"
# Imaginea target din oddball

LPP_FILE = STIM_DIR / "lpp_images.csv"
# CSV-ul care conține imaginile pentru LPP

DATA_DIR.mkdir(exist_ok=True)
# Creează folderul data dacă nu există deja


# =========================================================
# METADATA EEG - doar descriptive, scrise în CSV
# =========================================================

EEG_METADATA = {
    "device": "Unicorn Hybrid Black",
    "n_channels": 8,
    "sampling_rate_hz": 250,
    "reference": "L/R mastoids",
    "montage_description": "Fz,C3,Cz,C4,Pz,PO7,Oz,PO8",
    "roi_n100": "PO7,Oz,PO8",
    "roi_p300": "Pz",
    "roi_lpp": "Pz"
}


# =========================================================
# RAPORT ODDBALL
# =========================================================

ODDBALL_STANDARD_PROB = 0.80
ODDBALL_TARGET_PROB = 0.20
# Oddball clasic: 80% standard, 20% target


# =========================================================
# SETĂRI UDP PENTRU UNICORN RECORDER
# =========================================================

UDP_IP = "127.0.0.1"
UDP_PORT = 1000

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
# Creează socket-ul UDP

endpoint = (UDP_IP, UDP_PORT)
# Endpoint-ul UDP final

TRIGGER_PULSE_DUR = 0.05
# Triggerul rămâne activ 50 ms

MARKERS = {
    "practice_standard": 1,
    "practice_target": 2,
    "oddball_standard": 1,
    "oddball_target": 2,
    "lpp_positive": 3,
    "lpp_neutral": 4,
    "lpp_negative": 5,
    "fallback": 9,
}
# Codurile markerilor


# =========================================================
# TRIGGER QUEUE + WORKER THREAD
#
# This is the most robust trigger architecture for PsychoPy + Unicorn.
#
# A single long-lived background thread owns all UDP sends. The main thread
# only calls queue.put(code), which is O(1) and never blocks. The worker
# thread handles:
#   1. sock.sendto(bytes([code]), endpoint)   — onset pulse
#   2. time.sleep(TRIGGER_PULSE_DUR)          — 50 ms hold
#   3. sock.sendto(bytes([0]), endpoint)      — reset
#
# Advantages over solution2's per-trigger thread approach:
# - Only ONE thread is ever alive at a time; no risk of two overlapping
#   triggers spawning concurrent reset threads that race each other.
# - The queue serialises all triggers: if two events arrive within 50 ms
#   of each other (unlikely but possible), they are processed in order
#   rather than both firing simultaneously.
# - Thread creation overhead (which is non-trivial on Windows) happens
#   once at startup, not once per trial.
# - Clean shutdown: putting None into the queue signals the worker to
#   exit before the process terminates, avoiding any "daemon thread
#   abruptly killed" warnings.
# =========================================================

_trigger_queue = queue.Queue()


def _trigger_worker():
    """
    Background thread: reads trigger codes from the queue, sends the UDP
    onset pulse, waits 50 ms, then sends the UDP reset pulse.
    Exits cleanly when it receives None (sentinel value).
    """
    while True:
        code = _trigger_queue.get()
        if code is None:
            # Sentinel received — exit the thread cleanly
            _trigger_queue.task_done()
            break
        # Send onset pulse as raw integer byte
        sock.sendto(bytes([code]), endpoint)
        # Hold for 50 ms (safe to block here — we are NOT on the main thread)
        time.sleep(TRIGGER_PULSE_DUR)
        # Send reset as byte value 0 (integer 0, not ASCII '0')
        sock.sendto(bytes([0]), endpoint)
        _trigger_queue.task_done()


# Start the worker thread once at module load time.
# daemon=True means it will not prevent the process from exiting if
# cleanup_and_quit() fails to send the sentinel for any reason.
_trigger_thread = threading.Thread(target=_trigger_worker, daemon=True)
_trigger_thread.start()


def send_trigger(code):
    """
    Non-blocking trigger send.
    Puts the trigger code into the queue; the worker thread handles the
    actual UDP sendto() + sleep + reset entirely off the main thread.
    queue.put() returns immediately (no blocking, no sleep on main thread).
    """
    _trigger_queue.put(code)


# =========================================================
# FUNCȚII GENERALE
# =========================================================

def cleanup_and_quit(win):
    """
    Închide experimentul:
    - trimite sentinela None în coadă pentru a opri worker thread-ul curat
    - așteaptă terminarea worker thread-ului (max 1 s)
    - închide socket-ul UDP
    - închide fereastra PsychoPy
    - oprește scriptul
    """
    # Send sentinel to stop the worker thread gracefully before closing the socket
    _trigger_queue.put(None)
    _trigger_thread.join(timeout=1.0)

    try:
        sock.close()
    except Exception:
        pass

    win.close()
    core.quit()


def draw_text_and_wait(win, text, wait_for_key=True):
    """
    Afișează un ecran cu text.
    Dacă wait_for_key=True, așteaptă SPACE sau ESCAPE.
    """
    stim = visual.TextStim(
        win,
        text=text,
        color=TEXT_COLOR,
        wrapWidth=1.5,
        height=0.045
    )
    stim.draw()
    win.flip()

    if wait_for_key:
        keys = event.waitKeys(keyList=[START_KEY] + QUIT_KEYS)
        if "escape" in keys:
            cleanup_and_quit(win)


def show_instruction_image(win, image_stim, text):
    """
    Arată o imagine + text explicativ dedesubt.
    Folosit pentru a arăta participantului care e standardul și care e targetul.
    """
    text_stim = visual.TextStim(
        win,
        text=text,
        color=TEXT_COLOR,
        wrapWidth=1.5,
        height=0.04,
        pos=(0, -0.42)
    )

    image_stim.draw()
    text_stim.draw()
    win.flip()

    keys = event.waitKeys(keyList=[START_KEY] + QUIT_KEYS)
    if "escape" in keys:
        cleanup_and_quit(win)


def show_fixation(win, duration):
    """
    Arată crucea de fixare pentru durata specificată.
    """
    fix = visual.TextStim(win, text="+", color=FIX_COLOR, height=0.08)
    fix.draw()
    win.flip()
    core.wait(duration)


def save_trial(writer, row_dict, fieldnames, file_obj=None):
    """
    Scrie un rând în CSV-ul comportamental.
    Dacă vreo coloană lipsește, pune șir gol.

    Accepts optional file_obj: when provided, calls file_obj.flush() after
    each row write so that data reaches the disk immediately rather than
    sitting in Python's I/O buffer where it can be lost if the experiment
    crashes or is force-quit.
    """
    writer.writerow({k: row_dict.get(k, "") for k in fieldnames})
    if file_obj is not None:
        file_obj.flush()


def load_lpp_csv(csv_path):
    """
    Citește fișierul lpp_images.csv și returnează lista de trialuri LPP.
    Fiecare trial va conține:
    - image
    - valence
    """
    rows = []
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append({
                "image": row["image"],
                "valence": row["valence"]
            })
    return rows


def validate_lpp_counts(trials):
    """
    Verifică dacă lpp_images.csv are exact:
    - 30 positive
    - 30 neutral
    - 30 negative
    Dacă nu, dă eroare și oprește experimentul.
    """
    counts = {"positive": 0, "neutral": 0, "negative": 0}

    for t in trials:
        if t["valence"] in counts:
            counts[t["valence"]] += 1

    expected = {"positive": 30, "neutral": 30, "negative": 30}
    if counts != expected:
        raise ValueError(
            f"lpp_images.csv trebuie să conțină exact 30 positive, 30 neutral, 30 negative. "
            f"Acum are: {counts}"
        )


def build_oddball_trials(n_targets, standard_image_path, target_image_path, rng):
    """
    Construiește lista de trialuri pentru oddball:
    - standard
    - target

    Se calculează automat câte standarde trebuie pentru raportul 80/20.
    """
    standard_n = round(n_targets * (ODDBALL_STANDARD_PROB / ODDBALL_TARGET_PROB))
    trials = []

    for _ in range(standard_n):
        trials.append({
            "trial_type": "standard",
            "image": str(standard_image_path),
            "correct_response": 0
        })

    for _ in range(n_targets):
        trials.append({
            "trial_type": "target",
            "image": str(target_image_path),
            "correct_response": 1
        })

    rng.shuffle(trials)
    return trials


def prepare_all_trials(participant_code):
    """
    Pregătește TOATE trialurile înainte să înceapă experimentul:
    - practice oddball
    - oddball real
    - LPP

    Folosim participant_code ca seed pentru randomizare reproductibilă.
    """
    rng = random.Random(participant_code)

    practice_trials = build_oddball_trials(
        n_targets=PRACTICE_N_TARGETS,
        standard_image_path=ODDBALL_STANDARD_IMAGE,
        target_image_path=ODDBALL_TARGET_IMAGE,
        rng=rng
    )

    oddball_trials = build_oddball_trials(
        n_targets=ODDBALL_N_TARGETS,
        standard_image_path=ODDBALL_STANDARD_IMAGE,
        target_image_path=ODDBALL_TARGET_IMAGE,
        rng=rng
    )

    lpp_trials = load_lpp_csv(LPP_FILE)
    validate_lpp_counts(lpp_trials)
    rng.shuffle(lpp_trials)

    return practice_trials, oddball_trials, lpp_trials


def preload_images_from_trials(win, practice_trials, oddball_trials, lpp_trials):
    """
    Încarcă toate imaginile în memorie înainte de task.
    Asta reduce lagul produs de citirea din disc în timpul experimentului.
    """
    image_cache = {}
    all_paths = set()

    all_paths.add(str(ODDBALL_STANDARD_IMAGE))
    all_paths.add(str(ODDBALL_TARGET_IMAGE))

    for t in practice_trials:
        all_paths.add(t["image"])

    for t in oddball_trials:
        all_paths.add(t["image"])

    for t in lpp_trials:
        all_paths.add(t["image"])

    for path in all_paths:
        image_cache[path] = visual.ImageStim(
            win,
            image=path,
            size=IMAGE_SIZE,
            units="height",
            interpolate=True
        )

    return image_cache


def run_stimulus_for_duration(win, image_stim, duration, response_key=None, marker_code=None):
    """
    Afișează un stimul (imagine) pentru o durată fixă.
    Opțional:
    - trimite markerul sincronizat cu flip-ul ecranului via win.callOnFlip()
    - colectează răspunsul participantului

    win.callOnFlip(send_trigger, marker_code) schedules queue.put(marker_code)
    to be called at the exact hardware buffer swap moment. Because send_trigger()
    only calls queue.put() (which is O(1) and non-blocking), the callOnFlip
    callback returns in microseconds and does not interfere with the flip timing.
    The actual UDP send and the 50 ms sleep happen entirely in the worker thread.
    """
    event.clearEvents(eventType="keyboard")
    clock = core.Clock()

    # Schedule the trigger to fire at the hardware flip moment.
    # send_trigger() just calls queue.put() — extremely fast, non-blocking.
    if marker_code is not None:
        win.callOnFlip(send_trigger, marker_code)

    # PRIMUL FRAME AL IMAGINII
    image_stim.draw()
    win.flip()
    # imaginea apare pe ecran; send_trigger() is called here via callOnFlip

    pressed = 0
    rt = ""

    while clock.getTime() < duration:
        if response_key is not None:
            keys = event.getKeys(keyList=[response_key] + QUIT_KEYS, timeStamped=clock)
            if keys:
                for key, key_rt in keys:
                    if key in QUIT_KEYS:
                        cleanup_and_quit(win)
                    if key == response_key and pressed == 0:
                        pressed = 1
                        rt = key_rt

        image_stim.draw()
        win.flip()

    return pressed, rt


# =========================================================
# PRACTICĂ ODDBALL
# =========================================================

def run_oddball_practice(win, writer, fieldnames, participant_code, practice_trials, image_cache, file_obj=None):
    # file_obj: passed through to save_trial() for immediate flush after each row
    draw_text_and_wait(
        win,
        "Exersare\n\n"
        "Veți face acum un scurt exercițiu.\n\n"
        "Amintiți-vă:\n"
        "- nu apăsați nimic la imaginea frecventă;\n"
        "- apăsați SPACE la imaginea rară.\n\n"
        "Apăsați SPACE pentru a începe exercițiul."
    )

    for trial_index, trial in enumerate(practice_trials, start=1):
        image_stim = image_cache[trial["image"]]

        trigger_code = (
            MARKERS["practice_standard"]
            if trial["trial_type"] == "standard"
            else MARKERS["practice_target"]
        )

        pressed, rt = run_stimulus_for_duration(
            win=win,
            image_stim=image_stim,
            duration=ODDBALL_STIM_DUR,
            response_key=TARGET_KEY,
            marker_code=trigger_code
        )

        if trial["correct_response"] == 1:
            acc = 1 if pressed == 1 else 0
        else:
            acc = 1 if pressed == 0 else 0

        if acc == 1:
            fb_text = "Corect"
        else:
            fb_text = (
                "Trebuia să apăsați SPACE"
                if trial["correct_response"] == 1
                else "Nu trebuia să răspundeți"
            )

        save_trial(writer, {
            "participant_code": participant_code,
            "task": "oddball_practice",
            "block": "practice",
            "trial_index": trial_index,
            "trial_type": trial["trial_type"],
            "valence": "neutral_task",
            "image": trial["image"],
            "stim_dur_s": ODDBALL_STIM_DUR,
            "isi_s": ODDBALL_ISI,
            "response_key": TARGET_KEY if pressed else "",
            "rt_s": rt,
            "accuracy": acc,
            "marker_code": trigger_code,
            "device": EEG_METADATA["device"],
            "n_channels": EEG_METADATA["n_channels"],
            "sampling_rate_hz": EEG_METADATA["sampling_rate_hz"],
            "reference": EEG_METADATA["reference"],
            "montage_description": EEG_METADATA["montage_description"],
            "roi_n100": EEG_METADATA["roi_n100"],
            "roi_p300": EEG_METADATA["roi_p300"],
            "roi_lpp": EEG_METADATA["roi_lpp"]
        }, fieldnames, file_obj=file_obj)

        fb = visual.TextStim(
            win,
            text=fb_text,
            color=TEXT_COLOR,
            height=0.05
        )
        fb.draw()
        win.flip()
        core.wait(0.8)

        show_fixation(win, ODDBALL_ISI)

    draw_text_and_wait(
        win,
        "Exersarea s-a încheiat.\n\n"
        "Dacă ați înțeles sarcina, apăsați SPACE pentru a începe partea reală."
    )


# =========================================================
# ODDBALL REAL
# =========================================================

def run_oddball_block(win, writer, fieldnames, participant_code, oddball_trials, practice_trials, image_cache, file_obj=None):
    # file_obj: passed through to save_trial() for immediate flush after each row
    draw_text_and_wait(
        win,
        "Partea 1\n\n"
        "În această secțiune vor apărea pe ecran două tipuri de imagini.\n\n"
        "Mai întâi vi se va arăta ce trebuie să faceți pentru fiecare imagine.\n\n"
        "Apăsați SPACE pentru a continua."
    )

    show_instruction_image(
        win,
        image_cache[str(ODDBALL_STANDARD_IMAGE)],
        "Aceasta este imaginea care apare frecvent.\n"
        "Când vedeți această imagine, NU apăsați nimic.\n\n"
        "Apăsați SPACE pentru a continua."
    )

    show_instruction_image(
        win,
        image_cache[str(ODDBALL_TARGET_IMAGE)],
        "Aceasta este imaginea care apare rar.\n"
        "Când vedeți această imagine, apăsați tasta SPACE cât mai repede.\n\n"
        "Apăsați SPACE pentru a continua."
    )

    draw_text_and_wait(
        win,
        "Pe scurt:\n\n"
        "- la imaginea frecventă nu răspundeți;\n"
        "- la imaginea rară apăsați SPACE.\n\n"
        "Veți face acum o scurtă exersare."
    )

    run_oddball_practice(
        win=win,
        writer=writer,
        fieldnames=fieldnames,
        participant_code=participant_code,
        practice_trials=practice_trials,
        image_cache=image_cache,
        file_obj=file_obj
    )

    draw_text_and_wait(
        win,
        "Urmează partea reală.\n\n"
        "Încercați să răspundeți cât mai rapid și cât mai corect.\n\n"
        "Apăsați SPACE pentru a începe."
    )

    for trial_index, trial in enumerate(oddball_trials, start=1):
        image_stim = image_cache[trial["image"]]

        trigger_code = (
            MARKERS["oddball_standard"]
            if trial["trial_type"] == "standard"
            else MARKERS["oddball_target"]
        )

        pressed, rt = run_stimulus_for_duration(
            win=win,
            image_stim=image_stim,
            duration=ODDBALL_STIM_DUR,
            response_key=TARGET_KEY,
            marker_code=trigger_code
        )

        if trial["correct_response"] == 1:
            acc = 1 if pressed == 1 else 0
        else:
            acc = 1 if pressed == 0 else 0

        show_fixation(win, ODDBALL_ISI)

        save_trial(writer, {
            "participant_code": participant_code,
            "task": "oddball",
            "block": "oddball",
            "trial_index": trial_index,
            "trial_type": trial["trial_type"],
            "valence": "neutral_task",
            "image": trial["image"],
            "stim_dur_s": ODDBALL_STIM_DUR,
            "isi_s": ODDBALL_ISI,
            "response_key": TARGET_KEY if pressed else "",
            "rt_s": rt,
            "accuracy": acc,
            "marker_code": trigger_code,
            "device": EEG_METADATA["device"],
            "n_channels": EEG_METADATA["n_channels"],
            "sampling_rate_hz": EEG_METADATA["sampling_rate_hz"],
            "reference": EEG_METADATA["reference"],
            "montage_description": EEG_METADATA["montage_description"],
            "roi_n100": EEG_METADATA["roi_n100"],
            "roi_p300": EEG_METADATA["roi_p300"],
            "roi_lpp": EEG_METADATA["roi_lpp"]
        }, fieldnames, file_obj=file_obj)


# =========================================================
# LPP
# =========================================================

def run_lpp_block(win, writer, fieldnames, participant_code, lpp_trials, image_cache, file_obj=None):
    # file_obj: passed through to save_trial() for immediate flush after each row
    draw_text_and_wait(
        win,
        "Partea 2\n\n"
        "În această secțiunea vor apărea diferite imagini.\n\n"
        "Vă rugăm să priviți atent fiecare imagine până dispare de pe ecran.\n"
        "În această parte NU trebuie să apăsați nicio tastă.\n\n"
        "Important:\n"
        "- priviți imaginile cu atenție;\n"
        "- uitați-vă la crucea de fixare când apare;\n"
        "- stați cât mai nemișcat(ă);\n"
        "- clipiți cât mai puțin în timpul prezentării imaginilor.\n\n"
        "Apăsați SPACE pentru a începe."
    )

    for trial_index, trial in enumerate(lpp_trials, start=1):
        show_fixation(win, LPP_FIX_DUR)

        image_stim = image_cache[trial["image"]]

        trigger_code = {
            "positive": MARKERS["lpp_positive"],
            "neutral": MARKERS["lpp_neutral"],
            "negative": MARKERS["lpp_negative"]
        }.get(trial["valence"], MARKERS["fallback"])

        run_stimulus_for_duration(
            win=win,
            image_stim=image_stim,
            duration=LPP_STIM_DUR,
            response_key=None,
            marker_code=trigger_code
        )

        save_trial(writer, {
            "participant_code": participant_code,
            "task": "lpp_viewing",
            "block": "lpp",
            "trial_index": trial_index,
            "trial_type": "view",
            "valence": trial["valence"],
            "image": trial["image"],
            "stim_dur_s": LPP_STIM_DUR,
            "isi_s": LPP_FIX_DUR,
            "response_key": "",
            "rt_s": "",
            "accuracy": "",
            "marker_code": trigger_code,
            "device": EEG_METADATA["device"],
            "n_channels": EEG_METADATA["n_channels"],
            "sampling_rate_hz": EEG_METADATA["sampling_rate_hz"],
            "reference": EEG_METADATA["reference"],
            "montage_description": EEG_METADATA["montage_description"],
            "roi_n100": EEG_METADATA["roi_n100"],
            "roi_p300": EEG_METADATA["roi_p300"],
            "roi_lpp": EEG_METADATA["roi_lpp"]
        }, fieldnames, file_obj=file_obj)


# =========================================================
# MAIN
# =========================================================

def main():
    exp_info = {
        "participant_code": "",
        "session": "1"
    }

    dlg = gui.DlgFromDict(exp_info, title="ERP Image Task")
    if not dlg.OK:
        return

    participant_code = exp_info["participant_code"].strip()
    session = exp_info["session"].strip()

    outfile = DATA_DIR / f"{participant_code}_ses-{session}_{data.getDateStr()}.csv"

    fieldnames = [
        "participant_code",
        "task",
        "block",
        "trial_index",
        "trial_type",
        "valence",
        "image",
        "stim_dur_s",
        "isi_s",
        "response_key",
        "rt_s",
        "accuracy",
        "marker_code",
        "device",
        "n_channels",
        "sampling_rate_hz",
        "reference",
        "montage_description",
        "roi_n100",
        "roi_p300",
        "roi_lpp"
    ]

    win = visual.Window(
        size=(1200, 900),
        fullscr=False,
        color=BG_COLOR,
        units="height"
    )

    win.flip()
    # un flip de încălzire al ferestrei

    # PREGĂTIM TOTUL ÎNAINTE DE TASK
    practice_trials, oddball_trials, lpp_trials = prepare_all_trials(participant_code)
    image_cache = preload_images_from_trials(win, practice_trials, oddball_trials, lpp_trials)

    with open(outfile, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        f.flush()  # flush the header to disk immediately

        draw_text_and_wait(
            win,
            "Bine ați venit!\n\n"
            "În acest experiment veți vedea o serie de imagini prezentate pe ecran.\n\n"
            "Sarcina dumneavoastră este să priviți atent ecranul și să urmați "
            "instrucțiunile pentru fiecare parte a experimentului.\n\n"
            "Vă rugăm:\n"
            "- să stați cât mai nemișcat(ă),\n"
            "- să priviți spre centrul ecranului,\n"
            "- să clipiți cât mai puțin în timpul prezentării imaginilor,\n"
            "- să răspundeți cât mai corect și cât mai rapid atunci când este necesar.\n\n"
            "Experimentul este alcătuit din mai multe secțiuni.\n"
            "Înainte de fiecare secțiune, veți primi instrucțiuni specifice.\n\n"
            "Apăsați SPACE pentru a continua."
        )

        run_oddball_block(
            win=win,
            writer=writer,
            fieldnames=fieldnames,
            participant_code=participant_code,
            oddball_trials=oddball_trials,
            practice_trials=practice_trials,
            image_cache=image_cache,
            file_obj=f  # pass file handle so save_trial() can flush after each row
        )

        draw_text_and_wait(
            win,
            "Pauză\n\n"
            "Puteți să vă odihniți câteva momente.\n\n"
            "Apăsați SPACE când sunteți gata să continuați."
        )

        run_lpp_block(
            win=win,
            writer=writer,
            fieldnames=fieldnames,
            participant_code=participant_code,
            lpp_trials=lpp_trials,
            image_cache=image_cache,
            file_obj=f  # pass file handle so save_trial() can flush after each row
        )

        draw_text_and_wait(
            win,
            "Experimentul s-a încheiat.\n\n"
            "Vă mulțumim pentru participare!",
            wait_for_key=False
        )
        core.wait(2.0)

    cleanup_and_quit(win)


if __name__ == "__main__":
    main()

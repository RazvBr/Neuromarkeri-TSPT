from psychopy import visual, core, event, gui, data
import csv
import random
import socket
import threading
import time
from pathlib import Path


# =========================================================
# SETĂRI GENERALE EXPERIMENT
# =========================================================

DEBUG = True

ODDBALL_STIM_DUR = 1.000
ODDBALL_ISI = 2.000
LPP_FIX_DUR = 0.500
LPP_STIM_DUR = 2.000

PRACTICE_N_TARGETS = 1
ODDBALL_N_TARGETS = 3

QUIT_KEYS = ["escape"]
START_KEY = "space"
TARGET_KEY = "space"

BG_COLOR = "lightgrey"
TEXT_COLOR = "black"
FIX_COLOR = "black"

IMAGE_SIZE = (0.9, 0.7)


def dprint(*args):
    """Print doar dacă DEBUG=True."""
    if DEBUG:
        print("[DEBUG]", *args)


# =========================================================
# CĂI FIȘIERE
# =========================================================

BASE_DIR = Path(__file__).parent.resolve()
DATA_DIR = BASE_DIR / "data"
STIM_DIR = BASE_DIR / "stimuli"

ODDBALL_STANDARD_IMAGE = STIM_DIR / "oddball" / "standard_checkerboard.jpg"
ODDBALL_TARGET_IMAGE = STIM_DIR / "oddball" / "target_checkerboard.jpg"
LPP_FILE = STIM_DIR / "lpp_images.csv"

DATA_DIR.mkdir(exist_ok=True)

dprint("BASE_DIR =", BASE_DIR)
dprint("DATA_DIR =", DATA_DIR)
dprint("STIM_DIR =", STIM_DIR)
dprint("ODDBALL_STANDARD_IMAGE exists =", ODDBALL_STANDARD_IMAGE.exists())
dprint("ODDBALL_TARGET_IMAGE exists =", ODDBALL_TARGET_IMAGE.exists())
dprint("LPP_FILE exists =", LPP_FILE.exists())


# =========================================================
# METADATA EEG
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


# =========================================================
# SETĂRI UDP
# =========================================================

UDP_IP = "127.0.0.1"
UDP_PORT = 1000

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
endpoint = (UDP_IP, UDP_PORT)

TRIGGER_PULSE_DUR = 0.05

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

dprint("UDP endpoint =", endpoint)
dprint("MARKERS =", MARKERS)


# =========================================================
# FUNCȚII GENERALE
# =========================================================

def cleanup_and_quit(win):
    dprint("cleanup_and_quit() called")
    try:
        sock.close()
        dprint("Socket closed")
    except Exception as e:
        dprint("Socket close error:", e)

    win.close()
    dprint("Window closed")
    core.quit()


def _reset_trigger_after_delay():
    dprint("Trigger reset thread started; waiting", TRIGGER_PULSE_DUR, "sec")
    time.sleep(TRIGGER_PULSE_DUR)
    sock.sendto(bytes([0]), endpoint)
    dprint("Trigger reset sent: 0")


def send_trigger(code):
    dprint("send_trigger() called with code =", code)
    sock.sendto(bytes([code]), endpoint)
    dprint("Trigger sent:", code)
    threading.Thread(target=_reset_trigger_after_delay, daemon=True).start()


def draw_text_and_wait(win, text, wait_for_key=True):
    dprint("draw_text_and_wait() | wait_for_key =", wait_for_key)
    dprint("Text preview:", repr(text[:80]))

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
        dprint("Keys pressed on text screen:", keys)
        if "escape" in keys:
            cleanup_and_quit(win)


def show_instruction_image(win, image_stim, text):
    dprint("show_instruction_image()")
    dprint("Instruction text preview:", repr(text[:80]))
    dprint("Image path =", image_stim.image)

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
    dprint("Keys pressed on instruction image:", keys)
    if "escape" in keys:
        cleanup_and_quit(win)


def show_fixation(win, duration):
    dprint("show_fixation() duration =", duration)
    fix = visual.TextStim(win, text="+", color=FIX_COLOR, height=0.08)
    fix.draw()
    win.flip()
    core.wait(duration)


def save_trial(writer, row_dict, fieldnames, file_obj=None):
    writer.writerow({k: row_dict.get(k, "") for k in fieldnames})
    if file_obj is not None:
        file_obj.flush()

    dprint(
        "save_trial() | task =", row_dict.get("task"),
        "| block =", row_dict.get("block"),
        "| trial_index =", row_dict.get("trial_index"),
        "| trial_type =", row_dict.get("trial_type"),
        "| valence =", row_dict.get("valence"),
        "| response_key =", row_dict.get("response_key"),
        "| rt_s =", row_dict.get("rt_s"),
        "| accuracy =", row_dict.get("accuracy"),
        "| marker_code =", row_dict.get("marker_code")
    )


def load_lpp_csv(csv_path):
    dprint("load_lpp_csv() from", csv_path)
    rows = []
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append({
                "image": row["image"],
                "valence": row["valence"]
            })

    dprint("Loaded LPP rows =", len(rows))
    if rows:
        dprint("First 3 LPP rows =", rows[:3])
    return rows


def validate_lpp_counts(trials):
    dprint("validate_lpp_counts()")
    counts = {"positive": 0, "neutral": 0, "negative": 0}

    for t in trials:
        if t["valence"] in counts:
            counts[t["valence"]] += 1

    dprint("LPP valence counts =", counts)

    expected = {"positive": 30, "neutral": 30, "negative": 30}
    if counts != expected:
        raise ValueError(
            f"lpp_images.csv trebuie să conțină exact 30 positive, 30 neutral, 30 negative. "
            f"Acum are: {counts}"
        )


def build_oddball_trials(n_targets, standard_image_path, target_image_path, rng):
    dprint("build_oddball_trials() | n_targets =", n_targets)

    standard_n = round(n_targets * (ODDBALL_STANDARD_PROB / ODDBALL_TARGET_PROB))
    dprint("Calculated standard_n =", standard_n)

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

    dprint("Total oddball trials built =", len(trials))
    dprint("First 5 oddball trials =", trials[:5])

    return trials


def prepare_all_trials(participant_code):
    dprint("prepare_all_trials() | participant_code =", participant_code)

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

    dprint("Practice trials =", len(practice_trials))
    dprint("Oddball trials =", len(oddball_trials))
    dprint("LPP trials =", len(lpp_trials))
    dprint("First 3 shuffled LPP trials =", lpp_trials[:3])

    return practice_trials, oddball_trials, lpp_trials


def preload_images_from_trials(win, practice_trials, oddball_trials, lpp_trials):
    dprint("preload_images_from_trials()")
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

    dprint("Unique image paths to preload =", len(all_paths))

    for path in all_paths:
        dprint("Preloading image:", path)
        image_cache[path] = visual.ImageStim(
            win,
            image=path,
            size=IMAGE_SIZE,
            units="height",
            interpolate=True
        )

    dprint("Preloaded images =", len(image_cache))
    return image_cache


def run_stimulus_for_duration(win, image_stim, duration, response_key=None, marker_code=None):
    dprint(
        "run_stimulus_for_duration()",
        "| image =", image_stim.image,
        "| duration =", duration,
        "| response_key =", response_key,
        "| marker_code =", marker_code
    )

    event.clearEvents(eventType="keyboard")
    clock = core.Clock()

    if marker_code is not None:
        dprint("Scheduling trigger on flip:", marker_code)
        win.callOnFlip(send_trigger, marker_code)

    image_stim.draw()
    win.flip()
    dprint("Stimulus first frame shown")

    pressed = 0
    rt = ""

    while clock.getTime() < duration:
        if response_key is not None:
            keys = event.getKeys(keyList=[response_key] + QUIT_KEYS, timeStamped=clock)
            if keys:
                dprint("Keys during stimulus:", keys)
                for key, key_rt in keys:
                    if key in QUIT_KEYS:
                        cleanup_and_quit(win)
                    if key == response_key and pressed == 0:
                        pressed = 1
                        rt = key_rt
                        dprint("Registered response:", key, "| RT =", rt)

        image_stim.draw()
        win.flip()

    dprint("Stimulus finished | pressed =", pressed, "| rt =", rt)
    return pressed, rt


# =========================================================
# PRACTICĂ ODDBALL
# =========================================================

def run_oddball_practice(win, writer, fieldnames, participant_code, practice_trials, image_cache, file_obj=None):
    dprint("run_oddball_practice() START")
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
        dprint("Practice trial", trial_index, "|", trial)

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

        dprint("Practice trial result | pressed =", pressed, "| rt =", rt, "| acc =", acc)

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

    dprint("run_oddball_practice() END")
    draw_text_and_wait(
        win,
        "Exersarea s-a încheiat.\n\n"
        "Dacă ați înțeles sarcina, apăsați SPACE pentru a începe partea reală."
    )


# =========================================================
# ODDBALL REAL
# =========================================================

def run_oddball_block(win, writer, fieldnames, participant_code, oddball_trials, practice_trials, image_cache, file_obj=None):
    dprint("run_oddball_block() START")

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
        dprint("Oddball real trial", trial_index, "|", trial)

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

        dprint("Oddball real result | pressed =", pressed, "| rt =", rt, "| acc =", acc)

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

    dprint("run_oddball_block() END")


# =========================================================
# LPP
# =========================================================

def run_lpp_block(win, writer, fieldnames, participant_code, lpp_trials, image_cache, file_obj=None):
    dprint("run_lpp_block() START")

    draw_text_and_wait(
        win,
        "Partea 2\n\n"
        "În această secțiune vor apărea diferite imagini.\n\n"
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
        dprint("LPP trial", trial_index, "|", trial)

        show_fixation(win, LPP_FIX_DUR)
        image_stim = image_cache[trial["image"]]

        trigger_code = {
            "positive": MARKERS["lpp_positive"],
            "neutral": MARKERS["lpp_neutral"],
            "negative": MARKERS["lpp_negative"]
        }.get(trial["valence"], MARKERS["fallback"])

        dprint("LPP trigger_code =", trigger_code)

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

    dprint("run_lpp_block() END")


# =========================================================
# MAIN
# =========================================================

def main():
    dprint("main() START")

    exp_info = {
        "participant_code": "",
        "session": "1"
    }

    dlg = gui.DlgFromDict(exp_info, title="ERP Image Task")
    if not dlg.OK:
        dprint("Dialog cancelled")
        return

    participant_code = exp_info["participant_code"].strip()
    session = exp_info["session"].strip()

    dprint("participant_code =", participant_code)
    dprint("session =", session)

    outfile = DATA_DIR / f"{participant_code}_ses-{session}_{data.getDateStr()}.csv"
    dprint("outfile =", outfile)

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
    dprint("Window created")

    win.flip()
    dprint("Warm-up flip done")

    practice_trials, oddball_trials, lpp_trials = prepare_all_trials(participant_code)
    image_cache = preload_images_from_trials(win, practice_trials, oddball_trials, lpp_trials)

    with open(outfile, "w", newline="", encoding="utf-8") as f:
        dprint("CSV file opened for writing")
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        f.flush()
        dprint("CSV header written and flushed")

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
            file_obj=f
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
            file_obj=f
        )

        draw_text_and_wait(
            win,
            "Experimentul s-a încheiat.\n\n"
            "Vă mulțumim pentru participare!",
            wait_for_key=False
        )
        core.wait(2.0)
        dprint("End screen shown")

    dprint("CSV file closed")
    cleanup_and_quit(win)


if __name__ == "__main__":
    main()
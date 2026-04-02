import psychopy.visual
import psychopy.event
import time
import random
import numpy as np
import socket



# Initialize socket for sending triggers to to unicorn
socket   = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
endPoint = ("127.0.0.1", 1000)

# Global variables
win          = None  # Global variable for window (Initialized in main)
fixation     = None  # Global variable for fixation cross (Initialized in main)
bg_color     = [0, 0, 0]
win_w        = 800
win_h        = 600
refresh_rate = 165.0  # Monitor refresh rate #TODO: update this

# paradigm related vars
trial_duration = 20*1000  # 20 seconds 

#========================================================
# High Level Functions
#========================================================
def Paradigm(trials):
    # Initialize fixation cross
    fixation = psychopy.visual.ShapeStim(
        win=win,
        units='pix',
        size=50,
        fillColor=[1, 1, 1],
        lineColor=[1, 1, 1],
        lineWidth=1,
        vertices='cross',
        name='off',
        pos=[0, 0]
    )
    
    # Initialize text (for instructions & results)
    text = psychopy.visual.TextStim(win,
                                    'INIT TEXT', font='Open Sans', units='pix',
                                    pos=(0, 0), alignText='center',
                                    height=36, color=[1, 1, 1]
                                    )

    for trial in trials:

        # Send trigger for the start of the trial (trigger 100)
        socket.sendto(b"100", endPoint)
        
        # 1000 ms direction instruction (normal or hyperventilation)
        text.text = trial
        
        # Send trigger and get the trigger value for the condition
        trigger = trigger_dict[trial]
        print(f"Trigger: {trigger}")

        for frame in range(MsToFrames(1500, refresh_rate)):
            text.draw()
            win.flip()
        
        # 500ms blank screen
        for frame in range(MsToFrames(500, refresh_rate)):
            win.flip()

        # 5000ms fixation cross (doing condition - hyperventilation or rest)
        socket.sendto(b"%d" % trigger, endPoint)
        for frame in range(MsToFrames(trial_duration, refresh_rate)):
            fixation.draw()
            win.flip()

        # 500ms blank screen
        for frame in range(MsToFrames(500, refresh_rate)):
            win.flip()

        # 1000ms blank screen
        for frame in range(MsToFrames(5000, refresh_rate)):
            win.flip()

        # Send trigger for the end of the trial (trigger 200)
        socket.sendto(b"200", endPoint)

    print("Paradigm complete")


def MsToFrames(ms, fs):
    dt = 1000 / fs
    return np.round(ms / dt).astype(int)


if __name__ == "__main__":
    # Set random seed
    random.seed()
    
    # Create PsychoPy window
    win = psychopy.visual.Window(
        screen=0,
        size=[win_w, win_h],
        units="pix",
        fullscr=False,
        color=bg_color,
        gammaErrorPolicy="ignore"
    )
    
    # Wait a second for the window to settle down
    time.sleep(1)

    # Define the trials: 10 "rest" and 10 "hyperventilation"
    #trials_rest = ['rest'] * 10
    trials_hyperventilation = ['hyperventilation'] * 10
    trials =  trials_hyperventilation

    #
    # Generate a trigger dictionary for conditions
    trigger_dict = {'rest': 1, 'hyperventilation': 2}

    # Run through paradigm
    Paradigm(trials)

    # Close the window
    win.close()

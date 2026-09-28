# Follow the edge of a black line using the color sensor's reflected light.
# Put the color sensor on port 'C'. The robot follows the LEFT edge of the line.
#
# Tip: pick the "BIOGLOW practice (lines & sensors)" board in the Board tab and
# set the start near the line, e.g. Start X=38, Y=52, Heading=90.
from spike import PrimeHub, MotorPair, ColorSensor
from spike.control import wait_for_seconds

hub = PrimeHub()
drive = MotorPair('A', 'B')
color = ColorSensor('C')

TARGET = 50        # aim for the edge: halfway between black (~0) and white (~100)
GAIN = 0.6         # how hard to steer when off target
BASE_SPEED = 30

# Follow for a few seconds of simulated time.
timer_end = 6.0
from spike.control import Timer
t = Timer()

while t.now() < timer_end:
    reflection = color.get_reflected_light()
    error = reflection - TARGET
    steering = GAIN * error          # steer toward the edge
    drive.start(steering=int(steering), speed=BASE_SPEED)
    wait_for_seconds(0.02)

drive.stop()
print("Stopped after following the line.")

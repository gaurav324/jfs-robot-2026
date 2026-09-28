# Drive forward until the distance sensor sees an obstacle, then stop.
# Put the distance sensor on port 'D'.
from spike import PrimeHub, MotorPair, DistanceSensor
from spike.control import wait_for_seconds

hub = PrimeHub()
drive = MotorPair('A', 'B')
eyes = DistanceSensor('D')

drive.start(steering=0, speed=35)
while True:
    d = eyes.get_distance_cm()
    if d is not None and d < 12:
        break
    wait_for_seconds(0.02)

drive.stop()
print("Stopped! Obstacle is about", eyes.get_distance_cm(), "cm away.")

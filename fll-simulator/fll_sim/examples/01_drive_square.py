# Drive in a square using the gyro to make accurate 90-degree turns.
from spike import PrimeHub, MotorPair
from spike.control import wait_for_seconds

hub = PrimeHub()
drive = MotorPair('A', 'B')   # 'A' = left motor, 'B' = right motor
drive.set_default_speed(40)


def turn_right_90():
    """Spin right until the gyro has turned 90 degrees."""
    hub.motion_sensor.reset_yaw_angle()
    drive.start(steering=100, speed=25)      # spin in place, to the right
    while hub.motion_sensor.get_yaw_angle() < 90:
        wait_for_seconds(0.01)
    drive.stop()


for side in range(4):
    print("Driving side", side + 1)
    drive.move(40, 'cm')      # go forward 40 cm
    turn_right_90()
    wait_for_seconds(0.1)

print("Finished the square!")

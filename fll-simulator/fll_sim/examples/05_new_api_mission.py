# SPIKE 3 (new) API style: async + runloop, hub / motor / motor_pair.
# Drive base = motors on ports A (left) and B (right); attachment on port D.
from hub import motion_sensor, port
import motor
import motor_pair
import runloop


def degrees_for_distance(distance_cm):
    WHEEL_CIRCUMFERENCE = 17.5      # cm per wheel turn (~5.6 cm wheels)
    return int((distance_cm / WHEEL_CIRCUMFERENCE) * 360)


async def spin_left(target_degrees):
    # In the Python API, yaw is POSITIVE turning left (counter-clockwise),
    # measured in decidegrees (0.1°). So 90° = 900.
    motion_sensor.reset_yaw(0)
    await runloop.sleep_ms(50)
    motor_pair.move(motor_pair.PAIR_1, -100, velocity=200)   # -100 = spin left
    while motion_sensor.tilt_angles()[0] < target_degrees * 10:
        await runloop.sleep_ms(10)
    motor_pair.stop(motor_pair.PAIR_1)


async def main():
    motor_pair.pair(motor_pair.PAIR_1, port.A, port.B)

    # forward 30 cm
    await motor_pair.move_for_degrees(motor_pair.PAIR_1, degrees_for_distance(30), 0,
                                      velocity=400, stop=motor.BRAKE)
    # turn left 90 degrees using the gyro
    await spin_left(90)
    # forward 20 cm
    await motor_pair.move_for_degrees(motor_pair.PAIR_1, degrees_for_distance(20), 0,
                                      velocity=400, stop=motor.BRAKE)
    # run the attachment arm on port D
    await motor.run_for_degrees(port.D, 360, 720)
    print("Mission complete!")


runloop.run(main())

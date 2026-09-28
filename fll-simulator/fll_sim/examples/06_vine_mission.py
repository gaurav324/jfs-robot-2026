import color_sensor
import color
from hub import port, motion_sensor
import motor
import motor_pair
import runloop


def teeth_rot(rot, a, b):
    return rot * a / b


def degrees_for_distance(distance_cm):
    WHEEL_CIRCUMFERENCE = 17.5
    return int((distance_cm / WHEEL_CIRCUMFERENCE) * 360)


def deg_rot_motor(attach_rot_degree, g1, g2, g3, g4):
    # First gear rotation
    fg_rot = attach_rot_degree / 360.0
    print("First gear rotation:", fg_rot)

    # Transfer rotations with teeth
    sec_g_rot = teeth_rot(fg_rot, g1, g2)
    print("Second gear rotaion:", sec_g_rot)

    # Transfer rotations with axle
    third_g_rot = sec_g_rot
    print("Third:", third_g_rot)

    # Transfer rotation with teeth
    motor_rot = teeth_rot(third_g_rot, g3, g4)
    print("returning ", motor_rot)
    return motor_rot


def get_heading():
    # Heading in degrees since start of run. Right (clockwise) = positive.
    return -motion_sensor.tilt_angles()[0] / 10


async def turn_to(target_heading, turn_type, velocity=400):
    """Turns until the robot faces target_heading (absolute, degrees)."""
    direction = 1 if target_heading > get_heading() else -1  # 1 = right, -1 = left

    if turn_type.lower() == 'spin':
        steering_val = 100 * direction  # Both wheels move in opposition
    elif turn_type.lower() == 'pivot':
        steering_val = 50 * direction  # One wheel locks, one wheel drives
    else:
        raise ValueError("turn_type must be 'spin' or 'pivot'")

    while True:
        remaining = (target_heading - get_heading()) * direction
        if remaining <= 0:
            break
        # Fast when far away, slows down as it gets close to the target
        speed = max(80, min(velocity, int(remaining * 15)))
        motor_pair.move(motor_pair.PAIR_1, steering_val, velocity=speed)
        await runloop.sleep_ms(10)

    motor_pair.stop(motor_pair.PAIR_1, stop=motor.HOLD)


motor_pair.pair(motor_pair.PAIR_1, port.B, port.A)


async def gyro_straight(motor_degrees, heading, velocity=500, KP=2.0):
    """Drives motor_degrees while holding an absolute heading.
    Use a negative velocity to drive backward (motor_degrees stays positive)."""
    start_degrees = motor.relative_position(port.B)
    max_speed = abs(velocity)
    direction = 1 if velocity > 0 else -1

    while True:
        traveled = abs(motor.relative_position(port.B) - start_degrees)
        remaining = motor_degrees - traveled
        if remaining <= 0:
            break

        # Ramp up at the start and slow down near the end to avoid wheel slip
        speed = min(max_speed, 150 + traveled * 3, 100 + remaining * 2)

        # Positive error = robot is left of target heading, needs to steer right
        error = heading - get_heading()
        # Steering works in reverse when driving backward
        correction = round(error * KP) * direction
        correction = max(min(correction, 50), -50)

        motor_pair.move(motor_pair.PAIR_1, correction, velocity=int(speed * direction))
        await runloop.sleep_ms(10)

    motor_pair.stop(motor_pair.PAIR_1, stop=motor.SMART_BRAKE)


async def arm_to(attach_angle, velocity, g1=28, g2=12, g3=20, g4=12):
    """Moves the arm to an angle measured from the ground (0 = on the ground, negative = up)."""
    target = round(deg_rot_motor(attach_angle, g1, g2, g3, g4) * 360)
    await motor.run_to_relative_position(port.C, target, velocity, stop=motor.HOLD)


# YOUR MAIN PROGRAM
async def main():
    # Arm is resting on the ground: push down gently to take up gear slack, then call it 0
    await motor.run_for_time(port.C, 300, 150)
    motor.reset_relative_position(port.C, 0)

    # Reset heading ONCE - robot must be still
    motion_sensor.reset_yaw(0)
    await runloop.until(motion_sensor.stable)
    await arm_to(-90, 350)
    await gyro_straight(degrees_for_distance(37), heading=0)
    # First turn after going straight
    await turn_to(45, 'spin')
    await gyro_straight(degrees_for_distance(25), heading=45)
    # Second turn after additional going straight
    await turn_to(90, 'pivot')
    await gyro_straight(degrees_for_distance(5), heading=90)
    #### Aligning to mission and going forward
    await turn_to(0, 'pivot')
    #### Lifting vine
    await arm_to(-40, 350)
    await gyro_straight(degrees_for_distance(10), heading=0, velocity=100)
    await arm_to(-90, 400)
    await gyro_straight(degrees_for_distance(16), heading=0, velocity=-300)
    #### After coming back from mission completion
    await turn_to(56, 'spin')
    await arm_to(-133, 100)
    await gyro_straight(degrees_for_distance(45), heading=56)
    await arm_to(-163, 350)
    await turn_to(108, 'spin')
    await gyro_straight(degrees_for_distance(40), heading=108)
    await turn_to(56, 'spin')
    await gyro_straight(degrees_for_distance(12), heading=56, velocity=100)
    await gyro_straight(degrees_for_distance(12), heading=56, velocity=-300)
    await turn_to(90, 'spin')
    await arm_to(0, 350)
    await gyro_straight(degrees_for_distance(42), heading=90)
    await arm_to(-40, 350)


    # await gyro_straight(degrees_for_distance(80), heading=0, velocity=-600)
    # await arm_to(0, 350)


runloop.run(main())

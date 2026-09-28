"""
Vine mission — INSTRUMENTED with a telemetry logger.

Same driving logic as mission_vine.py, but it records what the robot is doing
at every control step and prints it as one CSV block at the end. Run this on the
real robot, then copy everything between ===BEGIN CSV=== and ===END CSV=== out of
the SPIKE console and save it as a .csv (or paste it back to review together).

Why: the robot's real speed depends on weight, battery, wheel slip and motor lag
-- none of which the code assumes. The log shows commanded-vs-actual heading,
how far each wheel really turned, and what the sensors read, so we can see WHERE
and WHY a run drifts and tune from evidence instead of guessing.

Logging is buffered in RAM and dumped once at the end, so it does not slow the
robot during the run.
"""

import color_sensor
import color
import distance_sensor
from hub import port, motion_sensor
import motor
import motor_pair
import runloop


# ===========================================================================
# CONFIG
# ===========================================================================
WHEEL_CIRCUMFERENCE = 17.5     # cm the robot rolls per one wheel turn

LEFT_DRIVE = port.B            # the two drive motors (used to read distance)
RIGHT_DRIVE = port.A
ARM_MOTOR = port.C

# Sensor ports to log. Set to the ports your sensors are actually plugged into,
# or leave as None to skip. Reads are wrapped in try/except, so a wrong/empty
# port just logs a blank instead of crashing.
COLOR_PORT = port.E            # set to None if you have no color sensor
DISTANCE_PORT = port.F         # set to None if you have no distance sensor

MIN_SAMPLE_MS = 20             # don't record faster than this (protects hub RAM)


# ===========================================================================
# TELEMETRY LOGGER  (portable: real hub uses time.ticks_ms; sim/PC falls back)
# ===========================================================================
try:
    from time import ticks_ms as _ticks_ms, ticks_diff as _ticks_diff
except ImportError:
    import time as _time
    def _ticks_ms():
        return int(_time.monotonic() * 1000)
    def _ticks_diff(a, b):
        return a - b

# Column order for the CSV output.
_COLS = ["t_ms", "phase", "yaw", "target", "error", "correction", "cmd_speed",
         "enc_left", "enc_right", "dist_cm", "arm", "color", "reflect", "dist_mm"]

_LOG = []
_T0 = None
_LAST_MS = None


def _read_color(p):
    if p is None:
        return None
    try:
        return color_sensor.color(p)
    except Exception:
        return None


def _read_reflect(p):
    if p is None:
        return None
    try:
        return color_sensor.reflection(p)
    except Exception:
        return None


def _read_distance(p):
    if p is None:
        return None
    try:
        return distance_sensor.distance(p)
    except Exception:
        return None


def sample(phase, target=None, error=None, correction=None, cmd_speed=None,
           force=False):
    """Record one row of telemetry (throttled to MIN_SAMPLE_MS unless force)."""
    global _T0, _LAST_MS
    now = _ticks_ms()
    if _T0 is None:
        _T0 = now
    if not force and _LAST_MS is not None and _ticks_diff(now, _LAST_MS) < MIN_SAMPLE_MS:
        return
    _LAST_MS = now

    enc_left = motor.relative_position(LEFT_DRIVE)
    row = {
        "t_ms": _ticks_diff(now, _T0),
        "phase": phase,
        "yaw": get_heading(),
        "target": target,
        "error": error,
        "correction": correction,
        "cmd_speed": cmd_speed,
        "enc_left": enc_left,
        "enc_right": motor.relative_position(RIGHT_DRIVE),
        "dist_cm": round(enc_left / 360.0 * WHEEL_CIRCUMFERENCE, 2),
        "arm": motor.relative_position(ARM_MOTOR),
        "color": _read_color(COLOR_PORT),
        "reflect": _read_reflect(COLOR_PORT),
        "dist_mm": _read_distance(DISTANCE_PORT),
    }
    _LOG.append(row)


def dump_csv():
    """Print the whole buffer as a CSV block that's easy to copy out."""
    print("===BEGIN CSV===")
    print(",".join(_COLS))
    for r in _LOG:
        cells = []
        for c in _COLS:
            v = r.get(c)
            cells.append("" if v is None else str(v))
        print(",".join(cells))
    print("===END CSV=== rows=%d" % len(_LOG))


# ===========================================================================
# ROBOT HELPERS  (unchanged logic from mission_vine.py, + sample() calls)
# ===========================================================================
def teeth_rot(rot, a, b):
    return rot * a / b


def degrees_for_distance(distance_cm):
    return int((distance_cm / WHEEL_CIRCUMFERENCE) * 360)


def deg_rot_motor(attach_rot_degree, g1, g2, g3, g4):
    fg_rot = attach_rot_degree / 360.0
    sec_g_rot = teeth_rot(fg_rot, g1, g2)
    third_g_rot = sec_g_rot
    motor_rot = teeth_rot(third_g_rot, g3, g4)
    return motor_rot


def get_heading():
    # Heading in degrees since start of run. Right (clockwise) = positive.
    return -motion_sensor.tilt_angles()[0] / 10


async def turn_to(target_heading, turn_type, velocity=400):
    """Turns until the robot faces target_heading (absolute, degrees)."""
    direction = 1 if target_heading > get_heading() else -1  # 1 = right, -1 = left
    phase = "turn->%s(%s)" % (target_heading, turn_type)

    if turn_type.lower() == 'spin':
        steering_val = 100 * direction
    elif turn_type.lower() == 'pivot':
        steering_val = 50 * direction
    else:
        raise ValueError("turn_type must be 'spin' or 'pivot'")

    while True:
        remaining = (target_heading - get_heading()) * direction
        if remaining <= 0:
            break
        speed = max(80, min(velocity, int(remaining * 15)))
        sample(phase, target=target_heading, error=round(remaining, 1),
               correction=steering_val, cmd_speed=speed)
        motor_pair.move(motor_pair.PAIR_1, steering_val, velocity=speed)
        await runloop.sleep_ms(10)

    motor_pair.stop(motor_pair.PAIR_1, stop=motor.HOLD)
    sample(phase, target=target_heading, force=True)


motor_pair.pair(motor_pair.PAIR_1, port.B, port.A)


async def gyro_straight(motor_degrees, heading, velocity=500, KP=2.0):
    """Drives motor_degrees while holding an absolute heading.
    Use a negative velocity to drive backward (motor_degrees stays positive)."""
    start_degrees = motor.relative_position(port.B)
    max_speed = abs(velocity)
    direction = 1 if velocity > 0 else -1
    phase = "straight h=%s d=%s" % (heading, motor_degrees)

    while True:
        traveled = abs(motor.relative_position(port.B) - start_degrees)
        remaining = motor_degrees - traveled
        if remaining <= 0:
            break

        speed = min(max_speed, 150 + traveled * 3, 100 + remaining * 2)

        error = heading - get_heading()
        correction = round(error * KP) * direction
        correction = max(min(correction, 50), -50)

        sample(phase, target=heading, error=round(error, 1),
               correction=correction, cmd_speed=int(speed * direction))
        motor_pair.move(motor_pair.PAIR_1, correction, velocity=int(speed * direction))
        await runloop.sleep_ms(10)

    motor_pair.stop(motor_pair.PAIR_1, stop=motor.SMART_BRAKE)
    sample(phase, target=heading, force=True)


async def arm_to(attach_angle, velocity, g1=28, g2=12, g3=20, g4=12):
    """Moves the arm to an angle measured from the ground (0 = on the ground, negative = up)."""
    phase = "arm->%s" % attach_angle
    sample(phase, force=True)
    target = round(deg_rot_motor(attach_angle, g1, g2, g3, g4) * 360)
    await motor.run_to_relative_position(port.C, target, velocity, stop=motor.HOLD)
    sample(phase, force=True)


# ===========================================================================
# MAIN PROGRAM
# ===========================================================================
async def main():
    try:
        await motor.run_for_time(port.C, 300, 150)
        motor.reset_relative_position(port.C, 0)

        motion_sensor.reset_yaw(0)
        await runloop.until(motion_sensor.stable)
        sample("start", force=True)

        await arm_to(-90, 350)
        await gyro_straight(degrees_for_distance(37), heading=0)
        await turn_to(45, 'spin')
        await gyro_straight(degrees_for_distance(25), heading=45)
        await turn_to(90, 'pivot')
        await gyro_straight(degrees_for_distance(5), heading=90)
        await turn_to(0, 'pivot')
        await arm_to(-40, 350)
        await gyro_straight(degrees_for_distance(10), heading=0, velocity=100)
        await arm_to(-90, 400)
        await gyro_straight(degrees_for_distance(16), heading=0, velocity=-300)
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
    finally:
        # Always dump what we recorded, even if the run is stopped early.
        dump_csv()


runloop.run(main())

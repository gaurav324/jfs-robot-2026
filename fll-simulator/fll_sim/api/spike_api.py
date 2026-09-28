"""
A simulated version of the LEGO SPIKE Prime `spike` Python module.

Kids write their FLL robot code against `from spike import ...` exactly as they
would in the SPIKE app; here those classes drive the SimContext instead of a
real hub. Only the commonly used, blocking-style API is implemented (the style
most FLL teams use). Unknown extras are stubbed so programs still run.

The active SimContext is injected via set_context() before the user's code runs.
"""

import math

_CTX = None


def set_context(ctx):
    global _CTX
    _CTX = ctx


def _ctx():
    if _CTX is None:
        raise RuntimeError("No simulation context is active.")
    return _CTX


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _clamp(v, lo, hi):
    return max(lo, min(hi, v))


def _speed_to_cmps(speed_pct):
    return (speed_pct / 100.0) * _ctx().cfg.full_speed_cmps


def _steering_speeds(steering, speed):
    """Convert SPIKE (steering, speed) into (left%, right%).
    steering 0 -> straight; 50 -> pivot on one wheel; 100 -> spin in place."""
    steering = _clamp(steering, -100, 100)
    if steering >= 0:            # turn right (clockwise)
        left = speed
        right = speed * (1 - steering / 50.0)
    else:                        # turn left
        right = speed
        left = speed * (1 + steering / 50.0)
    return left, right


def _distance_to_seconds(amount, unit, left_pct, right_pct):
    """How long to run so the robot covers `amount` of `unit`."""
    cfg = _ctx().cfg
    vL = _speed_to_cmps(left_pct)
    vR = _speed_to_cmps(right_pct)
    v_center = 0.5 * (vL + vR)
    v_outer = max(abs(vL), abs(vR))
    unit = (unit or "cm").lower()
    if unit == "seconds":
        return float(amount)
    if unit in ("cm", "in", "inches"):
        dist = amount * (2.54 if unit != "cm" else 1.0)
        return abs(dist) / abs(v_center) if abs(v_center) > 1e-6 else 0.0
    if unit in ("rotations", "degrees"):
        rot = amount if unit == "rotations" else amount / 360.0
        wheel_dist = rot * cfg.circumference_cm
        return abs(wheel_dist) / abs(v_outer) if abs(v_outer) > 1e-6 else 0.0
    return abs(amount) / abs(v_center) if abs(v_center) > 1e-6 else 0.0


# ---------------------------------------------------------------------------
# Motor pair (drive base)
# ---------------------------------------------------------------------------
class MotorPair:
    def __init__(self, left_port, right_port):
        self.left_port = left_port
        self.right_port = right_port
        self._default_speed = 50
        # cm the robot moves per wheel rotation; defaults to circumference
        self._cm_per_rotation = None
        # register drive ports so their encoders turn while driving
        _ctx().set_drive_ports(left_port, right_port)

    def set_default_speed(self, speed):
        self._default_speed = speed

    def set_motor_rotation(self, amount, unit="cm"):
        # amount of distance travelled per one wheel rotation
        self._cm_per_rotation = amount * (2.54 if unit in ("in", "inches") else 1.0)

    def _apply_cmps(self, left_pct, right_pct):
        _ctx().set_drive(_speed_to_cmps(left_pct), _speed_to_cmps(right_pct))

    def move(self, amount, unit="cm", steering=0, speed=None):
        speed = self._default_speed if speed is None else speed
        left, right = _steering_speeds(steering, speed)
        dur = _distance_to_seconds(amount, unit, left, right)
        _ctx().log("drive", "move %.1f %s (steering=%s speed=%s)"
                    % (amount, unit, steering, speed))
        self._apply_cmps(left, right)
        _ctx().advance(dur)
        _ctx().stop_drive()

    def move_tank(self, amount, unit="cm", left_speed=0, right_speed=0):
        dur = _distance_to_seconds(amount, unit, left_speed, right_speed)
        _ctx().log("drive", "move_tank %.1f %s (L=%s R=%s)"
                    % (amount, unit, left_speed, right_speed))
        self._apply_cmps(left_speed, right_speed)
        _ctx().advance(dur)
        _ctx().stop_drive()

    def start(self, steering=0, speed=None):
        speed = self._default_speed if speed is None else speed
        left, right = _steering_speeds(steering, speed)
        self._apply_cmps(left, right)

    def start_tank(self, left_speed=0, right_speed=0):
        self._apply_cmps(left_speed, right_speed)

    def start_at_power(self, power, steering=0):
        self.start(steering, power)

    def start_tank_at_power(self, left_power, right_power):
        self.start_tank(left_power, right_power)

    def stop(self):
        _ctx().stop_drive()


# ---------------------------------------------------------------------------
# Single motor (attachments, or a wheel)
# ---------------------------------------------------------------------------
class Motor:
    def __init__(self, port):
        self.port = port
        self._default_speed = 100
        _ctx().motor(port)

    def set_default_speed(self, speed):
        self._default_speed = speed

    def _run_degrees(self, degrees, speed):
        m = _ctx().motor(self.port)
        dps = (speed / 100.0) * 1000.0  # ~1000 deg/s at 100%
        if dps == 0:
            return
        dur = abs(degrees) / abs(dps)
        m["vel_dps"] = math.copysign(dps, degrees)
        _ctx().log("motor", "%s run %.0f deg @ %s%%" % (self.port, degrees, speed))
        _ctx().advance(dur)
        m["vel_dps"] = 0.0

    def run_for_degrees(self, degrees, speed=None):
        self._run_degrees(degrees, self._default_speed if speed is None else speed)

    def run_for_rotations(self, rotations, speed=None):
        self._run_degrees(rotations * 360.0,
                          self._default_speed if speed is None else speed)

    def run_for_seconds(self, seconds, speed=None):
        speed = self._default_speed if speed is None else speed
        m = _ctx().motor(self.port)
        m["vel_dps"] = (speed / 100.0) * 1000.0
        _ctx().log("motor", "%s run %.1fs @ %s%%" % (self.port, seconds, speed))
        _ctx().advance(seconds)
        m["vel_dps"] = 0.0

    def run_to_position(self, degrees, direction="shortest path", speed=None):
        speed = self._default_speed if speed is None else speed
        m = _ctx().motor(self.port)
        cur = m["pos"] % 360.0
        target = degrees % 360.0
        delta = (target - cur)
        if direction == "clockwise":
            delta = delta % 360.0
        elif direction == "counterclockwise":
            delta = -((-delta) % 360.0)
        else:  # shortest path
            delta = (delta + 180) % 360 - 180
        self._run_degrees(delta, speed)

    def start(self, speed=None):
        speed = self._default_speed if speed is None else speed
        _ctx().motor(self.port)["vel_dps"] = (speed / 100.0) * 1000.0

    def stop(self):
        _ctx().motor(self.port)["vel_dps"] = 0.0

    def get_position(self):
        return int(_ctx().motor(self.port)["pos"] % 360)

    def get_degrees_counted(self):
        return int(_ctx().motor(self.port)["pos"])

    def get_speed(self):
        return int(_ctx().motor(self.port)["vel_dps"] / 10.0)


# ---------------------------------------------------------------------------
# Sensors
# ---------------------------------------------------------------------------
class ColorSensor:
    def __init__(self, port):
        self.port = port

    def get_color(self):
        from .. engine.context import _nearest_color_name
        return _nearest_color_name(_ctx().color_at_sensor(self.port))

    def get_reflected_light(self):
        from .. engine.context import _reflected_of
        return int(_reflected_of(_ctx().color_at_sensor(self.port)))

    def get_ambient_light(self):
        return 0

    def get_rgb_intensity(self):
        r, g, b = _ctx().color_at_sensor(self.port)
        # SPIKE returns 0-1024-ish; scale rgb 0-255 up
        return (int(r * 4), int(g * 4), int(b * 4), int((r + g + b) / 3 * 4))

    def wait_until_color(self, color):
        _wait_until(lambda: self.get_color() == color)

    def wait_for_new_color(self, ignore=None):
        start = self.get_color()
        _wait_until(lambda: self.get_color() != start)
        return self.get_color()


class DistanceSensor:
    def __init__(self, port):
        self.port = port

    def _dist_cm(self):
        px, py = _ctx().sensor_position(self.port)
        return _ctx().board.ray_distance(px, py, _ctx().heading)

    def get_distance_cm(self, short_range=False):
        return self._dist_cm()

    def get_distance_inches(self, short_range=False):
        d = self._dist_cm()
        return None if d is None else round(d / 2.54, 1)

    def get_distance_percentage(self):
        d = self._dist_cm()
        return 100 if d is None else int(_clamp(d / 200.0 * 100, 0, 100))

    def wait_for_distance_closer_than(self, distance, unit="cm", short_range=False):
        cm = distance * (2.54 if unit in ("in", "inches") else 1.0)
        _wait_until(lambda: (self._dist_cm() or 1e9) < cm)

    def wait_for_distance_farther_than(self, distance, unit="cm", short_range=False):
        cm = distance * (2.54 if unit in ("in", "inches") else 1.0)
        _wait_until(lambda: (self._dist_cm() or 1e9) > cm)

    def light_up_all(self, brightness=100):
        pass

    def light_up(self, *a, **k):
        pass


class ForceSensor:
    """No physical touch in the sim; reports 'not pressed' unless you set it."""
    def __init__(self, port):
        self.port = port

    def is_pressed(self):
        return False

    def get_force_newton(self):
        return 0.0

    def get_force_percentage(self):
        return 0

    def wait_until_pressed(self):
        raise RuntimeError("ForceSensor.wait_until_pressed() can't be satisfied "
                           "in the simulator (no physical button).")

    def wait_until_released(self):
        return


class MotionSensor:
    """The hub's built-in gyro / accelerometer."""
    def get_yaw_angle(self):
        return int(round(_ctx().yaw()))

    def get_pitch_angle(self):
        return 0

    def get_roll_angle(self):
        return 0

    def reset_yaw_angle(self):
        _ctx().reset_yaw()

    def get_gesture(self):
        return None

    def get_orientation(self):
        return "front"

    def wait_for_new_gesture(self):
        return None

    def wait_for_new_orientation(self):
        return "front"


# ---------------------------------------------------------------------------
# Hub sub-devices (mostly logged)
# ---------------------------------------------------------------------------
class LightMatrix:
    def show_image(self, image, brightness=100):
        _ctx().log("hub", "light_matrix.show_image(%r)" % image)

    def write(self, text):
        _ctx().log("hub", "light_matrix.write(%r)" % text)

    def set_pixel(self, x, y, brightness=100):
        pass

    def off(self):
        pass


class StatusLight:
    def on(self, color="white"):
        _ctx().log("hub", "status_light.on(%r)" % color)

    def off(self):
        pass


class Speaker:
    def beep(self, note=60, seconds=0.2):
        _ctx().log("hub", "beep(note=%s, %ss)" % (note, seconds))

    def start_beep(self, note=60):
        pass

    def stop(self):
        pass

    def set_volume(self, volume):
        pass


class Button:
    def __init__(self, name="left"):
        self.name = name

    def is_pressed(self):
        return False

    def was_pressed(self):
        return False

    def wait_until_pressed(self):
        raise RuntimeError("Hub button can't be pressed in the simulator.")

    def wait_until_released(self):
        return


class PrimeHub:
    def __init__(self):
        self.light_matrix = LightMatrix()
        self.status_light = StatusLight()
        self.speaker = Speaker()
        self.motion_sensor = MotionSensor()
        self.left_button = Button("left")
        self.right_button = Button("right")

    def __repr__(self):
        return "PrimeHub(sim)"


# ---------------------------------------------------------------------------
# waiting helper shared with spike.control
# ---------------------------------------------------------------------------
def _wait_until(predicate, step=0.02, max_wait=60.0):
    """Advance the sim in small steps until predicate() is true."""
    ctx = _ctx()
    waited = 0.0
    while not predicate():
        ctx.check_abort()
        ctx.advance(step)
        waited += step
        if waited > max_wait:
            raise RuntimeError("wait_until timed out (condition never became true).")

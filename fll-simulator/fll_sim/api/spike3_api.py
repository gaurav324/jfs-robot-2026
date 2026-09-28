"""
Simulated SPIKE Prime **SPIKE 3 / new** Python API (the `hub`, `motor`,
`motor_pair`, `runloop`, `color_sensor`, `distance_sensor`, `force_sensor`,
`color`, `port` modules used by the current SPIKE app).

This is the async/`runloop` style. Motion functions are coroutines you `await`;
we run them with a tiny driver that steps the coroutine while advancing the same
SimContext the blocking `spike` API uses.

Conventions matched to the real hardware:
  * velocities are in degrees/second (of the wheel/motor)
  * distances passed as motor `degrees`
  * distance_sensor.distance() returns millimeters, or -1 when nothing is seen
  * motion_sensor.tilt_angles() returns (yaw, pitch, roll) in DECIDEGREES,
    with yaw POSITIVE counter-clockwise (a right/clockwise turn is negative)
"""

import types

from . import spike_api
from ..engine.context import _nearest_color_name, _reflected_of


def _ctx():
    return spike_api._ctx()


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _clamp(v, lo, hi):
    return max(lo, min(hi, v))


def _cmps(velocity_dps):
    """Wheel velocity in deg/s -> linear cm/s using the configured wheel."""
    return (velocity_dps / 360.0) * _ctx().cfg.circumference_cm


def _steer_ratios(steering):
    """steering -100..100 -> (left_ratio, right_ratio).
    0 = straight, 50 = pivot on a wheel, 100 = spin in place (same mapping the
    real MotorPair uses; positive steering turns the robot right/clockwise)."""
    steering = _clamp(steering, -100, 100)
    if steering >= 0:
        return 1.0, 1.0 - steering / 50.0
    return 1.0 + steering / 50.0, 1.0


def _wrap180(a):
    a = (a + 180.0) % 360.0 - 180.0
    return a


# ---------------------------------------------------------------------------
# port  (from hub import port  /  import port)
# ---------------------------------------------------------------------------
def _build_port():
    m = types.ModuleType("port")
    for name in "ABCDEF":
        setattr(m, name, name)
    return m


# ---------------------------------------------------------------------------
# hub.motion_sensor
# ---------------------------------------------------------------------------
class MotionSensor3:
    def reset_yaw(self, angle=0):
        # make tilt_angles()[0] read `angle` (decidegrees) right now
        _ctx()._yaw_offset = _ctx().heading + (angle / 10.0)

    def tilt_angles(self):
        raw = _wrap180(_ctx().heading - _ctx()._yaw_offset)
        yaw = -raw                      # CCW positive
        return (int(round(yaw * 10)), 0, 0)

    def stable(self):
        c = _ctx()
        moving = abs(c.vL) + abs(c.vR) > 1e-6 or any(
            abs(mm["vel_dps"]) > 1e-6 for mm in c.motors.values())
        return not moving

    def angular_velocity(self, *a, **k):
        return (0, 0, 0)

    def acceleration(self, *a, **k):
        return (0, 0, 981)

    def gesture(self):
        return None

    def up(self):
        return 0

    def quaternion(self):
        return (1.0, 0.0, 0.0, 0.0)

    def reset_tap_count(self):
        pass

    def tap_count(self):
        return 0


# ---------------------------------------------------------------------------
# hub  (light_matrix / button / light / sound are mostly logged)
# ---------------------------------------------------------------------------
class _LightMatrix3:
    def show_image(self, image):
        _ctx().log("hub", "light_matrix.show_image(%r)" % image)

    def write(self, text):
        _ctx().log("hub", "light_matrix.write(%r)" % text)

    def clear(self):
        pass

    def set_pixel(self, x, y, intensity=100):
        pass


class _Sound3:
    def beep(self, freq=440, duration=500, volume=100):
        _ctx().log("hub", "sound.beep(%s Hz, %s ms)" % (freq, duration))

    def stop(self):
        pass


class _Light3:
    def color(self, color):
        _ctx().log("hub", "light.color(%r)" % color)


class _Button3:
    def pressed(self, button):
        return 0


def _build_hub(port_mod):
    m = types.ModuleType("hub")
    m.motion_sensor = MotionSensor3()
    m.light_matrix = _LightMatrix3()
    m.sound = _Sound3()
    m.light = _Light3()
    m.button = _Button3()
    m.port = port_mod
    # button/orientation constants
    m.LEFT, m.RIGHT, m.CENTER = 0, 1, 2
    return m


# ---------------------------------------------------------------------------
# motor
# ---------------------------------------------------------------------------
async def _motor_run_for_degrees(port, degrees, velocity, stop=1, acceleration=1000,
                                 deceleration=1000):
    m = _ctx().motor(port)
    v = abs(velocity)
    if v == 0:
        return 0
    sign = 1 if degrees >= 0 else -1
    m["vel_dps"] = sign * v
    _ctx().log("motor", "port %s run_for_degrees(%s) @ %s dps" % (port, degrees, velocity))
    _ctx().advance(abs(degrees) / v)
    m["vel_dps"] = 0.0
    return 0  # motor.READY


async def _motor_run_for_time(port, duration, velocity, stop=1, **k):
    m = _ctx().motor(port)
    m["vel_dps"] = velocity
    _ctx().log("motor", "port %s run_for_time(%s ms) @ %s dps" % (port, duration, velocity))
    _ctx().advance(duration / 1000.0)
    m["vel_dps"] = 0.0
    return 0


async def _motor_run_to_relative_position(port, position, velocity, stop=1, **k):
    m = _ctx().motor(port)
    await _motor_run_for_degrees(port, position - m["pos"], velocity, stop)
    return 0


async def _motor_run_to_absolute_position(port, position, velocity, stop=1, direction=None, **k):
    m = _ctx().motor(port)
    cur = m["pos"] % 360
    delta = (position - cur + 180) % 360 - 180
    await _motor_run_for_degrees(port, delta, velocity, stop)
    return 0


def _build_motor():
    m = types.ModuleType("motor")
    # stop constants
    m.COAST, m.BRAKE, m.HOLD, m.CONTINUE, m.SMART_COAST, m.SMART_BRAKE = 0, 1, 2, 3, 4, 5
    # run status constants
    m.READY, m.RUNNING, m.STALLED, m.CANCELED, m.ERROR, m.DISCONNECTED = 0, 1, 2, 3, 4, 5
    m.run_for_degrees = _motor_run_for_degrees
    m.run_for_time = _motor_run_for_time
    m.run_to_relative_position = _motor_run_to_relative_position
    m.run_to_absolute_position = _motor_run_to_absolute_position
    m.run = lambda port, velocity, **k: _ctx().motor(port).__setitem__("vel_dps", velocity)
    m.stop = lambda port, stop=1, **k: _ctx().motor(port).__setitem__("vel_dps", 0.0)
    m.velocity = lambda port: int(_ctx().motor(port)["vel_dps"])
    m.absolute_position = lambda port: int(_ctx().motor(port)["pos"] % 360)
    m.relative_position = lambda port: int(_ctx().motor(port)["pos"])
    m.reset_relative_position = lambda port, position: _ctx().motor(port).__setitem__("pos", float(position))
    return m


# ---------------------------------------------------------------------------
# motor_pair
# ---------------------------------------------------------------------------
_PAIRS = {}


def _mp_pair(pair, left_port, right_port):
    _PAIRS[pair] = (left_port, right_port)
    _ctx().set_drive_ports(left_port, right_port)


def _mp_move(pair, steering, velocity=360, acceleration=1000):
    lr, rr = _steer_ratios(steering)
    base = _cmps(velocity)
    _ctx().set_drive(base * lr, base * rr)


def _mp_move_tank(pair, left_velocity, right_velocity, acceleration=1000):
    _ctx().set_drive(_cmps(left_velocity), _cmps(right_velocity))


def _mp_stop(pair=None, stop=1):
    _ctx().stop_drive()


async def _mp_move_for_degrees(pair, degrees, steering, velocity=360, stop=1,
                               acceleration=1000, deceleration=1000):
    lr, rr = _steer_ratios(steering)
    base = _cmps(velocity)
    sign = 1 if degrees >= 0 else -1
    _ctx().log("drive", "move_for_degrees(%s deg, steer=%s, vel=%s)"
               % (degrees, steering, velocity))
    _ctx().set_drive(sign * base * lr, sign * base * rr)
    if velocity:
        _ctx().advance(abs(degrees) / abs(velocity))
    _ctx().stop_drive()
    return 0  # motor.READY


async def _mp_move_for_time(pair, duration, steering, velocity=360, stop=1, **k):
    lr, rr = _steer_ratios(steering)
    base = _cmps(velocity)
    _ctx().set_drive(base * lr, base * rr)
    _ctx().advance(duration / 1000.0)
    _ctx().stop_drive()
    return 0


async def _mp_move_tank_for_degrees(pair, degrees, left_velocity, right_velocity, stop=1, **k):
    vmax = max(abs(left_velocity), abs(right_velocity)) or 1
    _ctx().set_drive(_cmps(left_velocity), _cmps(right_velocity))
    _ctx().advance(abs(degrees) / vmax)
    _ctx().stop_drive()
    return 0


def _build_motor_pair():
    m = types.ModuleType("motor_pair")
    m.PAIR_1, m.PAIR_2, m.PAIR_3 = 0, 1, 2
    m.pair = _mp_pair
    m.unpair = lambda pair: _PAIRS.pop(pair, None)
    m.move = _mp_move
    m.move_tank = _mp_move_tank
    m.stop = _mp_stop
    m.move_for_degrees = _mp_move_for_degrees
    m.move_for_time = _mp_move_for_time
    m.move_tank_for_degrees = _mp_move_tank_for_degrees
    return m


# ---------------------------------------------------------------------------
# color, color_sensor, distance_sensor, force_sensor
# ---------------------------------------------------------------------------
def _build_color():
    m = types.ModuleType("color")
    # constants are the same strings the sim uses internally
    for name in ("BLACK", "WHITE", "RED", "GREEN", "BLUE", "YELLOW",
                 "MAGENTA", "CYAN", "VIOLET", "ORANGE", "AZURE"):
        setattr(m, name, name.lower())
    m.UNKNOWN = None
    return m


def _build_color_sensor():
    m = types.ModuleType("color_sensor")
    m.color = lambda port: _nearest_color_name(_ctx().color_at_sensor(port))
    m.reflection = lambda port: int(_reflected_of(_ctx().color_at_sensor(port)))
    def _rgbi(port):
        r, g, b = _ctx().color_at_sensor(port)
        return (int(r * 4), int(g * 4), int(b * 4), int((r + g + b) / 3 * 4))
    m.rgbi = _rgbi
    return m


def _build_distance_sensor():
    m = types.ModuleType("distance_sensor")
    def _distance(port, raw_unfiltered=False):
        px, py = _ctx().sensor_position(port)
        cm = _ctx().board.ray_distance(px, py, _ctx().heading)
        return -1 if cm is None else int(round(cm * 10))  # mm, -1 if none
    m.distance = _distance
    m.enable_lights = lambda *a, **k: None
    return m


def _build_force_sensor():
    m = types.ModuleType("force_sensor")
    m.force = lambda port: 0
    m.pressed = lambda port: False
    m.raw = lambda port: 0
    return m


# ---------------------------------------------------------------------------
# runloop  (the tiny async driver)
# ---------------------------------------------------------------------------
def _drive(coro):
    """Run a coroutine to completion. Our awaitables never truly suspend (all
    sim work is synchronous), so a single .send() usually finishes it; we loop
    defensively in case an awaitable yields."""
    try:
        while True:
            coro.send(None)
            _ctx().check_abort()
    except StopIteration:
        return


def _runloop_run(*functions):
    for coro in functions:
        _drive(coro)


async def _runloop_sleep_ms(duration):
    _ctx().advance(max(0, duration) / 1000.0)


async def _runloop_until(condition, timeout_ms=None):
    waited = 0.0
    while not condition():
        _ctx().advance(0.02)
        waited += 0.02
        if timeout_ms is not None and waited * 1000 > timeout_ms:
            return
        if waited > 60:
            return


def _build_runloop():
    m = types.ModuleType("runloop")
    m.run = _runloop_run
    m.sleep_ms = _runloop_sleep_ms
    m.until = _runloop_until
    return m


def _build_app():
    """Minimal `app` module (from app import sound) — logged."""
    m = types.ModuleType("app")

    async def _play(name, *a, **k):
        _ctx().log("hub", "app.sound.play(%r)" % name)
    snd = types.ModuleType("app.sound")
    snd.play = _play
    m.sound = snd
    return m


# ---------------------------------------------------------------------------
# assemble everything
# ---------------------------------------------------------------------------
def build_modules():
    """Return {import_name: module} for all SPIKE 3 modules."""
    port_mod = _build_port()
    hub = _build_hub(port_mod)
    return {
        "hub": hub,
        "port": port_mod,
        "motor": _build_motor(),
        "motor_pair": _build_motor_pair(),
        "color": _build_color(),
        "color_sensor": _build_color_sensor(),
        "distance_sensor": _build_distance_sensor(),
        "force_sensor": _build_force_sensor(),
        "runloop": _build_runloop(),
        "app": _build_app(),
    }

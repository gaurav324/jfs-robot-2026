"""
Core simulation engine for the FLL BIOGLOW Robot Lab simulator.

Coordinate system (matches how kids think about a mat and the SPIKE gyro):
  * Units are centimeters.
  * Origin (0, 0) is the bottom-left corner of the mat.
  * +X points right, +Y points up.
  * Heading 0 means the robot points "up" (+Y, away from the driver).
  * Heading increases CLOCKWISE (turning right is positive), like the SPIKE
    gyro's yaw angle. Heading is stored in degrees.

The engine uses a differential-drive (two independently driven wheels) model.
Everything the pasted user code does flows through a single SimContext, which
records a timeline of frames the browser then animates.
"""

import math
import time


class AbortSimulation(Exception):
    """Raised when a run exceeds its time budget (e.g. an infinite loop)."""


# ---------------------------------------------------------------------------
# Colors: name <-> rgb, plus a "reflected light" brightness (0-100).
# These are the colors the SPIKE color sensor can report.
# ---------------------------------------------------------------------------
COLOR_RGB = {
    "black": (0, 0, 0),
    "white": (255, 255, 255),
    "red": (220, 40, 40),
    "green": (40, 170, 90),
    "blue": (40, 110, 220),
    "yellow": (245, 210, 40),
    "magenta": (210, 60, 170),
    "cyan": (60, 200, 210),
    "violet": (150, 90, 220),
    "orange": (240, 140, 40),
    "brown": (140, 90, 50),
    "gray": (140, 140, 140),
    "grey": (140, 140, 140),
}


def _rgb_of(color):
    """Accept a color name or an [r,g,b] list; return an (r,g,b) tuple."""
    if isinstance(color, str):
        return COLOR_RGB.get(color.lower(), (128, 128, 128))
    if isinstance(color, (list, tuple)) and len(color) == 3:
        return tuple(int(c) for c in color)
    return (128, 128, 128)


def _reflected_of(rgb):
    """Perceived brightness 0-100 (what the reflected-light sensor sees)."""
    r, g, b = rgb
    return round((0.299 * r + 0.587 * g + 0.114 * b) / 255.0 * 100.0, 1)


def _nearest_color_name(rgb):
    """Closest named SPIKE color to an rgb tuple."""
    best, best_d = "black", 1e18
    for name, ref in COLOR_RGB.items():
        if name == "grey":
            continue
        d = sum((a - b) ** 2 for a, b in zip(rgb, ref))
        if d < best_d:
            best, best_d = name, d
    return best


class Board:
    """The mat: size, background, colored regions and obstacles."""

    def __init__(self, cfg):
        self.width = float(cfg.get("width_cm", 236.2))
        self.height = float(cfg.get("height_cm", 114.3))
        self.base_color = cfg.get("base_color", "white")
        # Staging space around the mat (real table has room beside the field to
        # park attachments; extensions can swing into it while moving). The
        # robot may drive into these margins; the table walls are the real edge.
        m = cfg.get("margins", {}) or {}
        self.margin_left = float(m.get("left", 0))
        self.margin_right = float(m.get("right", 0))
        self.margin_top = float(m.get("top", 0))
        self.margin_bottom = float(m.get("bottom", 0))
        self.table_color = cfg.get("table_color", "gray")
        # regions: [{shape:'rect', x,y,w,h, color}]  (x,y = bottom-left)
        self.regions = cfg.get("regions", [])
        # obstacles the distance sensor can hit: rect or circle
        self.obstacles = cfg.get("obstacles", [])
        self.background_image = cfg.get("background_image")  # optional data URL/path
        # decorative zones (home/launch areas): drawn but not sensed
        self.zones = cfg.get("zones", [])
        self.grid_cm = float(cfg.get("grid_cm", 20))
        self.grid_labels = bool(cfg.get("grid_labels", False))
        # True when the background image already draws the grid (don't overlay)
        self.image_grid = bool(cfg.get("image_grid", False))

    # world bounds = the whole table interior (mat + staging margins)
    @property
    def min_x(self):
        return -self.margin_left

    @property
    def max_x(self):
        return self.width + self.margin_right

    @property
    def min_y(self):
        return -self.margin_bottom

    @property
    def max_y(self):
        return self.height + self.margin_top

    def color_at(self, x, y):
        """RGB of the topmost region containing (x, y), else the base color."""
        # Later regions in the list win (drawn on top).
        for reg in reversed(self.regions):
            if reg.get("shape", "rect") == "rect":
                rx, ry = reg["x"], reg["y"]
                if rx <= x <= rx + reg["w"] and ry <= y <= ry + reg["h"]:
                    return _rgb_of(reg.get("color", "black"))
            elif reg.get("shape") == "circle":
                if math.hypot(x - reg["x"], y - reg["y"]) <= reg["r"]:
                    return _rgb_of(reg.get("color", "black"))
        # inside the mat -> base color; in the staging margins -> table surface
        if 0 <= x <= self.width and 0 <= y <= self.height:
            return _rgb_of(self.base_color)
        return _rgb_of(self.table_color)

    def ray_distance(self, x, y, heading_deg, max_cm=200.0):
        """Cast a ray from (x,y) along heading; return distance to the first
        obstacle or wall in cm, or None if nothing within max_cm."""
        h = math.radians(heading_deg)
        dx, dy = math.sin(h), math.cos(h)  # heading 0 -> +Y, clockwise positive
        step = 0.5
        d = 0.0
        while d <= max_cm:
            px, py = x + dx * d, y + dy * d
            # table wall? (the outer edge of the whole table, incl. staging)
            if px < self.min_x or px > self.max_x or py < self.min_y or py > self.max_y:
                return round(d, 1) if d > 0 else 0.0
            # obstacle?
            for ob in self.obstacles:
                if ob.get("shape", "rect") == "rect":
                    if ob["x"] <= px <= ob["x"] + ob["w"] and ob["y"] <= py <= ob["y"] + ob["h"]:
                        return round(d, 1)
                elif ob.get("shape") == "circle":
                    if math.hypot(px - ob["x"], py - ob["y"]) <= ob["r"]:
                        return round(d, 1)
            d += step
        return None


class RobotConfig:
    """Physical parameters of the robot, all adjustable from the UI."""

    def __init__(self, cfg):
        cfg = cfg or {}
        self.wheel_diameter_cm = float(cfg.get("wheel_diameter_cm", 5.6))
        self.axle_track_cm = float(cfg.get("axle_track_cm", 11.2))
        # linear speed of a wheel when a motor runs at 100%
        self.full_speed_cmps = float(cfg.get("full_speed_cmps", 40.0))
        # robot body size (for drawing / collision feel)
        self.body_length_cm = float(cfg.get("body_length_cm", 18.0))
        self.body_width_cm = float(cfg.get("body_width_cm", 14.0))
        # start pose
        self.start_x = float(cfg.get("start_x", 30.0))
        self.start_y = float(cfg.get("start_y", 20.0))
        self.start_heading = float(cfg.get("start_heading", 0.0))
        # left/right drive motor ports (first = left, second = right)
        self.left_port = cfg.get("left_port", "A")
        self.right_port = cfg.get("right_port", "B")
        # per-port sensor mounting offsets from robot center, in robot frame:
        #   forward = +cm toward the front, side = +cm to the right
        # e.g. {"C": {"forward": 9, "side": -3}}
        self.sensor_offsets = cfg.get("sensor_offsets", {})

    @property
    def circumference_cm(self):
        return math.pi * self.wheel_diameter_cm


class SimContext:
    """
    Holds the live robot state and records the timeline. The simulated `spike`
    API objects talk to exactly one SimContext during a run.
    """

    MAX_WALL_SECONDS = 12.0   # real time budget for a run (infinite-loop guard)
    MAX_SIM_SECONDS = 600.0   # simulated-time budget
    DT = 0.01                 # integration step (s)
    FRAME_DT = 1.0 / 30.0     # how often we emit an animation frame (s)

    def __init__(self, robot_cfg, board):
        self.cfg = robot_cfg
        self.board = board

        # pose
        self.x = robot_cfg.start_x
        self.y = robot_cfg.start_y
        self.heading = robot_cfg.start_heading  # degrees, clockwise positive

        # drive wheel linear velocities (cm/s)
        self.vL = 0.0
        self.vR = 0.0

        # gyro baseline (yaw is measured relative to reset point)
        self._yaw_offset = self.heading

        # attachment motors: port -> {"pos": deg, "speed_pct": .., "vel_dps": ..}
        self.motors = {}

        # drive-base motor ports (left, right). Their encoders turn while the
        # motor_pair drives, so encoder-based distance code (e.g. reading
        # motor.relative_position() on a drive port) sees the wheels move.
        self._drive_ports = None

        # timeline
        self.t = 0.0
        self._next_frame_t = 0.0
        self.frames = []      # [{t,x,y,heading,color,reflected,distance,motors}]
        self.path = []        # [[x,y], ...] downsampled trace
        self.events = []      # [{t,type,text}]
        self.console = []     # captured print() lines

        self._start_wall = time.time()
        self.aborted = False

        self._emit_frame()    # initial frame

    # -- guards --------------------------------------------------------------
    def check_abort(self):
        if time.time() - self._start_wall > self.MAX_WALL_SECONDS:
            self.aborted = True
            raise AbortSimulation(
                "Simulation stopped: the program ran too long "
                "(possible infinite loop, or motors never stop)."
            )
        if self.t > self.MAX_SIM_SECONDS:
            self.aborted = True
            raise AbortSimulation("Simulation stopped: reached the time limit.")

    # -- logging -------------------------------------------------------------
    def log(self, kind, text):
        self.events.append({"t": round(self.t, 3), "type": kind, "text": text})

    def print_line(self, text):
        self.console.append(text)
        self.events.append({"t": round(self.t, 3), "type": "print", "text": text})

    # -- sensors -------------------------------------------------------------
    def sensor_position(self, port):
        """World (x,y) of the sensor mounted at `port`, using its offset."""
        off = self.cfg.sensor_offsets.get(str(port), {"forward": 8.0, "side": 0.0})
        fwd = float(off.get("forward", 8.0))
        side = float(off.get("side", 0.0))
        h = math.radians(self.heading)
        # forward unit = (sin h, cos h); right unit = (cos h, -sin h)
        fx, fy = math.sin(h), math.cos(h)
        rx, ry = math.cos(h), -math.sin(h)
        return (self.x + fwd * fx + side * rx, self.y + fwd * fy + side * ry)

    def color_at_sensor(self, port):
        px, py = self.sensor_position(port)
        return self.board.color_at(px, py)

    def yaw(self):
        """Gyro yaw in degrees, wrapped to (-180, 180], relative to last reset."""
        a = (self.heading - self._yaw_offset) % 360.0
        if a > 180.0:
            a -= 360.0
        return round(a, 1)

    def reset_yaw(self):
        self._yaw_offset = self.heading

    # -- motion --------------------------------------------------------------
    def set_drive(self, vL, vR):
        self.vL, self.vR = vL, vR

    def set_drive_ports(self, left_port, right_port):
        """Register the two drive-base motor ports so their encoders advance as
        the robot drives. Encoder-based distance code reads these (a real robot
        knows how far it has gone from its drive motors' rotation counts)."""
        self._drive_ports = (str(left_port), str(right_port))
        self.motor(self._drive_ports[0])   # make sure the encoder entries exist
        self.motor(self._drive_ports[1])

    def stop_drive(self):
        self.vL = self.vR = 0.0

    def advance(self, duration):
        """Integrate the robot forward by `duration` seconds using current
        wheel velocities, emitting animation frames along the way."""
        if duration <= 0:
            return
        end = self.t + duration
        while self.t < end - 1e-9:
            self.check_abort()
            dt = min(self.DT, end - self.t)
            v = 0.5 * (self.vL + self.vR)                    # cm/s forward
            omega = (self.vL - self.vR) / self.cfg.axle_track_cm  # rad/s clockwise
            h = math.radians(self.heading)
            self.x += v * math.sin(h) * dt
            self.y += v * math.cos(h) * dt
            self.heading = (self.heading + math.degrees(omega * dt)) % 360.0

            # advance attachment motors
            for m in self.motors.values():
                if m["vel_dps"]:
                    m["pos"] += m["vel_dps"] * dt

            # advance the drive motors' encoders from the wheel speeds, so code
            # that reads motor.relative_position() on a drive port sees distance
            # accumulate. deg = (linear cm/s / wheel circumference) * 360.
            if self._drive_ports is not None:
                circ = self.cfg.circumference_cm
                if circ > 1e-9:
                    lp, rp = self._drive_ports
                    self.motors[lp]["pos"] += (self.vL / circ) * 360.0 * dt
                    self.motors[rp]["pos"] += (self.vR / circ) * 360.0 * dt

            self.t += dt
            if self.t >= self._next_frame_t:
                self._emit_frame()
                self._next_frame_t += self.FRAME_DT

    def _emit_frame(self):
        # Report the color/reflection under a generic front sensor point so the
        # UI can show a live readout even before any sensor is created.
        px, py = self.sensor_position("C")
        rgb = self.board.color_at(px, py)
        dpx, dpy = self.sensor_position("D")
        dist = self.board.ray_distance(dpx, dpy, self.heading)
        frame = {
            "t": round(self.t, 3),
            "x": round(self.x, 2),
            "y": round(self.y, 2),
            "heading": round(self.heading, 2),
            "color": _nearest_color_name(rgb),
            "reflected": _reflected_of(rgb),
            "distance": dist,
            "motors": {p: round(m["pos"], 1) for p, m in self.motors.items()},
        }
        self.frames.append(frame)
        # downsample the path a little to keep payloads small
        if not self.path or math.hypot(self.x - self.path[-1][0], self.y - self.path[-1][1]) > 0.25:
            self.path.append([round(self.x, 2), round(self.y, 2)])

    # -- attachment motors ---------------------------------------------------
    def motor(self, port):
        if port not in self.motors:
            self.motors[port] = {"pos": 0.0, "vel_dps": 0.0}
        return self.motors[port]

    # -- result --------------------------------------------------------------
    def result(self):
        return {
            "ok": not self.aborted,
            "frames": self.frames,
            "path": self.path,
            "events": self.events,
            "console": self.console,
            "final": {
                "x": round(self.x, 2),
                "y": round(self.y, 2),
                "heading": round(self.heading, 2),
                "sim_time": round(self.t, 2),
            },
        }

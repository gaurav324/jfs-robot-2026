"""
Runs a pasted SPIKE Prime program against the simulator and returns the trace.

We register simulated modules under the names the user's code imports
(`spike`, `spike.control`), redirect print(), and execute the code in a fresh
namespace. A line-level tracer aborts runaway programs.
"""

import builtins
import sys
import time
import traceback
import types

from .engine.context import Board, RobotConfig, SimContext, AbortSimulation
from .api import spike_api, spike_control, spike3_api


def _build_spike_module():
    """Create a module object exposing the SPIKE API classes."""
    mod = types.ModuleType("spike")
    for name in (
        "PrimeHub", "Motor", "MotorPair", "ColorSensor", "DistanceSensor",
        "ForceSensor", "MotionSensor", "LightMatrix", "StatusLight",
        "Speaker", "Button",
    ):
        setattr(mod, name, getattr(spike_api, name))
    mod.control = spike_control  # so `spike.control` resolves
    return mod


def run_code(code, robot_cfg_dict, board_cfg_dict):
    """Execute `code`; return a result dict (see SimContext.result)."""
    board = Board(board_cfg_dict or {})
    cfg = RobotConfig(robot_cfg_dict or {})
    ctx = SimContext(cfg, board)
    spike_api.set_context(ctx)

    spike_module = _build_spike_module()

    # Build the SPIKE 3 (new) modules: hub, motor, motor_pair, runloop, ...
    spike3_modules = spike3_api.build_modules()

    # capture print()
    real_print = builtins.print

    def sim_print(*args, **kwargs):
        sep = kwargs.get("sep", " ")
        ctx.print_line(sep.join(str(a) for a in args))

    injected = {"spike": spike_module, "spike.control": spike_control}
    injected.update(spike3_modules)
    injected["app.sound"] = spike3_modules["app"].sound
    saved_modules = {}
    for key in injected:
        if key in sys.modules:
            saved_modules[key] = sys.modules[key]
    for key, mod in injected.items():
        sys.modules[key] = mod

    error = None
    g = {"__name__": "__main__", "__builtins__": builtins}
    builtins.print = sim_print

    # Line-level tracer so we can interrupt even a pure-Python `while True: pass`
    # (a loop that never calls the robot API). It fires per source line and
    # raises once the wall-clock budget is spent.
    deadline = time.time() + ctx.MAX_WALL_SECONDS
    counter = {"n": 0}

    def tracer(frame, event, arg):
        counter["n"] += 1
        if counter["n"] % 2000 == 0 and time.time() > deadline:
            raise AbortSimulation(
                "Simulation stopped: the program ran too long "
                "(possible infinite loop)."
            )
        return tracer

    try:
        sys.settrace(tracer)
        exec(compile(code, "<robot_program>", "exec"), g, g)
    except AbortSimulation as e:
        error = {"type": "timeout", "message": str(e)}
    except Exception:
        tb = traceback.format_exc()
        # trim our frames from the traceback so kids see their own code
        error = {"type": "error", "message": _friendly_traceback(tb)}
    finally:
        sys.settrace(None)
        builtins.print = real_print
        for key in injected:
            if key in saved_modules:
                sys.modules[key] = saved_modules[key]
            else:
                sys.modules.pop(key, None)
        spike_api.set_context(None)

    result = ctx.result()
    result["error"] = error
    result["ok"] = error is None
    result["board"] = {
        "width": board.width, "height": board.height,
        "base_color": board.base_color, "regions": board.regions,
        "obstacles": board.obstacles, "background_image": board.background_image,
        "zones": board.zones, "grid_cm": board.grid_cm,
        "grid_labels": board.grid_labels, "image_grid": board.image_grid,
        "margins": {"left": board.margin_left, "right": board.margin_right,
                    "top": board.margin_top, "bottom": board.margin_bottom},
        "table_color": board.table_color,
    }
    result["robot"] = {
        "body_length": cfg.body_length_cm, "body_width": cfg.body_width_cm,
        "start_x": cfg.start_x, "start_y": cfg.start_y,
        "start_heading": cfg.start_heading,
    }
    return result


def _friendly_traceback(tb):
    """Keep only the frames from the user's program, not our harness frames."""
    lines = tb.splitlines()
    keep = []
    capture = False
    for ln in lines:
        # a traceback frame header looks like:  File "<robot_program>", line N
        if ln.lstrip().startswith('File "<robot_program>"'):
            capture = True
        if capture:
            keep.append(ln)
    # always include the final "SomeError: message" line
    if lines and (not keep or keep[-1] != lines[-1]):
        keep.append(lines[-1])
    return "\n".join(keep) if keep else tb

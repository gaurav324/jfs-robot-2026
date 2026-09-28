# BIOGLOW Robot Lab Simulator

A friendly, zero-install robot simulator for **FIRST LEGO League (FLL)** teams.
Paste your **SPIKE Prime Python** code, press **Run**, and watch the robot trace
its path across the mat — then tweak wheel size, speed, sensors, and starting
position and try again.

Built for kids to experiment safely without touching the real robot.

## Requirements

- **Python 3.8 or newer.** That's it. No `pip install`, no internet, no build step.
  (macOS and most Linux machines already have Python 3. On Windows, install it
  from python.org and check "Add Python to PATH".)

## Run it

```bash
cd fll-simulator
python3 run.py
```

Your browser opens automatically at `http://127.0.0.1:8000`. (Use `py run.py`
on Windows if `python3` isn't found.)

- `python3 run.py --port 9000` — use a different port
- `python3 run.py --no-browser` — don't auto-open the browser

Press **Ctrl+C** in the terminal to stop.

## What you can do

- **Paste real robot code — both SPIKE APIs work.**
  - **SPIKE 3 (new) API** — the current SPIKE app's async style:
    `from hub import motion_sensor, port`, `import motor`, `import motor_pair`,
    `import runloop`, plus `color_sensor` / `distance_sensor` / `force_sensor` /
    `color`. Write `async def main(): ...` and `runloop.run(main())`; `await`
    `motor_pair.move_for_degrees(...)`, `motor.run_for_degrees(...)`,
    `runloop.sleep_ms(...)`, `runloop.until(...)`.
  - **Legacy `spike` API** — the older blocking style: `PrimeHub`, `MotorPair`,
    `Motor`, `ColorSensor`, `DistanceSensor`, `MotionSensor`, plus
    `spike.control` (`wait_for_seconds`, `wait_until`, `Timer`).

  Units match the real hardware: SPIKE-3 velocities are in **degrees/second**,
  distances in **motor degrees**, `distance_sensor.distance()` in **mm** (`-1`
  when nothing is seen), and `motion_sensor.tilt_angles()` returns
  **decidegrees** with yaw **positive counter-clockwise** (a right turn reads
  negative).
- **See the path.** The robot's route is drawn on the mat and animated. Scrub
  the timeline, change playback speed, toggle the trace and grid.
- **Adjust the robot.** Wheel diameter, axle track (distance between wheels),
  top speed, body size, motor ports, and where each sensor is mounted.
- **Set the start.** Type coordinates, or just click on the mat.
- **Design the board.** Change the mat size, add colored regions (what the
  color sensor sees) and obstacles (what the distance sensor detects), or drop
  in a **photo/scan of your real BIOGLOW mat** as the background to trace over.

## The real 2026-2027 BIOGLOW field

The default board matches the **official BIOGLOW (Founders Edition) robot game
field** from FIRST:

- **Field size: 200 cm × 120 cm** (78.7 in × 47.2 in).
- **20 cm coordinate grid**, columns **A–J** (left→right) and rows **1–6**
  (bottom→top) — the same grid the official *Wireframe & Path Diagram* uses, so
  mission locations line up exactly. `(0, 0)` is the bottom-left corner.
- **Home area** (red arc, bottom-left) and the **Launch area** (blue arc,
  bottom-right). The robot starts in Home by default.
- The backdrop is the **real colored mat art** (from FIRST's official files),
  shown inside a black table frame.
- **Attachment staging areas** (yellow-dashed) sit to the left and right of the
  mat, matching the real table's side space. The robot — and any attachment or
  extension sticking out — can drive into them; the table walls are the real
  boundary the distance sensor sees.

## Seeing output and errors

The **Output & Logs** panel across the bottom is always visible. Every time you
Run, it shows:
- anything your program `print`ed,
- a timestamped list of robot actions (toggle "show robot actions" off to hide),
- and, if the program fails, a red **error banner** naming the exact line in your
  code (e.g. `NameError: name 'speed_typo' is not defined`).

Use **Hide** to collapse it and **Clear** to empty it.

Boards available in the **Board** tab:
- **BIOGLOW 2026-27 (official field)** — real size, grid, and mat art.
- **BIOGLOW practice (lines & sensors)** — same size with practice lines,
  colored targets, and an obstacle, so the color and distance sensors have
  something to detect.

The official source documents are included in `reference/` (Wireframe & Grid,
Field Set-Up Reference Guide, Table Building Instructions). These documents are
© FIRST; they're bundled here only for your own team's practice — please don't
redistribute them.

> Note: the color/distance sensors read the *simulated* regions you define, not
> the pixels of the mat image. On the official-mat board the art is a visual
> reference; use the practice board (or add your own regions) when you want the
> sensors to react to specific lines and models.
- **Read the sensors live.** The Sensors tab shows position, gyro yaw, color,
  reflected light, distance, and attachment-motor angles as the robot moves,
  plus everything your program `print`ed.

Load one of the built-in **examples** (top-right dropdown) to get started:
driving a square with the gyro, following a line, stopping at an obstacle, and
running an attachment arm.

## Tips for the coach

- **Ports:** the first two ports of `MotorPair('A','B')` are the left and right
  drive motors. Give the color sensor and distance sensor their own ports (the
  examples use `'C'` and `'D'`) and set their mounting offset in the Robot tab
  so readings come from where they actually sit on your robot.
- **Turns:** `steering=100` spins in place, `50` pivots on one wheel, `0` drives
  straight. For accurate turns, use the gyro (`hub.motion_sensor`) like the
  square example does.
- **Calibrate to your robot:** measure your real wheel diameter and axle track
  and enter them so distances and turns match the real thing.

## How it works (for the curious)

- `run.py` — launcher; starts a tiny built-in web server and opens the browser.
- `fll_sim/server.py` — standard-library HTTP server + JSON API (no frameworks).
- `fll_sim/api/spike_api.py` — the simulated `spike` module your code imports.
- `fll_sim/engine/context.py` — the physics: a differential-drive model that
  integrates the robot's pose and samples the sensors against the board.
- `fll_sim/simulator.py` — runs your pasted code and records the motion trace.
- `fll_sim/static/` — the browser UI (HTML canvas, no external libraries).
- `fll_sim/boards/` — mat definitions (JSON). `fll_sim/examples/` — sample code.

## Limitations & notes

- It's a **kinematic** simulator: it models where the wheels take the robot, not
  wheel slip, weight, or collisions. Great for planning paths and logic; the
  real robot will still need fine-tuning.
- Both the SPIKE 3 (`runloop`/async) API and the legacy blocking `spike` API are
  supported. In the async API, coroutines are driven to completion synchronously
  — fine for the usual `runloop.run(main())`, but truly concurrent tasks running
  at the same time aren't scheduled in parallel.
- The color/distance sensors read the *simulated* board regions, not the
  background image. Draw regions where your lines and models are.
- Running pasted Python executes it on your computer. Only run code you trust
  (your own team's). A run is stopped automatically after ~12 seconds as a
  safety net against infinite loops.

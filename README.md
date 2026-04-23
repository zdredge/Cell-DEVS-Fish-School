# Fish School Predator Evasion — Cell-DEVS Cadmium Simulation

**Author:** Zachary Dredge — 101197514
**Course:** SYSC 4906G — Carleton University

---

## Overview

This project simulates the emergent formation of fish schools and their
evasion of a predator under water currents, using the **Cell-DEVS** formalism
in the **Cadmium v2** simulation framework. It extends an earlier symmetric
Cell-DEVS model of fish schooling (adapted from Etemad, 2014) with three
additions:

1. **Asymmetric Cell-DEVS** — string-based cell IDs and per-connection
   vicinity factors, replacing the uniform-neighborhood symmetric model.
2. **Predator + evasion behavior** — after Zheng et al. (2005), fish switch
   between three *component behavior patterns* (CBPs): **schooling**,
   **cooperative escape**, and **selfish escape** depending on predator
   proximity. Predators pursue the nearest fish with limited turning and
   confusion-driven target selection.
3. **Water currents** — directional vicinity factors encode current
   assistance (+1.0), opposition (−1.0), or neutrality (0.0) per directed
   connection. Currents bias fish escape-move selection and can stall the
   predator against strong opposing flow.

The grid is **20×20, non-wrapped**. Cell IDs have the form `(col,row)`
(e.g. `(5,3)`). Movement priority when fish compete for the same cell is
**West > East > North > South**.

### Cell state — six fields

| Variable       | Values            | Meaning                                                    |
|----------------|-------------------|------------------------------------------------------------|
| `presence`     | `0` / `5` / `10`  | Empty / Fish / Predator                                    |
| `direction`    | `0`–`4`           | Intended next direction (0=none, 1=E, 2=N, 3=W, 4=S)       |
| `orientation`  | `0`–`4`           | Direction of last movement (same encoding)                 |
| `behavior`     | `0`–`2`           | CBP: 0=schooling, 1=cooperative escape, 2=selfish escape   |
| `predatorDist` | `0`–`6`           | Manhattan distance to nearest predator (0 = none detected) |
| `predatorDir`  | `0`–`4`           | Direction *from which* the predator approaches             |

Logged CSV entries are formatted as
`<presence,direction,orientation,behavior,predatorDist,predatorDir>`.

### Component Behavior Patterns (CBPs)

| predatorDist    | CBP                         | Summary                                                            |
|-----------------|-----------------------------|--------------------------------------------------------------------|
| `0` or `≥ 4`    | **Schooling** (`0`)         | Anchor in school, attract to neighbors, random walk if isolated    |
| `3`             | **Cooperative escape** (`1`)| 70% school cohesion + 30% flee; prefer current-assisted directions |
| `1`–`2`         | **Selfish escape** (`2`)    | Swerve perpendicular to predator; override school anchor           |
| adjacent / same | **Capture**                 | Fish removed                                                       |

### Water current zones

| Rows    | Current direction | Horizontal vicinity |
|---------|-------------------|---------------------|
| 0 – 6   | Eastward          | +1.0 east / −1.0 west |
| 7 – 13  | Calm              | 0.0 all              |
| 14 – 19 | Westward          | −1.0 east / +1.0 west |

Vertical connections carry vicinity `0.0` (current is horizontal only).

---

## File Organization

```
Term-Project/
├── main/
│   ├── main.cpp                        # Entry point + AsymmCell factory
│   └── include/
│       ├── state.hpp                   # CellState (6 fields), Direction enum, JSON parsing
│       ├── fish_cell.hpp               # FishCell : AsymmCell<CellState,double>
│       ├── predator_cell.hpp           # PredatorCell : AsymmCell<CellState,double>
│       └── cell_logic.hpp              # Shared local-computation (schooling, CBPs, pursuit)
├── config/                             # Generated asymmetric Cell-DEVS configs (JSON)
│   ├── schooling[_no_currents]_config.json
│   ├── predator_{east,west,north,south}_config.json
│   ├── selfish_encounter[_no_currents]_config.json
│   ├── coop_{platoon,diagonal,wall}_config.json
│   ├── reluctance_demo[_no_currents]_config.json
│   ├── large_school[_no_currents]_config.json
│   └── current_{stall,wander,coop_fallback,selfish_tiebreak}[_no_currents]_config.json
├── logs/                               # CSV simulation outputs
├── videos/                             # Rendered scenario walkthroughs (.webm)
├── bin/fish_school                     # Compiled simulation executable
├── build/                              # CMake build artifacts (generated)
├── generate_config.py                  # Python generator for the 20×20 asymmetric configs
├── test_fish_school.py                 # Invariant + statistical test harness
├── CMakeLists.txt
├── build_sim.sh
└── README.md
```

---

## Prerequisites

- **C++17** compatible compiler (e.g. `g++`)
- **CMake** 3.16 or later
- **Python 3** (for config generation and the test harness)
- **Cadmium v2** — header-only DEVS simulation library (bundles nlohmann/json)

Cadmium must be available either:
- at `../cadmium_v2/` relative to this project root, **or**
- via the `CADMIUM` environment variable pointing to Cadmium's `include/` directory

```bash
export CADMIUM=/path/to/cadmium_v2/include
```

---

## Compilation Instructions

Use the provided build script to clean, configure, and compile:

```bash
source build_sim.sh
```

This will:
1. Remove any previous `build/` directory and stale `.csv` logs
2. Run `cmake ..` to configure the project
3. Run `make` to compile the `fish_school` executable into `bin/`

Alternatively, build manually:

```bash
mkdir -p build && cd build
cmake ..
make
cd ..
```

---

## Generating Scenario Configs

All 20×20 asymmetric configs are produced by the Python generator. Each
config contains one entry per cell (400 in total) with explicit Von Neumann
range-6 neighborhoods and per-connection vicinity factors.

```bash
# Generate a single scenario
python3 generate_config.py schooling
python3 generate_config.py predator_east
python3 generate_config.py current_coop_fallback

# Generate every scenario
for s in schooling schooling_no_currents \
         predator_east predator_west predator_north predator_south \
         selfish_encounter selfish_encounter_no_currents \
         large_school large_school_no_currents \
         reluctance_demo reluctance_demo_no_currents \
         coop_platoon coop_diagonal coop_wall \
         current_stall current_stall_no_currents \
         current_coop_fallback current_coop_fallback_no_currents \
         current_selfish_tiebreak current_selfish_tiebreak_no_currents \
         current_wander current_wander_no_currents; do
    python3 generate_config.py "$s"
done
```

Outputs are written to `config/<scenario>_config.json`. Every `*_no_currents`
twin is generated with all vicinity factors zeroed out, to isolate the
effect of the water currents from the underlying schooling/evasion logic.

---

## Running the Simulation

Run a scenario by passing a config file path and an optional simulation time
(default `50`) and log path (default `fish_school_log.csv`):

```bash
./bin/fish_school config/<scenario>_config.json [sim_time] [log_path]
```

Examples:

```bash
./bin/fish_school config/schooling_config.json 50
./bin/fish_school config/predator_east_config.json 40 logs/predator_east_log.csv
./bin/fish_school config/reluctance_demo_config.json 60
```

Each run emits a CSV log (`;` delimiter) of every cell's state at each
simulation time step.

### Visualizing results

Use the [Cell-DEVS Web Viewer](https://devssim.carleton.ca/cell-devs-viewer/):

1. Load the scenario config JSON file.
2. Load the corresponding CSV log file.
3. Step through or animate the simulation.

The config files ship with a `viewer` block that provides color breakpoints
for all six state fields:

| Field          | Color coding                                                                        |
|----------------|-------------------------------------------------------------------------------------|
| `presence`     | Grey = empty, Red = fish, Black = predator                                          |
| `direction`    | Green = East, Yellow = North, Blue = West, Pink = South                             |
| `orientation`  | Same palette as `direction`                                                         |
| `behavior`     | Grey = schooling, Orange = cooperative escape, Purple = selfish escape              |
| `predatorDist` | Red (close) → green (far)                                                           |
| `predatorDir`  | Same palette as `direction`                                                         |

Rendered walkthroughs for the main scenarios are stored under `videos/`.

---

## Testing

`test_fish_school.py` drives the simulator across every scenario and
checks a layered set of invariants plus statistical outcomes. All 208
assertions must pass.

```bash
python3 test_fish_school.py
```

The harness covers:

- **Phase A / B — per-scenario invariants**: 6-field state validity,
  empty-cell consistency, grid boundaries, fish monotonicity (only
  decreases via capture), predator conservation, capture traceability,
  CBP correctness, paired predator fields, and movement continuity.
- **Phase C — statistical (`STAT_RUNS=20`)**: capture probability and
  ≥30% open-water capture rate for the reluctance and large-school
  scenarios.
- **Phase D — currents on/off comparisons**: cooperative fallback,
  selfish tiebreak, and wander scenarios are run with and without
  currents to verify the current bias actually changes outcomes.
- **Phase E — aggregate open-water summary**: cross-scenario roll-up of
  capture statistics.

---


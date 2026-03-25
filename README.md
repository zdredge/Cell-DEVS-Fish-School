# Fish School Formation — Cell-DEVS Cadmium Simulation

**Author:** Zachary Dredge — 101197514
**Course:** SYSC4906G

---

## Overview

This project simulates the emergent formation of fish schools using the **Cell-DEVS formalism** implemented in the **Cadmium** simulation framework. It is adapted from Mohammad Etemad's 2014 CD++ model of fish school formation.

Individual fish are modeled as cells on a 10×10 grid. Each fish moves randomly until it detects a neighbor within its Von Neumann viewing radius, at which point it overrides its random movement and swims toward that neighbor to form or join a school. Fish already part of a school become anchored and stop moving.

Each cell tracks three state variables compressed into a single layer:

| Variable | Values | Meaning |
|---|---|---|
| `presence` | `0` / `5` | Empty cell / Fish present |
| `direction` | `0`–`4` | Intended next direction (0=none, 1=E, 2=N, 3=W, 4=S) |
| `orientation` | `0`–`4` | Direction of last movement (same encoding as direction) |

Movement priority when fish compete for the same cell: **West > East > North > South**.

---

## File Organization

```
Fish School/
├── main/
│   ├── main.cpp                        # Simulation entry point
│   └── include/
│       ├── cell.hpp                    # FishCell: local computation function (tau)
│       └── state.hpp                   # FishState struct, Direction enum, JSON parsing
├── config/
│   ├── scenario_1_apart_config.json    # Fish widely spread apart
│   ├── scenario_2_vline_config.json    # Fish arranged in a vertical line
│   ├── scenario_3_hline_config.json    # Fish arranged in a horizontal line
│   ├── scenario_4_cross_config.json    # Fish arranged in a cross pattern
│   ├── scenario_5_diamond_config.json  # Fish arranged in a diamond pattern
│   └── scenario_6_right_angle_config.json  # Fish arranged in a right angle
├── logs/
│   ├── scenario_1_fish_school_log.csv  # Simulation output for scenario 1
│   ├── scenario_2_fish_school_log.csv  # Simulation output for scenario 2
│   ├── scenario_3_fish_school_log.csv  # Simulation output for scenario 3
│   ├── scenario_4_fish_school_log.csv  # Simulation output for scenario 4
│   ├── scenario_5_fish_school_log.csv  # Simulation output for scenario 5
│   └── scenario_6_fish_school_log.csv  # Simulation output for scenario 6
├── bin/
│   └── fish_school                     # Compiled simulation executable
├── build/                              # CMake build artifacts (generated)
├── CMakeLists.txt                      # CMake build configuration
├── build_sim.sh                        # Build script
└── README.md
```

---

## Prerequisites

- **C++17** compatible compiler (e.g., `g++`)
- **CMake** 3.16 or later
- **Cadmium v2** — header-only DEVS simulation library (includes nlohmann/json)

Cadmium must be available either:
- At `../cadmium_v2/` relative to this project root, **or**
- Via the `CADMIUM` environment variable pointing to Cadmium's `include/` directory

To set the environment variable:
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

## Testing Instructions

Run a scenario by passing a config file path and an optional simulation time (default: 50):

```bash
./bin/fish_school config/<scenario_config>.json [sim_time]
```

**Run all six scenarios:**

```bash
./bin/fish_school config/scenario_1_apart_config.json 50
./bin/fish_school config/scenario_2_vline_config.json 50
./bin/fish_school config/scenario_3_hline_config.json 50
./bin/fish_school config/scenario_4_cross_config.json 50
./bin/fish_school config/scenario_5_diamond_config.json 50
./bin/fish_school config/scenario_6_right_angle_config.json 50
```

Each run produces a `fish_school_log.csv` file in the working directory containing the state of every cell at each simulation time step.

**Visualizing results** using the [Cell-DEVS Web Viewer](https://devssim.carleton.ca/cell-devs-viewer/):
1. Load the scenario config JSON file
2. Load the corresponding `fish_school_log.csv` output file
3. Step through or animate the simulation to observe school formation

**Color coding for the `direction` and `orientation` fields:**

| Direction | Color |
|---|---|
| East (1) | Green |
| North (2) | Yellow |
| West (3) | Blue |
| South (4) | Pink |

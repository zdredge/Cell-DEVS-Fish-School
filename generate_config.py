#!/usr/bin/env python3
"""
Generate asymmetric Cell-DEVS JSON configs for the 20x20 fish school simulation.

Cell ID format: "rXcY" where X=row, Y=col
Coordinate convention: col = dimension 0 (East+), row = dimension 1 (South+)

Vicinity factors encode water currents:
  - Rows 0-6:   eastward current  (horizontal: +1.0 east, -1.0 west; vertical: 0.0)
  - Rows 7-13:  calm zone         (all 0.0)
  - Rows 14-19: westward current  (horizontal: -1.0 east, +1.0 west; vertical: 0.0)
"""

import json
import argparse
import sys


GRID_ROWS = 20
GRID_COLS = 20

# Neighborhood range
# All cells use range 6 since predators move between cells each step,
# so any cell may host a predator that needs the full predator vision range.
CELL_RANGE = 6


def cell_id(row, col):
    return f"({col},{row})"


def manhattan_distance(r1, c1, r2, c2):
    return abs(r1 - r2) + abs(c1 - c2)


def get_vicinity(from_row, from_col, to_row, to_col):
    """
    Compute vicinity factor for the directed connection from_cell -> to_cell.
    Encodes water current effect on movement in that direction.
    """
    dr = to_row - from_row
    dc = to_col - from_col

    # Vertical connections are unaffected by horizontal currents
    if dc == 0:
        return 0.0

    # Self-loop
    if dr == 0 and dc == 0:
        return 0.0

    # Determine current zone based on the source cell's row
    if from_row <= 6:
        # Eastward current zone
        # Moving east (dc > 0): current assists (+1.0)
        # Moving west (dc < 0): current opposes (-1.0)
        return 1.0 if dc > 0 else -1.0
    elif from_row <= 13:
        # Calm zone — no current effect
        return 0.0
    else:
        # Westward current zone (rows 14-19)
        # Moving west (dc < 0): current assists (+1.0)
        # Moving east (dc > 0): current opposes (-1.0)
        return 1.0 if dc < 0 else -1.0


def generate_neighborhood(row, col, vn_range):
    """Generate Von Neumann neighborhood for a cell at (row, col) with given range."""
    neighborhood = {}
    for dr in range(-vn_range, vn_range + 1):
        for dc in range(-vn_range, vn_range + 1):
            if abs(dr) + abs(dc) > vn_range:
                continue
            nr, nc = row + dr, col + dc
            if 0 <= nr < GRID_ROWS and 0 <= nc < GRID_COLS:
                nid = cell_id(nr, nc)
                vicinity = get_vicinity(row, col, nr, nc)
                neighborhood[nid] = vicinity
    return neighborhood


def generate_config(fish_positions=None, predator_positions=None, no_currents=False):
    """
    Generate asymmetric Cell-DEVS config for a 20x20 grid.

    Args:
        fish_positions: list of (row, col, direction) tuples for fish placement
        predator_positions: list of (row, col, direction) tuples for predator placement
        no_currents: if True, set all vicinity factors to 0.0
    """
    if fish_positions is None:
        fish_positions = []
    if predator_positions is None:
        predator_positions = []

    # Build lookup sets
    fish_set = {(r, c) for r, c, _ in fish_positions}
    predator_set = {(r, c) for r, c, _ in predator_positions}
    fish_dir = {(r, c): d for r, c, d in fish_positions}
    pred_dir = {(r, c): d for r, c, d in predator_positions}
    config = {
        "scenario": {
            "shape": [GRID_ROWS, GRID_COLS],
            "origin": [0, 0],
            "wrapped": False
        },
        "cells": {
            "default": {
                "delay": "transport",
                "model": "fish",
                "state": {
                    "presence": 0,
                    "direction": 0,
                    "orientation": 0,
                    "behavior": 0,
                    "predatorDist": 0,
                    "predatorDir": 0
                }
            }
        },
        "viewer": [
            {
                "field": "presence",
                "breaks": [-1, 0, 5, 10],
                "colors": [
                    [220, 220, 220], # Light Grey (0: Empty)
                    [255, 0, 0],     # Red (5: Fish)
                    [0, 0, 0]        # Black (10: Predator)
                ]
            },
            {
                "field": "direction",
                "breaks": [-1, 0, 1, 2, 3, 4],
                "colors": [
                    [220, 220, 220], # Grey (0: None)
                    [0, 255, 0],     # Green (1: East)
                    [255, 255, 0],   # Yellow (2: North)
                    [0, 0, 255],     # Blue (3: West)
                    [255, 192, 203]  # Pink (4: South)
                ]
            },
            {
                "field": "orientation",
                "breaks": [-1, 0, 1, 2, 3, 4],
                "colors": [
                    [220, 220, 220],
                    [0, 255, 0],
                    [255, 255, 0],
                    [0, 0, 255],
                    [255, 192, 203]
                ]
            },
            {
                "field": "behavior",
                "breaks": [-1, 0, 1, 2],
                "colors": [
                    [220, 220, 220], # Grey (0: Schooling)
                    [255, 165, 0],   # Orange (1: Cooperative escape)
                    [128, 0, 128]    # Purple (2: Selfish escape)
                ]
            },
            {
                "field": "predatorDist",
                "breaks": [-1, 0, 1, 2, 3, 4, 5, 6],
                "colors": [
                    [220, 220, 220],
                    [255,   0,   0],
                    [255,  80,   0],
                    [255, 160,   0],
                    [255, 220,   0],
                    [200, 255,   0],
                    [120, 255,   0]
                ]
            },
            {
                "field": "predatorDir",
                "breaks": [-1, 0, 1, 2, 3, 4],
                "colors": [
                    [220, 220, 220],
                    [0, 255, 0],
                    [255, 255, 0],
                    [0, 0, 255],
                    [255, 192, 203]
                ]
            }
        ]
    }

    for row in range(GRID_ROWS):
        for col in range(GRID_COLS):
            cid = cell_id(row, col)
            is_predator = (row, col) in predator_set
            is_fish = (row, col) in fish_set

            neighborhood = generate_neighborhood(row, col, CELL_RANGE)

            if no_currents:
                neighborhood = {k: 0.0 for k in neighborhood}

            cell_config = {
                "neighborhood": neighborhood,
                # Add the cell_map so the viewer knows where to draw this cell
                "cell_map": [[col, row]] 
            }

            # Predator starting cells are tagged with model="predator" so the
            # factory routes them to PredatorCell. All cells share computation,
            # but the tag marks predator seeds in the configuration.
            if is_predator:
                cell_config["model"] = "predator"
                cell_config["state"] = {
                    "presence": 10,
                    "direction": pred_dir.get((row, col), 0),
                    "orientation": pred_dir.get((row, col), 0),
                    "behavior": 0,
                    "predatorDist": 0,
                    "predatorDir": 0
                }
            elif is_fish:
                cell_config["state"] = {
                    "presence": 5,
                    "direction": fish_dir.get((row, col), 0),
                    "orientation": 0,
                    "behavior": 0,
                    "predatorDist": 0,
                    "predatorDir": 0
                }

            config["cells"][cid] = cell_config

    return config


# Predefined Scenarios 

def scenario_schooling_no_predator():
    """6 fish in a loose cluster, no predator. Tests basic schooling on 20x20."""
    fish = [
        (8, 8, 0), (8, 10, 0), (8, 12, 0),
        (10, 9, 0), (10, 11, 0), (12, 10, 0),
    ]
    return generate_config(fish_positions=fish)


def scenario_predator_east():
    """School of fish in center, predator approaching from the east."""
    fish = [
        (9, 9, 0), (9, 10, 0), (9, 11, 0),
        (10, 9, 0), (10, 10, 0), (10, 11, 0),
    ]
    predator = [(10, 16, 3)]  # direction=3 (WEST), approaching from east
    return generate_config(fish_positions=fish, predator_positions=predator)


def scenario_predator_north():
    """School of fish in center, predator approaching from the north."""
    fish = [
        (10, 9, 0), (10, 10, 0), (10, 11, 0),
        (11, 9, 0), (11, 10, 0), (11, 11, 0),
    ]
    predator = [(4, 10, 4)]  # direction=4 (SOUTH), approaching from north
    return generate_config(fish_positions=fish, predator_positions=predator)


def scenario_predator_west():
    """School of fish in center, predator approaching from the west."""
    fish = [
        (9, 9, 0), (9, 10, 0), (9, 11, 0),
        (10, 9, 0), (10, 10, 0), (10, 11, 0),
    ]
    predator = [(10, 4, 1)]  # direction=1 (EAST), approaching from west
    return generate_config(fish_positions=fish, predator_positions=predator)


def scenario_predator_south():
    """School of fish in center, predator approaching from the south."""
    fish = [
        (9, 9, 0), (9, 10, 0), (9, 11, 0),
        (10, 9, 0), (10, 10, 0), (10, 11, 0),
    ]
    predator = [(16, 10, 2)]  # direction=2 (NORTH), approaching from south
    return generate_config(fish_positions=fish, predator_positions=predator)


def _selfish_encounter(no_currents):
    """Single fish at (10,10) with predator at (10,12) distance 2 directly east.
    Fish should enter selfish escape (directPredDist==2) and swerve perpendicular
    (NORTH or SOUTH). Predator initial direction=0 lets the predator compute
    pursuit direction on the first tick rather than bypassing via initial
    departure."""
    fish = [(10, 10, 0)]
    predator = [(10, 12, 0)]
    return generate_config(fish_positions=fish, predator_positions=predator,
                           no_currents=no_currents)


def _large_school(no_currents):
    """6x6 block of 36 fish in the grid interior with predator approaching from
    the east. Tests evasion of a dense formation — predator must find a way in
    through the platoon, captures should occur over time."""
    fish = [(r, c, 0) for r in range(5, 11) for c in range(5, 11)]
    predator = [(8, 17, 3)]  # WEST
    return generate_config(fish_positions=fish, predator_positions=predator,
                           no_currents=no_currents)


def _reluctance_demo(no_currents):
    """Horizontal line of 5 fish in open water (row 10, cols 4-8) with predator
    approaching from the east. Tests that the cooperative-escape reluctance
    mechanic produces captures in open water at a regular rate rather than
    letting the school reach the west wall every time."""
    fish = [(10, c, 0) for c in range(4, 9)]
    predator = [(10, 15, 3)]  # WEST
    return generate_config(fish_positions=fish, predator_positions=predator,
                           no_currents=no_currents)


def scenario_selfish_encounter():              return _selfish_encounter(False)
def scenario_selfish_encounter_no_currents():  return _selfish_encounter(True)
def scenario_large_school():                   return _large_school(False)
def scenario_large_school_no_currents():       return _large_school(True)
def scenario_reluctance_demo():                return _reluctance_demo(False)
def scenario_reluctance_demo_no_currents():    return _reluctance_demo(True)


def scenario_current_test():
    """Fish in different current zones to test current-assisted movement."""
    fish = [
        # Top zone (eastward current)
        (3, 5, 0), (3, 7, 0), (3, 9, 0),
        # Calm zone
        (10, 5, 0), (10, 7, 0), (10, 9, 0),
        # Bottom zone (westward current)
        (17, 5, 0), (17, 7, 0), (17, 9, 0),
    ]
    predator = [(3, 15, 3), (10, 15, 3), (17, 15, 3)]  # predators from east in each zone
    return generate_config(fish_positions=fish, predator_positions=predator)


def scenario_schooling_no_predator_no_currents():
    """Same as schooling_no_predator but with all currents disabled."""
    fish = [
        (8, 8, 0), (8, 10, 0), (8, 12, 0),
        (10, 9, 0), (10, 11, 0), (12, 10, 0),
    ]
    return generate_config(fish_positions=fish, no_currents=True)


def scenario_coop_platoon():
    """Two fish in a horizontal row + predator east. Both fish should enter
    cooperative escape simultaneously and translate west via platoon movement."""
    fish = [(10, 5, 0), (10, 6, 0)]
    predator = [(10, 9, 3)]  # WEST
    return generate_config(fish_positions=fish, predator_positions=predator, no_currents=True)


def scenario_coop_diagonal():
    """Two fish + predator approaching diagonally to exercise the fracturing
    case where different fish compute different nearestPredDir values."""
    fish = [(10, 5, 0), (10, 6, 0)]
    predator = [(8, 8, 3)]  # diagonal NE of school, moving WEST
    return generate_config(fish_positions=fish, predator_positions=predator, no_currents=True)


def scenario_coop_wall():
    """School adjacent to the west wall with predator east. Consensus fleeDir=WEST
    is invalid (wall). Fallback path in cooperative escape should engage;
    fish must not teleport through each other into the wall."""
    fish = [(10, 0, 0), (10, 1, 0)]
    predator = [(10, 4, 3)]  # WEST, range 3 from (10,1)
    return generate_config(fish_positions=fish, predator_positions=predator, no_currents=True)


# Current-influence tests. Each pair is (currents-on, currents-off) for
# isolating a single current-driven hook in cell_logic.hpp.

def _current_stall(no_currents):
    """Predator at (3,15) sees an anchored 2-fish school at (3,8)-(3,9),
    distance 6. Predator prefers WEST. In row-3 eastward zone, vicinity
    west = -1.0 which trips the stall gate. Fish are outside range-4
    alarm so stay anchored; the predator never moves. Control: predator
    advances west each tick.

    Predator starts with direction=0 so the stall is tested in the
    direction-compute phase rather than bypassed by an initial departure."""
    fish = [(3, 8, 0), (3, 9, 0)]
    predator = [(3, 15, 0)]
    return generate_config(fish_positions=fish, predator_positions=predator,
                           no_currents=no_currents)


def _current_coop_fallback(no_currents):
    """Row-0 school of 3 fish with a predator to the south at (3,11).
    Every fish is in cooperative escape (direct dist <=4, >2); consensus
    flee = NORTH is blocked by the north wall. In eastward zone (row 0),
    the perpendicular-by-vicinity fallback picks EAST (+1.0) over WEST
    (-1.0). Control: fallback uses schoolDir, which is WEST for the middle
    fish (fishWest from its left neighbour)."""
    fish = [(0, 10, 0), (0, 11, 0), (0, 12, 0)]
    predator = [(3, 11, 0)]
    return generate_config(fish_positions=fish, predator_positions=predator,
                           no_currents=no_currents)


def _current_selfish_tiebreak(no_currents):
    """Isolated fish at (3,10) with a predator at (5,10). Selfish escape
    (direct dist 2); swerveAxis = nearestPredDir = SOUTH, so perpendiculars
    are EAST / WEST. In row-3 eastward zone EAST (+1.0) beats WEST (-1.0)
    deterministically. Control: 50/50 coin flip over many runs."""
    fish = [(3, 10, 0)]
    predator = [(5, 10, 0)]
    return generate_config(fish_positions=fish, predator_positions=predator,
                           no_currents=no_currents)


def _current_wander(no_currents):
    """Lone predator at (3,10), no fish anywhere. Predator enters the no-fish
    random walk. With currents, WEST edge vicinity = -1.0 is filtered out
    of validAllowed, so the first tick's direction can never be WEST.
    Control: first-tick WEST appears roughly 25% of runs."""
    predator = [(3, 10, 0)]
    return generate_config(predator_positions=predator, no_currents=no_currents)


def scenario_current_stall():                    return _current_stall(False)
def scenario_current_stall_no_currents():        return _current_stall(True)
def scenario_current_coop_fallback():            return _current_coop_fallback(False)
def scenario_current_coop_fallback_no_currents():return _current_coop_fallback(True)
def scenario_current_selfish_tiebreak():         return _current_selfish_tiebreak(False)
def scenario_current_selfish_tiebreak_no_currents(): return _current_selfish_tiebreak(True)
def scenario_current_wander():                   return _current_wander(False)
def scenario_current_wander_no_currents():       return _current_wander(True)


SCENARIOS = {
    "schooling": scenario_schooling_no_predator,
    "schooling_no_currents": scenario_schooling_no_predator_no_currents,
    "predator_east": scenario_predator_east,
    "predator_west": scenario_predator_west,
    "predator_north": scenario_predator_north,
    "predator_south": scenario_predator_south,
    "selfish_encounter": scenario_selfish_encounter,
    "selfish_encounter_no_currents": scenario_selfish_encounter_no_currents,
    "large_school": scenario_large_school,
    "large_school_no_currents": scenario_large_school_no_currents,
    "reluctance_demo": scenario_reluctance_demo,
    "reluctance_demo_no_currents": scenario_reluctance_demo_no_currents,
    "coop_platoon": scenario_coop_platoon,
    "coop_diagonal": scenario_coop_diagonal,
    "coop_wall": scenario_coop_wall,
    "current_test": scenario_current_test,
    "current_stall": scenario_current_stall,
    "current_stall_no_currents": scenario_current_stall_no_currents,
    "current_coop_fallback": scenario_current_coop_fallback,
    "current_coop_fallback_no_currents": scenario_current_coop_fallback_no_currents,
    "current_selfish_tiebreak": scenario_current_selfish_tiebreak,
    "current_selfish_tiebreak_no_currents": scenario_current_selfish_tiebreak_no_currents,
    "current_wander": scenario_current_wander,
    "current_wander_no_currents": scenario_current_wander_no_currents,
}


def main():
    parser = argparse.ArgumentParser(description="Generate asymmetric Cell-DEVS configs for fish school simulation")
    parser.add_argument("scenario", choices=list(SCENARIOS.keys()),
                        help="Scenario to generate")
    parser.add_argument("-o", "--output", default=None,
                        help="Output file path (default: config/<scenario>_config.json)")

    args = parser.parse_args()

    config = SCENARIOS[args.scenario]()
    output_path = args.output or f"config/{args.scenario}_config.json"

    with open(output_path, "w") as f:
        json.dump(config, f, indent=2)

    # Count entities
    fish_count = sum(1 for k, v in config["cells"].items()
                     if k != "default" and v.get("state", {}).get("presence") == 5)
    pred_count = sum(1 for k, v in config["cells"].items()
                     if k != "default" and v.get("state", {}).get("presence") == 10)
    total_cells = sum(1 for k in config["cells"] if k != "default")

    print(f"Generated {output_path}: {total_cells} cells, {fish_count} fish, {pred_count} predators")


if __name__ == "__main__":
    main()

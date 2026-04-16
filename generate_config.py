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

# Neighborhood ranges
FISH_RANGE = 4
PREDATOR_RANGE = 6


def cell_id(row, col):
    return f"r{row}c{col}"


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
        }
    }

    for row in range(GRID_ROWS):
        for col in range(GRID_COLS):
            cid = cell_id(row, col)
            is_predator = (row, col) in predator_set
            is_fish = (row, col) in fish_set

            # Determine neighborhood range
            vn_range = PREDATOR_RANGE if is_predator else FISH_RANGE
            neighborhood = generate_neighborhood(row, col, vn_range)

            if no_currents:
                neighborhood = {k: 0.0 for k in neighborhood}

            cell_config = {"neighborhood": neighborhood}

            if is_predator:
                cell_config["model"] = "predator"
                cell_config["state"] = {
                    "presence": 10,
                    "direction": pred_dir.get((row, col), 0),
                    "orientation": 0,
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


SCENARIOS = {
    "schooling": scenario_schooling_no_predator,
    "predator_east": scenario_predator_east,
    "predator_north": scenario_predator_north,
    "current_test": scenario_current_test,
    "schooling_no_currents": scenario_schooling_no_predator_no_currents,
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

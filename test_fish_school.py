#!/usr/bin/env python3
"""
Phase 4 test suite for the asymmetric Cell-DEVS fish-school simulation.

Covers:
  - Invariants on every scenario (fish/predator conservation, CBP correctness,
    movement consistency, paired predator fields, boundary respect).
  - Scenario-specific deterministic assertions.
  - Statistical tests (reluctance_demo, large_school) for open-water capture
    rate and capture probability.
  - Currents-on / currents-off comparison (ported from test_currents.py).

Run: python3 test_fish_school.py
"""

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from collections import Counter, defaultdict
from pathlib import Path

# --- Constants ----------------------------------------------------------------

PROJECT_DIR = Path(__file__).parent
BINARY = PROJECT_DIR / "bin" / "fish_school"
GENERATOR = PROJECT_DIR / "generate_config.py"
CONFIG_DIR = PROJECT_DIR / "config"

# State: <presence,direction,orientation,behavior,predatorDist,predatorDir>
STATE_RE = re.compile(r"<(-?\d+),(-?\d+),(-?\d+),(-?\d+),(-?\d+),(-?\d+)>")
CELL_RE = re.compile(r"\((\d+),(\d+)\)")

DIR_NAMES = {0: "NONE", 1: "EAST", 2: "NORTH", 3: "WEST", 4: "SOUTH"}
BEHAVIOR_NAMES = {0: "SCHOOL", 1: "COOP", 2: "SELFISH"}
DIR_OFFSET = {1: (1, 0), 2: (0, -1), 3: (-1, 0), 4: (0, 1)}  # E, N, W, S (col, row delta)

STAT_RUNS = 20
OPEN_WATER_MARGIN = 3          # Manhattan distance from every boundary
OPEN_WATER_RATE_MIN = 0.30     # >= 30% of captures must occur in open water (not along the boundary)
SIM_TIMEOUT_S = 60

# Scenarios covered by the suite.
ALL_SCENARIOS = [
    "schooling",
    "schooling_no_currents",
    "predator_east",
    "predator_west",
    "predator_north",
    "predator_south",
    "selfish_encounter",
    "selfish_encounter_no_currents",
    "large_school",
    "large_school_no_currents",
    "reluctance_demo",
    "reluctance_demo_no_currents",
    "coop_platoon",
    "coop_diagonal",
    "coop_wall",
    "current_stall",
    "current_stall_no_currents",
    "current_coop_fallback",
    "current_coop_fallback_no_currents",
    "current_selfish_tiebreak",
    "current_selfish_tiebreak_no_currents",
    "current_wander",
    "current_wander_no_currents",
]


# --- Reporting ----------------------------------------------------------------

class Report:
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.warnings = 0
        self.lines = []

    def ok(self, msg):
        self.passed += 1
        self.lines.append(f"  [PASS] {msg}")

    def fail(self, msg):
        self.failed += 1
        self.lines.append(f"  [FAIL] {msg}")

    def warn(self, msg):
        self.warnings += 1
        self.lines.append(f"  [WARN] {msg}")

    def info(self, msg):
        self.lines.append(f"  [INFO] {msg}")

    def section(self, title):
        self.lines.append(f"\n=== {title} ===")

    def print_and_exit(self):
        for line in self.lines:
            print(line)
        print("\n" + "=" * 70)
        print(f"SUMMARY: {self.passed} passed, {self.failed} failed, {self.warnings} warnings")
        print("=" * 70)
        sys.exit(0 if self.failed == 0 else 1)


# --- Parsers ------------------------------------------------------------------

def parse_asymm_config(path):
    """Parse an asymmetric config JSON.

    Returns {'fish': {(col,row): state6}, 'predators': {(col,row): state6},
             'grid_shape': (cols, rows), 'no_currents': bool (best-effort)}
    """
    cfg = json.load(open(path))
    shape = cfg.get("scenario", {}).get("shape", [20, 20])
    grid_shape = (int(shape[0]), int(shape[1]))

    fish, preds = {}, {}
    for key, val in cfg["cells"].items():
        if key == "default":
            continue
        m = CELL_RE.match(key)
        if not m:
            continue
        col, row = int(m.group(1)), int(m.group(2))
        state = val.get("state", {})
        if not state:
            continue
        p = state.get("presence", 0)
        tup = (
            p,
            state.get("direction", 0),
            state.get("orientation", 0),
            state.get("behavior", 0),
            state.get("predatorDist", 0),
            state.get("predatorDir", 0),
        )
        if p == 5:
            fish[(col, row)] = tup
        elif p == 10:
            preds[(col, row)] = tup

    # Heuristic: detect no-currents by inspecting any non-default cell's neighborhood — if all vicinity values are 0.0
    no_currents = True
    for key, val in cfg["cells"].items():
        if key == "default":
            continue
        neigh = val.get("neighborhood", {})
        if any(v != 0.0 for v in neigh.values()):
            no_currents = False
            break

    return {
        "fish": fish,
        "predators": preds,
        "grid_shape": grid_shape,
        "no_currents": no_currents,
    }


def parse_log(log_path):
    """Parse a Cadmium CSV log.

    Returns {t_int: {(col,row): (p,d,o,b,pD,pDir)}}. Only state snapshot rows
    (empty port_name). For duplicate (t, cell) entries, keeps the LAST one.
    """
    timesteps = defaultdict(dict)
    with open(log_path) as f:
        for line in f:
            parts = line.strip().split(";")
            if len(parts) < 5:
                continue
            try:
                t = int(float(parts[0]))
            except ValueError:
                continue
            if parts[3].strip():  # skip output port events
                continue
            cm = CELL_RE.search(parts[2])
            sm = STATE_RE.search(parts[4])
            if not cm or not sm:
                continue
            col, row = int(cm.group(1)), int(cm.group(2))
            state = tuple(int(sm.group(i)) for i in range(1, 7))
            timesteps[t][(col, row)] = state
    return dict(timesteps)


def build_snapshots(parsed_log, grid_shape, initial_fish, initial_predators):
    """Build cumulative full-grid snapshots at each logged integer timestep."""
    cols, rows = grid_shape
    grid = {(c, r): (0, 0, 0, 0, 0, 0) for c in range(cols) for r in range(rows)}
    for cell, state in initial_fish.items():
        grid[cell] = state
    for cell, state in initial_predators.items():
        grid[cell] = state

    snapshots = {}
    for t in sorted(parsed_log.keys()):
        for cell, state in parsed_log[t].items():
            grid[cell] = state
        snapshots[t] = dict(grid)
    return snapshots


# --- Runner -------------------------------------------------------------------

def regenerate(scenario):
    subprocess.run(
        [sys.executable, str(GENERATOR), scenario],
        check=True, capture_output=True,
    )
    return CONFIG_DIR / f"{scenario}_config.json"


def run_sim(config_path, sim_time=50):
    tmp = tempfile.mkdtemp(prefix="phase4_")
    log = os.path.join(tmp, "log.csv")
    try:
        subprocess.run(
            [str(BINARY), str(config_path), str(sim_time), log],
            check=True, capture_output=True, text=True, timeout=SIM_TIMEOUT_S,
        )
        return log, tmp
    except Exception as e:
        shutil.rmtree(tmp, ignore_errors=True)
        raise RuntimeError(f"sim failed for {config_path}: {e}")


# --- Helpers ------------------------------------------------------------------

def count_presence(grid, p):
    return sum(1 for s in grid.values() if s[0] == p)


def fish_positions(grid):
    return {pos for pos, s in grid.items() if s[0] == 5}


def predator_positions(grid):
    return {pos for pos, s in grid.items() if s[0] == 10}


def is_open_water(col, row, grid_shape):
    cols, rows = grid_shape
    return (col >= OPEN_WATER_MARGIN
            and col < cols - OPEN_WATER_MARGIN
            and row >= OPEN_WATER_MARGIN
            and row < rows - OPEN_WATER_MARGIN)


def find_captures(snapshots):
    """Return list of (t, cell) where a fish was captured

    Capture: a cell has presence=5 at t and presence=10 at t+1.
    """
    captures = []
    times = sorted(snapshots.keys())
    for i in range(len(times) - 1):
        t0, t1 = times[i], times[i + 1]
        g0, g1 = snapshots[t0], snapshots[t1]
        for cell, s0 in g0.items():
            if s0[0] == 5 and g1.get(cell, (0,))[0] == 10:
                captures.append((t1, cell))
    return captures


# --- Invariants ---------------------------------------------------------------

def check_valid_states(snapshots, r, label):
    for t, grid in snapshots.items():
        for cell, (p, d, o, b, pd, pdir) in grid.items():
            if p not in (0, 5, 10):
                r.fail(f"{label} t={t} {cell}: invalid presence {p}")
                return
            if not (0 <= d <= 4):
                r.fail(f"{label} t={t} {cell}: invalid direction {d}")
                return
            if not (0 <= o <= 4):
                r.fail(f"{label} t={t} {cell}: invalid orientation {o}")
                return
            if not (0 <= b <= 2):
                r.fail(f"{label} t={t} {cell}: invalid behavior {b}")
                return
            if pd < 0:
                r.fail(f"{label} t={t} {cell}: negative predatorDist {pd}")
                return
            if not (0 <= pdir <= 4):
                r.fail(f"{label} t={t} {cell}: invalid predatorDir {pdir}")
                return
    r.ok(f"{label}: all cell states valid across {len(snapshots)} snapshots")


def check_empty_cell_consistency(snapshots, r, label):
    for t, grid in snapshots.items():
        for cell, (p, d, o, b, pd, pdir) in grid.items():
            if p == 0 and (d or o or b or pd or pdir):
                r.fail(f"{label} t={t} {cell}: empty cell has non-zero state "
                       f"<{p},{d},{o},{b},{pd},{pdir}>")
                return
    r.ok(f"{label}: all empty cells have fully-cleared transient fields")


def check_boundary_respect(snapshots, grid_shape, r, label):
    cols, rows = grid_shape
    for t, grid in snapshots.items():
        for (c, row), s in grid.items():
            if s[0] != 0 and (c < 0 or c >= cols or row < 0 or row >= rows):
                r.fail(f"{label} t={t} ({c},{row}): entity out of grid {grid_shape}")
                return
    r.ok(f"{label}: all entities within {cols}x{rows} grid")


def check_predator_conservation(snapshots, expected, r, label):
    for t, grid in snapshots.items():
        c = count_presence(grid, 10)
        if c != expected:
            r.fail(f"{label} t={t}: predator count {c} != expected {expected}")
            return
    r.ok(f"{label}: predator count constant at {expected}")


def check_fish_monotonic(snapshots, r, label):
    prev = None
    times = sorted(snapshots.keys())
    for t in times:
        c = count_presence(snapshots[t], 5)
        if prev is not None and c > prev:
            r.fail(f"{label} t={t}: fish count {c} > previous {prev} (fish created)")
            return
        prev = c
    r.ok(f"{label}: fish count non-increasing (captures-only)")


def check_capture_traceability(snapshots, r, label):
    """Every fish-count drop must correspond to a predator arriving at the
    former fish cell."""
    times = sorted(snapshots.keys())
    unexplained = []
    for i in range(len(times) - 1):
        t0, t1 = times[i], times[i + 1]
        g0, g1 = snapshots[t0], snapshots[t1]
        drop = count_presence(g0, 5) - count_presence(g1, 5)
        if drop <= 0:
            continue
        # Count predator arrivals at formerly-fish cells
        captured = 0
        for cell, s0 in g0.items():
            if s0[0] == 5 and g1.get(cell, (0,))[0] == 10:
                captured += 1
        if captured != drop:
            unexplained.append(
                f"t={t0}->{t1}: fish dropped by {drop} but {captured} predator-arrivals traced"
            )
    if unexplained:
        for u in unexplained[:3]:
            r.fail(f"{label} {u}")
    else:
        r.ok(f"{label}: all fish-count drops traced to predator arrivals")


def check_cbp_correctness(snapshots, r, label):
    """behavior==0 iff predatorDist==0 (both directions).

    Note: schoolmate-relay alarms set predatorDist>0 with behavior==1, never
    behavior==0. Selfish escape (behavior==2) requires directPredDist<=2 which
    is not directly visible in state; skip that sub-check.
    """
    bad = []
    for t, grid in snapshots.items():
        for cell, (p, d, o, b, pd, pdir) in grid.items():
            if p != 5:
                continue
            if pd == 0 and b != 0:
                bad.append(f"t={t} {cell}: predatorDist=0 but behavior={BEHAVIOR_NAMES[b]}")
            if pd > 0 and b == 0:
                bad.append(f"t={t} {cell}: predatorDist={pd} but behavior=SCHOOL")
    if bad:
        for b in bad[:3]:
            r.fail(f"{label} CBP mismatch: {b}")
    else:
        r.ok(f"{label}: CBP correctness (behavior↔predatorDist)")


def check_paired_predator_fields(snapshots, r, label):
    bad = []
    for t, grid in snapshots.items():
        for cell, (p, d, o, b, pd, pdir) in grid.items():
            if p != 5:
                continue
            if (pd > 0) != (pdir != 0):
                bad.append(f"t={t} {cell}: predatorDist={pd}, predatorDir={pdir} (unpaired)")
    if bad:
        for b in bad[:3]:
            r.fail(f"{label} paired-field violation: {b}")
    else:
        r.ok(f"{label}: paired predator fields (dist↔dir)")


def check_predator_movement_consistency(snapshots, r, label):
    """A predator that leaves cell X must appear at an adjacent cell it headed
    toward (via state.direction at t0). Accounts for double-resolution of
    capture (fish at target → predator replaces it)."""
    times = sorted(snapshots.keys())
    bad = []
    for i in range(len(times) - 1):
        t0, t1 = times[i], times[i + 1]
        g0, g1 = snapshots[t0], snapshots[t1]
        for cell, s0 in g0.items():
            if s0[0] != 10:
                continue
            s1 = g1.get(cell, (0,)*6)
            if s1[0] == 10:
                continue  # predator stayed
            d = s0[1]
            if d == 0:
                # Predator had no direction but disappeared — it shouldn't leave.
                bad.append(f"t={t0}->{t1} {cell}: predator vanished with direction=0")
                continue
            if d not in DIR_OFFSET:
                continue
            dc, dr = DIR_OFFSET[d]
            target = (cell[0] + dc, cell[1] + dr)
            if g1.get(target, (0,))[0] != 10:
                bad.append(
                    f"t={t0}->{t1} {cell}: predator moved {DIR_NAMES[d]} but "
                    f"target {target} is not predator"
                )
    if bad:
        for b in bad[:3]:
            r.fail(f"{label} predator movement: {b}")
    else:
        r.ok(f"{label}: predator moves traceable")


def run_all_invariants(snapshots, cfg, r, label):
    check_valid_states(snapshots, r, label)
    check_empty_cell_consistency(snapshots, r, label)
    check_boundary_respect(snapshots, cfg["grid_shape"], r, label)
    check_predator_conservation(snapshots, len(cfg["predators"]), r, label)
    check_fish_monotonic(snapshots, r, label)
    check_capture_traceability(snapshots, r, label)
    check_cbp_correctness(snapshots, r, label)
    check_paired_predator_fields(snapshots, r, label)
    check_predator_movement_consistency(snapshots, r, label)


# --- Scenario-specific assertions ---------------------------------------------

def behaviors_observed(snapshots):
    """Return set of behavior values observed on any fish across all ticks."""
    seen = set()
    for grid in snapshots.values():
        for s in grid.values():
            if s[0] == 5:
                seen.add(s[3])
    return seen


def directions_observed(snapshots, predicate):
    """Directions observed on fish cells matching predicate(state)."""
    c = Counter()
    for grid in snapshots.values():
        for s in grid.values():
            if s[0] == 5 and predicate(s):
                c[s[1]] += 1
    return c


def assert_no_captures(snapshots, r, label):
    caps = find_captures(snapshots)
    if not caps:
        r.ok(f"{label}: no captures (as expected)")
    else:
        r.fail(f"{label}: {len(caps)} captures occurred; first at t={caps[0][0]} {caps[0][1]}")


def assert_behavior_observed(snapshots, behavior, r, label):
    if behavior in behaviors_observed(snapshots):
        r.ok(f"{label}: behavior {BEHAVIOR_NAMES[behavior]} observed at least once")
    else:
        r.fail(f"{label}: behavior {BEHAVIOR_NAMES[behavior]} never observed")


def assert_at_least_one_capture(snapshots, r, label):
    caps = find_captures(snapshots)
    if caps:
        r.ok(f"{label}: {len(caps)} capture(s); first at t={caps[0][0]} {caps[0][1]}")
    else:
        r.warn(f"{label}: no captures in this run (may be stochastic)")


# --- Statistical tests --------------------------------------------------------

def stat_captures(scenario, sim_time, grid_shape, runs=STAT_RUNS):
    """Run `runs` simulations of `scenario`; return list of capture lists,
    one per run. Each capture list is [(t, (col,row))]."""
    cfg_path = regenerate(scenario)
    cfg = parse_asymm_config(cfg_path)
    all_runs = []
    for _ in range(runs):
        log, tmp = run_sim(cfg_path, sim_time)
        parsed = parse_log(log)
        shutil.rmtree(tmp, ignore_errors=True)
        snaps = build_snapshots(parsed, cfg["grid_shape"], cfg["fish"], cfg["predators"])
        all_runs.append(find_captures(snaps))
    return all_runs, cfg


def open_water_rate(all_runs, grid_shape):
    """Return (total_captures, open_water_captures, rate) across all runs."""
    total = 0
    ow = 0
    for caps in all_runs:
        for _t, (c, r) in caps:
            total += 1
            if is_open_water(c, r, grid_shape):
                ow += 1
    rate = ow / total if total else 0.0
    return total, ow, rate


def test_statistical_open_water(scenario, sim_time, capture_prob_min, r):
    r.section(f"Statistical: {scenario}  ({STAT_RUNS} runs, {sim_time} ticks)")
    all_runs, cfg = stat_captures(scenario, sim_time, None)
    runs_with_cap = sum(1 for caps in all_runs if caps)
    prob = runs_with_cap / STAT_RUNS
    r.info(f"{scenario}: {runs_with_cap}/{STAT_RUNS} runs produced ≥1 capture "
           f"(P={prob:.2f}, required ≥{capture_prob_min:.2f})")
    if prob >= capture_prob_min:
        r.ok(f"{scenario}: capture probability {prob:.2f} ≥ {capture_prob_min:.2f}")
    else:
        r.fail(f"{scenario}: capture probability {prob:.2f} < {capture_prob_min:.2f}")

    total, ow, rate = open_water_rate(all_runs, cfg["grid_shape"])
    r.info(f"{scenario}: total captures={total}, open-water={ow} ({rate*100:.1f}%); "
           f"required ≥{OPEN_WATER_RATE_MIN*100:.0f}%")
    if total == 0:
        r.fail(f"{scenario}: no captures at all across {STAT_RUNS} runs")
    elif rate >= OPEN_WATER_RATE_MIN:
        r.ok(f"{scenario}: open-water capture rate {rate*100:.1f}% ≥ {OPEN_WATER_RATE_MIN*100:.0f}%")
    else:
        r.fail(f"{scenario}: open-water capture rate {rate*100:.1f}% < {OPEN_WATER_RATE_MIN*100:.0f}%")
    return total, ow


# --- Phase B: scenario-specific -----------------------------------------------

def test_scenario_schooling(snapshots, r, label):
    assert_no_captures(snapshots, r, label)
    assert_behavior_observed(snapshots, 0, r, label)
    # No predator → no alarm; behaviors 1, 2 should NEVER appear.
    obs = behaviors_observed(snapshots)
    if 1 in obs or 2 in obs:
        r.fail(f"{label}: alarm behavior seen without predator (observed={obs})")
    else:
        r.ok(f"{label}: only SCHOOL behavior observed (no predator → no alarm)")


def test_scenario_predator_approach(snapshots, r, label):
    # Predator present; fish should enter cooperative escape at least once.
    obs = behaviors_observed(snapshots)
    if 1 in obs:
        r.ok(f"{label}: COOP escape observed")
    else:
        r.warn(f"{label}: COOP escape never fired (fish never in direct range 3-4)")
    assert_at_least_one_capture(snapshots, r, label)


def test_scenario_selfish_encounter(snapshots, r, label):
    # directPredDist==2 at t=0 → behavior must become SELFISH at t=0 or t=1.
    obs = behaviors_observed(snapshots)
    if 2 in obs:
        r.ok(f"{label}: SELFISH escape observed")
    else:
        r.fail(f"{label}: SELFISH never observed (expected at predDist≤2)")


def test_scenario_coop(snapshots, r, label):
    # Cooperative escape must fire on at least one fish.
    obs = behaviors_observed(snapshots)
    if 1 in obs:
        r.ok(f"{label}: COOP escape observed")
    else:
        r.fail(f"{label}: COOP escape never fired")


def test_scenario_reluctance_demo_single(snapshots, r, label):
    # At least one tick where a cooperatively-alerted fish has direction==0
    # (reluctance gate firing). Then also demonstrate captures happen (single run
    # — statistical open-water rate is checked in Phase C).
    saw_hold = False
    for t, grid in snapshots.items():
        for cell, s in grid.items():
            if s[0] == 5 and s[3] == 1 and s[1] == 0 and s[4] > 0:
                saw_hold = True
                break
        if saw_hold:
            break
    if saw_hold:
        r.ok(f"{label}: reluctance observed (coop-alerted fish with direction=0)")
    else:
        r.warn(f"{label}: reluctance not observed in this run (stochastic)")


def test_scenario_current_stall(snapshots, cfg, r, label):
    start = next(iter(cfg["predators"].keys()))  # (col,row) of initial predator
    pred_cells_seen = set()
    for grid in snapshots.values():
        for cell, s in grid.items():
            if s[0] == 10:
                pred_cells_seen.add(cell)
    if cfg["no_currents"]:
        # Expected: predator advanced (visited >1 cell).
        if len(pred_cells_seen) > 1:
            r.ok(f"{label}: predator advanced (visited {len(pred_cells_seen)} cells)")
        else:
            r.fail(f"{label}: predator did not advance (cells={pred_cells_seen})")
    else:
        if pred_cells_seen == {start}:
            r.ok(f"{label}: predator stalled at {start} (never moved)")
        else:
            r.fail(f"{label}: predator moved despite opposing current: {sorted(pred_cells_seen)}")


def test_scenario_current_wander_single(snapshots, cfg, r, label):
    # With currents: predator should never have direction=WEST(3) in row 3.
    if cfg["no_currents"]:
        return  # Handled by statistical phase
    pred_cell = next(iter(cfg["predators"].keys()))
    for t, grid in snapshots.items():
        s = grid.get(pred_cell)
        if s and s[0] == 10 and s[1] == 3:
            r.fail(f"{label} t={t}: predator took WEST despite opposing current")
            return
    r.ok(f"{label}: predator never selected WEST (filter active)")


# --- Phase C: statistical runs for randomness-heavy scenarios -----------------

def phase_c_statistical(r):
    r.section("PHASE C — Statistical tests")
    # reluctance_demo: 5 fish in open water, predator 6 cells east.
    # Expect some captures in interior thanks to reluctance slowing the flee.
    test_statistical_open_water("reluctance_demo", sim_time=40, capture_prob_min=0.5, r=r)
    # large_school: dense 6x6 block; even with reluctance the predator must
    # catch at least one over time.
    test_statistical_open_water("large_school", sim_time=60, capture_prob_min=0.8, r=r)


# --- Phase D: currents comparisons (lifted from test_currents.py) -------------

def _selfish_tiebreak_directions(scenario, cell):
    cfg = regenerate(scenario)
    dirs = Counter()
    for _ in range(STAT_RUNS):
        log, tmp = run_sim(cfg, sim_time=1)
        parsed = parse_log(log)
        shutil.rmtree(tmp, ignore_errors=True)
        st = parsed.get(0, {}).get(cell)
        if st and st[3] == 2:
            dirs[st[1]] += 1
    return dirs


def phase_d_currents(r):
    r.section("PHASE D — Water-current influence")

    # Test 1: current_coop_fallback row-0 fish pick EAST under currents;
    # remain anchored (dir=0) without.
    targets = [(10, 0), (11, 0), (12, 0)]
    cfg = regenerate("current_coop_fallback")
    log, tmp = run_sim(cfg, sim_time=1)
    parsed = parse_log(log)
    shutil.rmtree(tmp, ignore_errors=True)
    t0 = parsed.get(0, {})
    all_east = all((st := t0.get(c)) and st[1] == 1 and st[3] == 1 for c in targets)
    if all_east:
        r.ok("current_coop_fallback: all 3 row-0 fish chose EAST fallback (current-assisted)")
    else:
        r.fail(f"current_coop_fallback: not all fish chose EAST; t0={[t0.get(c) for c in targets]}")

    cfg2 = regenerate("current_coop_fallback_no_currents")
    log2, tmp2 = run_sim(cfg2, sim_time=1)
    parsed2 = parse_log(log2)
    shutil.rmtree(tmp2, ignore_errors=True)
    t0b = parsed2.get(0, {})
    in_coop = all((st := t0b.get(c)) and st[3] == 1 for c in targets)
    not_flee_north = all((st := t0b.get(c)) and st[1] != 2 for c in targets)
    if in_coop and not_flee_north:
        r.ok("current_coop_fallback_no_currents: row-0 fish in COOP; never flee NORTH (wall-blocked)")
    else:
        r.fail(f"current_coop_fallback_no_currents: unexpected; t0={[t0b.get(c) for c in targets]}")

    # Test 2: selfish tie-break direction — EAST strongly preferred with currents.
    # Selfish escape has 30% panic (dir=0) + 80/20 current-preference split, so
    # expected ~63% EAST, ~7% WEST, ~30% panic. Assert the distribution skew.
    fish_cell = (10, 3)
    dirs_with = _selfish_tiebreak_directions("current_selfish_tiebreak", fish_cell)
    east_w = dirs_with.get(1, 0)
    west_w = dirs_with.get(3, 0)
    if east_w >= 2 * max(west_w, 1) and east_w >= STAT_RUNS // 2:
        r.ok(f"current_selfish_tiebreak: EAST dominates ({east_w} EAST, {west_w} WEST)")
    else:
        r.fail(f"current_selfish_tiebreak: EAST should dominate, got {dict(dirs_with)}")

    dirs_without = _selfish_tiebreak_directions("current_selfish_tiebreak_no_currents", fish_cell)
    east, west = dirs_without.get(1, 0), dirs_without.get(3, 0)
    # Without currents: 50/50 coin flip between EAST/WEST among non-panic runs.
    if east > 0 and west > 0 and abs(east - west) <= max(4, STAT_RUNS // 2):
        r.ok(f"current_selfish_tiebreak_no_currents: coin flip EAST={east}, WEST={west}")
    else:
        r.fail(f"current_selfish_tiebreak_no_currents: expected ~50/50, got EAST={east}, WEST={west}")

    # Test 3: wander — WEST never chosen under currents; appears without.
    pred_cell = (10, 3)
    cfg3 = regenerate("current_wander")
    dirs_w = Counter()
    for _ in range(STAT_RUNS):
        log, tmp = run_sim(cfg3, sim_time=1)
        parsed = parse_log(log)
        shutil.rmtree(tmp, ignore_errors=True)
        st = parsed.get(0, {}).get(pred_cell)
        if st and st[0] == 10:
            dirs_w[st[1]] += 1
    if dirs_w.get(3, 0) == 0 and sum(dirs_w.values()) == STAT_RUNS:
        r.ok(f"current_wander: WEST never selected across {STAT_RUNS} runs")
    else:
        r.fail(f"current_wander: expected WEST=0, got {dict(dirs_w)}")

    cfg4 = regenerate("current_wander_no_currents")
    dirs_wo = Counter()
    for _ in range(STAT_RUNS):
        log, tmp = run_sim(cfg4, sim_time=1)
        parsed = parse_log(log)
        shutil.rmtree(tmp, ignore_errors=True)
        st = parsed.get(0, {}).get(pred_cell)
        if st and st[0] == 10:
            dirs_wo[st[1]] += 1
    if dirs_wo.get(3, 0) >= 1:
        r.ok(f"current_wander_no_currents: WEST selected {dirs_wo.get(3,0)}/{STAT_RUNS} (filter inactive)")
    else:
        r.fail(f"current_wander_no_currents: WEST never selected (statistically unlikely)")


# --- Phase A+B: per-scenario single-run sweep ---------------------------------

SCENARIO_DISPATCH = {
    "schooling": test_scenario_schooling,
    "schooling_no_currents": test_scenario_schooling,
    "predator_east": test_scenario_predator_approach,
    "predator_west": test_scenario_predator_approach,
    "predator_north": test_scenario_predator_approach,
    "predator_south": test_scenario_predator_approach,
    "selfish_encounter": test_scenario_selfish_encounter,
    "selfish_encounter_no_currents": test_scenario_selfish_encounter,
    "large_school": test_scenario_predator_approach,
    "large_school_no_currents": test_scenario_predator_approach,
    "reluctance_demo": test_scenario_reluctance_demo_single,
    "reluctance_demo_no_currents": test_scenario_reluctance_demo_single,
    "coop_platoon": test_scenario_coop,
    "coop_diagonal": test_scenario_coop,
    "coop_wall": test_scenario_coop,
}


def phase_ab_sweep(r):
    r.section("PHASE A+B — Invariants & scenario-specific checks")
    sim_time_defaults = {
        "schooling": 30,
        "schooling_no_currents": 30,
        "large_school": 50,
        "large_school_no_currents": 50,
        "reluctance_demo": 40,
        "reluctance_demo_no_currents": 40,
    }
    skipped_stat = {
        "current_selfish_tiebreak",
        "current_selfish_tiebreak_no_currents",
        "current_wander",
        "current_wander_no_currents",
    }
    for scenario in ALL_SCENARIOS:
        if scenario in skipped_stat:
            continue  # handled by Phase D
        cfg_path = regenerate(scenario)
        cfg = parse_asymm_config(cfg_path)
        sim_time = sim_time_defaults.get(scenario, 30)
        try:
            log, tmp = run_sim(cfg_path, sim_time)
        except RuntimeError as e:
            r.fail(f"{scenario}: simulation failed: {e}")
            continue
        parsed = parse_log(log)
        shutil.rmtree(tmp, ignore_errors=True)
        snapshots = build_snapshots(parsed, cfg["grid_shape"], cfg["fish"], cfg["predators"])
        label = scenario
        run_all_invariants(snapshots, cfg, r, label)
        if scenario in SCENARIO_DISPATCH:
            SCENARIO_DISPATCH[scenario](snapshots, r, label)
        elif scenario.startswith("current_stall"):
            test_scenario_current_stall(snapshots, cfg, r, label)
        elif scenario == "current_wander" or scenario == "current_wander_no_currents":
            test_scenario_current_wander_single(snapshots, cfg, r, label)


# --- Phase E: aggregate open-water report -------------------------------------

def phase_e_summary(r, capture_totals):
    r.section("PHASE E — Aggregate open-water report")
    total, ow = capture_totals
    if total == 0:
        r.info("No captures recorded across statistical runs.")
    else:
        pct = ow / total * 100
        r.info(f"Aggregate: {ow}/{total} captures in open water ({pct:.1f}%)")


# --- Main ---------------------------------------------------------------------

def main():
    if not BINARY.exists():
        print(f"Binary not found at {BINARY}. Run: source build_sim.sh")
        sys.exit(2)

    print("=" * 70)
    print("FISH SCHOOL — TEST SUITE")
    print("=" * 70)

    r = Report()
    phase_ab_sweep(r)

    # Phase C returns capture totals so we can aggregate in Phase E.
    # Each stat_test call inside phase_c_statistical currently prints its own
    # counts; we collect them here.
    cap_total, cap_ow = 0, 0
    r.section("PHASE C — Statistical tests")
    for scenario, sim_time, prob_min in [
        ("reluctance_demo", 40, 0.5),
        ("large_school", 60, 0.8),
    ]:
        r.info(f"--- {scenario} (×{STAT_RUNS}, sim_time={sim_time}) ---")
        all_runs, cfg = stat_captures(scenario, sim_time, None)
        runs_with_cap = sum(1 for caps in all_runs if caps)
        prob = runs_with_cap / STAT_RUNS
        r.info(f"{scenario}: {runs_with_cap}/{STAT_RUNS} runs with ≥1 capture (P={prob:.2f})")
        if prob >= prob_min:
            r.ok(f"{scenario}: capture probability {prob:.2f} ≥ {prob_min:.2f}")
        else:
            r.fail(f"{scenario}: capture probability {prob:.2f} < {prob_min:.2f}")
        t, ow, rate = open_water_rate(all_runs, cfg["grid_shape"])
        r.info(f"{scenario}: {t} total captures, {ow} open-water ({rate*100:.1f}%)")
        if t == 0:
            r.fail(f"{scenario}: no captures across {STAT_RUNS} runs")
        elif rate >= OPEN_WATER_RATE_MIN:
            r.ok(f"{scenario}: open-water rate {rate*100:.1f}% ≥ {OPEN_WATER_RATE_MIN*100:.0f}%")
        else:
            r.fail(f"{scenario}: open-water rate {rate*100:.1f}% < {OPEN_WATER_RATE_MIN*100:.0f}%")
        cap_total += t
        cap_ow += ow

    phase_d_currents(r)
    phase_e_summary(r, (cap_total, cap_ow))
    r.print_and_exit()


if __name__ == "__main__":
    main()

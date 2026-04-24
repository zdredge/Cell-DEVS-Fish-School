#ifndef CELL_LOGIC_HPP
#define CELL_LOGIC_HPP

#include <algorithm>
#include <limits>
#include <random>
#include <string>
#include <unordered_map>
#include <vector>
#include <functional>

#include <cadmium/modeling/celldevs/asymm/cell.hpp>

#include "state.hpp"

using namespace cadmium::celldevs;

// Helper: parse "(col,row)" → row, col
inline void parseCellId(const std::string& id, int& row, int& col) {
    sscanf(id.c_str(), "(%d,%d)", &col, &row);
}

// Helper: format row, col → "(col,row)"
inline std::string makeCellId(int row, int col) {
    return "(" + std::to_string(col) + "," + std::to_string(row) + ")";
}

// Shared local-computation function used by both FishCell and PredatorCell.
// A single function is used because predators move between cells each step, so
// every cell must handle presence values 0 (empty), 5 (fish), and 10 (predator).
// The FishCell / PredatorCell split is preserved for factory routing and
// configuration semantics but the computation is identical.
inline CellState computeCellLocal(
    const std::string& cellId,
    CellState state,
    const std::unordered_map<std::string, NeighborData<CellState, double>>& neighborhood)
{
    CellState nextState = state;

    int myRow, myCol;
    parseCellId(cellId, myRow, myCol);

    // helpers
    
    // Look up neighbor at relative offset (dx=East+, dy=South+)
    auto getNeighbors = [&](int dx, int dy) -> CellState {
        std::string targetId = makeCellId(myRow + dy, myCol + dx);
        auto it = neighborhood.find(targetId);
        if (it != neighborhood.end() && it->second.state != nullptr) {
            return *it->second.state;
        }
        CellState wall;
        wall.presence = -1;
        return wall;
    };

    // Vicinity of the edge from this cell to the neighbor at (dx, dy).
    // Positive = water current assists movement in that direction; negative = opposes.
    auto getVicinityTo = [&](int dx, int dy) -> double {
        std::string targetId = makeCellId(myRow + dy, myCol + dx);
        auto it = neighborhood.find(targetId);
        return (it != neighborhood.end()) ? it->second.vicinity : 0.0;
    };

    auto dirToDelta = [](int dir, int& dx, int& dy) {
        dx = dy = 0;
        switch (dir) {
            case (int)Direction::EAST:  dx =  1; break;
            case (int)Direction::WEST:  dx = -1; break;
            case (int)Direction::SOUTH: dy =  1; break;
            case (int)Direction::NORTH: dy = -1; break;
            default: break;
        }
    };

    auto oppositeDir = [](int dir) -> int {
        switch (dir) {
            case 1: return 3; case 3: return 1;
            case 2: return 4; case 4: return 2;
            default: return 0;
        }
    };

    auto isReverseDir = [](int d1, int d2) -> bool {
        return (d1 == 1 && d2 == 3) || (d1 == 3 && d2 == 1) ||
               (d1 == 2 && d2 == 4) || (d1 == 4 && d2 == 2);
    };

    // Range-2 school check: target fish has any adjacent fish (excluding the current cell)
    auto isInSchool = [&](int dx, int dy) -> bool {
        if (getNeighbors(dx, dy).presence != 5) return false;
        if (getNeighbors(dx + 1, dy).presence == 5 && !(dx + 1 == 0 && dy == 0)) return true;
        if (getNeighbors(dx - 1, dy).presence == 5 && !(dx - 1 == 0 && dy == 0)) return true;
        if (getNeighbors(dx, dy + 1).presence == 5 && !(dx == 0 && dy + 1 == 0)) return true;
        if (getNeighbors(dx, dy - 1).presence == 5 && !(dx == 0 && dy - 1 == 0)) return true;
        return false;
    };

    // Returns true if any predator is committed to moving into cell at (toX, toY).
    // Predator commitments are read from state.direction (the previously-computed move).
    // Note: with multiple predators heading to the same cell there can be rare false
    // positives (one of them won't actually arrive); fish error on the side of caution.
    auto isPredatorHeadingTo = [&](int toX, int toY) -> bool {
        CellState e = getNeighbors(toX + 1, toY);
        if (e.presence == 10 && e.direction == (int)Direction::WEST) return true;
        CellState w = getNeighbors(toX - 1, toY);
        if (w.presence == 10 && w.direction == (int)Direction::EAST) return true;
        CellState s = getNeighbors(toX, toY + 1);
        if (s.presence == 10 && s.direction == (int)Direction::NORTH) return true;
        CellState n = getNeighbors(toX, toY - 1);
        if (n.presence == 10 && n.direction == (int)Direction::SOUTH) return true;
        return false;
    };

    // Fish movement priority check (West > East > North > South)
    // Cooperative (1) and selfish (2) escape override the school anchor.
    // Platoon vacating: a target cell with a fish moving the same direction
    // counts as "vacating" — enables coordinated school translation.
    std::function<bool(int, int, int, int, int)> canMoveTo = [&](int fromX, int fromY, int toX, int toY, int dir) -> bool {
        CellState fish = getNeighbors(fromX, fromY);
        if (fish.presence != 5 || fish.direction != dir) return false;
        if (fish.behavior == 0 && isInSchool(fromX, fromY)) return false;
        CellState target = getNeighbors(toX, toY);
        if (target.presence != 0) {
            bool platoon = target.presence == 5
                        && target.direction == dir
                        && (target.behavior != 0 || !isInSchool(toX, toY));
            if (!platoon) return false;
            // check to see if the vacating fish can actually move or not
            int nextX = toX + (dir == (int)Direction::EAST ? 1 : dir == (int)Direction::WEST ? -1 : 0);
            int nextY = toY + (dir == (int)Direction::SOUTH ? 1 : dir == (int)Direction::NORTH ? -1 : 0);
            
            if (!canMoveTo(toX, toY, nextX, nextY, dir)) {
                return false; // The platoon is blocked up ahead. Do not move.
            }
        }
        if (isPredatorHeadingTo(toX, toY)) return false;

        // A competing fish only blocks priority if it can actually move
        auto isCompetitor = [&](int cx, int cy, int compDir) -> bool {
            CellState comp = getNeighbors(cx, cy);
            if (comp.presence != 5 || comp.direction != compDir) return false;
            if (comp.behavior == 0 && isInSchool(cx, cy)) return false;
            return true;
        };

        if (dir == (int)Direction::EAST) {
            if (isCompetitor(toX + 1, toY, (int)Direction::WEST)) return false;
        }
        else if (dir == (int)Direction::NORTH) {
            if (isCompetitor(toX + 1, toY, (int)Direction::WEST)) return false;
            if (isCompetitor(toX - 1, toY, (int)Direction::EAST)) return false;
        }
        else if (dir == (int)Direction::SOUTH) {
            if (isCompetitor(toX + 1, toY, (int)Direction::WEST)) return false;
            if (isCompetitor(toX - 1, toY, (int)Direction::EAST)) return false;
            if (isCompetitor(toX, toY + 1, (int)Direction::NORTH)) return false;
        }
        return true;
    };

    static thread_local std::mt19937 rng(std::random_device{}());

    // MOVEMENT PHASE: departures, then arrivals (predator > fish)

    // Predator departure
    if (state.presence == 10) {
        if (state.direction != 0) {
            int dx, dy;
            dirToDelta(state.direction, dx, dy);
            CellState target = getNeighbors(dx, dy);
            // Predator can move if target is not wall and not another predator
            if (target.presence != -1 && target.presence != 10) {
                nextState.presence = 0;
            }
        }
    }
    // Fish departure
    else if (state.presence == 5) {
        auto depart = [&]() { nextState.presence = 0; nextState.orientation = 0; };
        switch (state.direction) {
            case (int)Direction::EAST:  if (canMoveTo(0, 0,  1,  0, state.direction)) depart(); break;
            case (int)Direction::WEST:  if (canMoveTo(0, 0, -1,  0, state.direction)) depart(); break;
            case (int)Direction::SOUTH: if (canMoveTo(0, 0,  0,  1, state.direction)) depart(); break;
            case (int)Direction::NORTH: if (canMoveTo(0, 0,  0, -1, state.direction)) depart(); break;
            default: break;
        }
    }

    // Predator arrival (priority over fish)
    // If a fish was here and didn't escape, this is a CAPTURE.
    bool predatorArrived = false;
    if (isPredatorHeadingTo(0, 0) && nextState.presence != 10) {
        predatorArrived = true;
        nextState.presence = 10;
        if      (getNeighbors( 1, 0).presence == 10 && getNeighbors( 1, 0).direction == (int)Direction::WEST)
            nextState.orientation = (int)Direction::WEST;
        else if (getNeighbors(-1, 0).presence == 10 && getNeighbors(-1, 0).direction == (int)Direction::EAST)
            nextState.orientation = (int)Direction::EAST;
        else if (getNeighbors(0,  1).presence == 10 && getNeighbors(0,  1).direction == (int)Direction::NORTH)
            nextState.orientation = (int)Direction::NORTH;
        else if (getNeighbors(0, -1).presence == 10 && getNeighbors(0, -1).direction == (int)Direction::SOUTH)
            nextState.orientation = (int)Direction::SOUTH;
    }

    // Fish arrival
    if (!predatorArrived && nextState.presence == 0) {
        if      (canMoveTo( 1,  0, 0, 0, (int)Direction::WEST))  { nextState.presence = 5; nextState.orientation = (int)Direction::WEST;  }
        else if (canMoveTo(-1,  0, 0, 0, (int)Direction::EAST))  { nextState.presence = 5; nextState.orientation = (int)Direction::EAST;  }
        else if (canMoveTo( 0,  1, 0, 0, (int)Direction::NORTH)) { nextState.presence = 5; nextState.orientation = (int)Direction::NORTH; }
        else if (canMoveTo( 0, -1, 0, 0, (int)Direction::SOUTH)) { nextState.presence = 5; nextState.orientation = (int)Direction::SOUTH; }
    }

    // DIRECTION PHASE: compute next-step intent for whoever is here now

    if (nextState.presence == 10) {
        // PREDATOR DIRECTION COMPUTATION

        // Scan range-6 neighborhood for nearest fish (presence==5)
        int minFishDist = 999;
        int visibleFishCount = 0;
        std::vector<std::pair<int,int>> nearestFish;
        for (const auto& [neighborId, neighborData] : neighborhood) {
            if (neighborData.state == nullptr || neighborId == cellId) continue;
            if (neighborData.state->presence != 5) continue;
            ++visibleFishCount;
            int nRow, nCol;
            parseCellId(neighborId, nRow, nCol);
            int dist = abs(nRow - myRow) + abs(nCol - myCol);
            if (dist < minFishDist) {
                minFishDist = dist;
                nearestFish.clear();
                nearestFish.push_back({nRow, nCol});
            } else if (dist == minFishDist) {
                nearestFish.push_back({nRow, nCol});
            }
        }

        // Allowed directions (turning limit: no reversals)
        std::vector<int> allowed;
        if (nextState.orientation == 0) {
            allowed = {1, 2, 3, 4};
        } else {
            for (int d = 1; d <= 4; d++) {
                if (!isReverseDir(nextState.orientation, d)) allowed.push_back(d);
            }
        }

        int predDir = 0;

        // Strong-opposing-current threshold: predator declines to enter an
        // edge whose vicinity is <= this value (current resistance).
        const double CURRENT_BLOCK = -0.5;

        if (nearestFish.empty()) {
            // No fish — random valid allowed direction, excluding strong-opposing-current edges
            std::vector<int> validAllowed;
            for (int d : allowed) {
                int dx, dy;
                dirToDelta(d, dx, dy);
                CellState t = getNeighbors(dx, dy);
                if (t.presence == -1 || t.presence == 10) continue;
                if (getVicinityTo(dx, dy) <= CURRENT_BLOCK) continue;
                validAllowed.push_back(d);
            }
            if (!validAllowed.empty()) {
                std::uniform_int_distribution<int> pick(0, (int)validAllowed.size() - 1);
                predDir = validAllowed[pick(rng)];
            }
        } else {
            // Overwhelmed-by-school confusion: probability of stall scales
            // linearly with visible fish count, capped so the predator always
            // has at least (1 - CAP) chance to act (no permanent paralysis).
            const double CONFUSION_PER_FISH = 0.06;
            const double CONFUSION_CAP      = 0.36;
            double confProb = std::min(CONFUSION_CAP,
                                       CONFUSION_PER_FISH * visibleFishCount);
            std::uniform_real_distribution<double> prob(0.0, 1.0);
            if (prob(rng) < confProb) {
                predDir = 0;  // stall this tick
            } else {
                // Pick random target among equidistant fish (confusion effect)
                std::uniform_int_distribution<int> pick(0, (int)nearestFish.size() - 1);
                auto target = nearestFish[pick(rng)];
                int tRow = target.first, tCol = target.second;
                int dCol = tCol - myCol;
                int dRow = tRow - myRow;

                int preferred = 0;
                if (abs(dCol) > abs(dRow)) {
                    preferred = dCol > 0 ? (int)Direction::EAST : (int)Direction::WEST;
                } else if (abs(dRow) > abs(dCol)) {
                    preferred = dRow > 0 ? (int)Direction::SOUTH : (int)Direction::NORTH;
                } else {
                    std::uniform_int_distribution<int> coin(0, 1);
                    preferred = coin(rng) == 0
                        ? (dCol > 0 ? (int)Direction::EAST : (int)Direction::WEST)
                        : (dRow > 0 ? (int)Direction::SOUTH : (int)Direction::NORTH);
                }

                if (std::find(allowed.begin(), allowed.end(), preferred) != allowed.end()) {
                    predDir = preferred;
                } else {
                    // Turning limit blocks preferred — pick best allowed by distance reduction
                    int bestDir = 0, bestScore = -999;
                    for (int d : allowed) {
                        int ddx, ddy;
                        dirToDelta(d, ddx, ddy);
                        int newDist = abs(dCol - ddx) + abs(dRow - ddy);
                        int score = minFishDist - newDist;
                        if (score > bestScore) { bestScore = score; bestDir = d; }
                    }
                    predDir = bestDir;
                }

                // Validate target cell. If blocked, re-score allowed directions
                // by distance reduction (ignoring blocked ones) — keeps predator
                // heading toward prey instead of picking the first clear tile.
                int tdx, tdy;
                dirToDelta(predDir, tdx, tdy);
                CellState targetCell = getNeighbors(tdx, tdy);
                if (targetCell.presence == -1 || targetCell.presence == 10) {
                    predDir = 0;
                    int bestScore = -999;
                    for (int d : allowed) {
                        int ddx, ddy;
                        dirToDelta(d, ddx, ddy);
                        CellState t = getNeighbors(ddx, ddy);
                        if (t.presence == -1 || t.presence == 10) continue;
                        int newDist = abs(dCol - ddx) + abs(dRow - ddy);
                        int score = minFishDist - newDist;
                        if (score > bestScore) { bestScore = score; predDir = d; }
                    }
                }

                // Current resistance: strong opposing current has a chance to stall a predator
                // Does not fully stall them, as they should attempt to resist it rather than permanently giving up
                if (predDir != 0) {
                    int sdx, sdy;
                    dirToDelta(predDir, sdx, sdy);
                    if (getVicinityTo(sdx, sdy) <= CURRENT_BLOCK) {
                        std::uniform_real_distribution<double> dragChance(0.0, 1.0);
                        // 50% chance to stall when fighting strong current
                        if (dragChance(rng) < 0.5) { 
                        predDir = 0;
                        }
                    }
                }
            }
        }

        nextState.direction = predDir;
        nextState.behavior = 0;
        nextState.predatorDist = 0;
        nextState.predatorDir = 0;
    }
    else if (nextState.presence == 5) {
        // FISH DIRECTION COMPUTATION

        // Detect nearest predator within range 4
        // Also track predator's orientation (its movement direction) for use in selfish-escape swerve calculation.
        int nearestPredDist = 0;
        int nearestPredDir = 0;
        int nearestPredOrientation = 0;
        for (const auto& [neighborId, neighborData] : neighborhood) {
            if (neighborData.state == nullptr || neighborId == cellId) continue;
            if (neighborData.state->presence != 10) continue;
            int nRow, nCol;
            parseCellId(neighborId, nRow, nCol);
            int dist = abs(nRow - myRow) + abs(nCol - myCol);
            if (dist <= 4 && (nearestPredDist == 0 || dist < nearestPredDist)) {
                nearestPredDist = dist;
                int dCol = nCol - myCol;
                int dRow = nRow - myRow;
                // predatorDir = direction FROM which the predator approaches
                if (abs(dCol) >= abs(dRow)) {
                    nearestPredDir = dCol > 0 ? (int)Direction::EAST : (int)Direction::WEST;
                } else {
                    nearestPredDir = dRow > 0 ? (int)Direction::SOUTH : (int)Direction::NORTH;
                }
                nearestPredOrientation = neighborData.state->orientation;
            }
        }
        // Snapshot the direct-sighting distance before relay overrides it.
        // Selfish escape must be triggered only by direct vision: a relayed
        // alarm at dist 2 means a schoolmate saw the predator one cell away,
        // not us — we should still cooperate, not panic-swerve.
        int directPredDist = nearestPredDist;

        // Alarm relay + self-decay 
        // Propagates predator awareness through the school so that schooling fish
        // join cooperative escape when any schoolmate has an active alarm. Direct
        // vision caps at range 4; relay fills in the back of the school.
        // Sentinel: predatorDist == 0 means "no alarm" — never enter arithmetic on it.
        // Always carries predatorDir paired with predatorDist so fleeDir is well-defined.
        const int RELAY_THRESHOLD = 7;   // direct range 4 + up to 3 hops of relay
        if (nearestPredDist == 0) {
            int bestDist = 0;   // 0 = no candidate yet
            int bestDir  = 0;

            auto consider = [&](int d, int dir) {
                if (d <= 0 || dir == 0) return;
                if (bestDist == 0 || d < bestDist) {
                    bestDist = d;
                    bestDir  = dir;
                }
            };

            if (state.predatorDist > 0) {
                consider(state.predatorDist + 1, state.predatorDir);
            }

            for (const auto& [nid, nd] : neighborhood) {
                if (nd.state == nullptr || nid == cellId) continue;
                if (nd.state->presence != 5) continue;
                if (nd.state->predatorDist <= 0) continue;
                int nr, nc; parseCellId(nid, nr, nc);
                int hop = std::abs(nr - myRow) + std::abs(nc - myCol);
                consider(nd.state->predatorDist + hop, nd.state->predatorDir);
            }

            if (bestDist > 0 && bestDist <= RELAY_THRESHOLD) {
                nearestPredDist = bestDist;
                nearestPredDir  = bestDir;
            }
        }

        // Paired-invariant guard: dist > 0 must have a paired direction.
        if (nearestPredDist > 0 && nearestPredDir == 0) {
            nearestPredDist = 0;
        }

        nextState.predatorDist = nearestPredDist;
        nextState.predatorDir = nearestPredDir;

        // Determine BP
        // schooling: no alarm anywhere
        //
        // selfish: direct dist <= 2 — fires one tick early so the swerve
        // executes BEFORE the predator can step into the fish's
        // cell. Triggering at dist == 1 was too late: predator
        // arrival and fish swerve resolve in the same tick.
        //
        // cooperative: direct 3-4 or any relayed alarm
        if (nearestPredDist == 0) {
            nextState.behavior = 0;
        } else if (directPredDist > 0 && directPredDist <= 2) {
            nextState.behavior = 2;
        } else {
            nextState.behavior = 1;
        }

        // Ghost cell / blind spot setup
        int srcX = 0, srcY = 0;
        bool inSchool;
        if (state.presence == 0) {
            // Just arrived: source cell is opposite of arrival orientation
            if      (nextState.orientation == (int)Direction::WEST)  srcX =  1;
            else if (nextState.orientation == (int)Direction::EAST)  srcX = -1;
            else if (nextState.orientation == (int)Direction::NORTH) srcY =  1;
            else if (nextState.orientation == (int)Direction::SOUTH) srcY = -1;

            auto isSchoolmate = [&](int dx, int dy, int towardDir) -> bool {
                if (dx == srcX && dy == srcY) return false;
                CellState n = getNeighbors(dx, dy);
                return n.presence == 5 && (n.direction == 0 || n.direction == towardDir);
            };
            inSchool = isSchoolmate( 1,  0, (int)Direction::WEST)  ||
                       isSchoolmate(-1,  0, (int)Direction::EAST)  ||
                       isSchoolmate( 0,  1, (int)Direction::NORTH) ||
                       isSchoolmate( 0, -1, (int)Direction::SOUTH);
        } else {
            if      (state.orientation == (int)Direction::EAST)  { srcX = -1; srcY =  0; }
            else if (state.orientation == (int)Direction::WEST)  { srcX =  1; srcY =  0; }
            else if (state.orientation == (int)Direction::NORTH) { srcX =  0; srcY =  1; }
            else if (state.orientation == (int)Direction::SOUTH) { srcX =  0; srcY = -1; }
            inSchool = getNeighbors( 1,  0).presence == 5 ||
                       getNeighbors(-1,  0).presence == 5 ||
                       getNeighbors( 0,  1).presence == 5 ||
                       getNeighbors( 0, -1).presence == 5;
        }

        // Compute schooling direction (used by behaviors 0 and 1)
        int schoolDir = 0;
        if (!inSchool) {
            auto checkPresence = [&](int dx, int dy) -> bool {
                if (dx == srcX && dy == srcY) return false;
                CellState n = getNeighbors(dx, dy);
                if (n.presence != 5) return false;
                // Anti-chase: ignore range-1 fish moving away from this cell
                int currDist = (dx < 0 ? -dx : dx) + (dy < 0 ? -dy : dy);
                if (currDist == 1 && n.direction != 0) {
                    int ndx = dx, ndy = dy;
                    if      (n.direction == (int)Direction::EAST)  ndx++;
                    else if (n.direction == (int)Direction::WEST)  ndx--;
                    else if (n.direction == (int)Direction::NORTH) ndy--;
                    else if (n.direction == (int)Direction::SOUTH) ndy++;
                    int newDist = (ndx < 0 ? -ndx : ndx) + (ndy < 0 ? -ndy : ndy);
                    if (newDist > currDist) return false;
                }
                return true;
            };

            bool fishWest  = checkPresence(-1, 0) || checkPresence(-2, 0);
            bool fishEast  = checkPresence( 1, 0) || checkPresence( 2, 0);
            bool fishNorth = checkPresence( 0,-1) || checkPresence( 0,-2);
            bool fishSouth = checkPresence( 0, 1) || checkPresence( 0, 2);
            bool fishEastInSchool  = (checkPresence( 1, 0) && isInSchool( 1, 0)) ||
                                     (checkPresence( 2, 0) && isInSchool( 2, 0));
            bool fishSouthInSchool = (checkPresence( 0, 1) && isInSchool( 0, 1)) ||
                                     (checkPresence( 0, 2) && isInSchool( 0, 2));

            std::vector<int> validDirs;
            if (getNeighbors( 1,  0).presence != -1) validDirs.push_back((int)Direction::EAST);
            if (getNeighbors(-1,  0).presence != -1) validDirs.push_back((int)Direction::WEST);
            if (getNeighbors( 0,  1).presence != -1) validDirs.push_back((int)Direction::SOUTH);
            if (getNeighbors( 0, -1).presence != -1) validDirs.push_back((int)Direction::NORTH);
            if (validDirs.empty()) validDirs = {1, 2, 3, 4};
            std::uniform_int_distribution<int> dist(0, (int)validDirs.size() - 1);
            schoolDir = validDirs[dist(rng)];

            if (fishWest) {
                schoolDir = (int)Direction::WEST;
            } else if (fishEastInSchool) {
                schoolDir = (int)Direction::EAST;
            } else if (!fishEast) {
                if      (fishNorth)         schoolDir = (int)Direction::NORTH;
                else if (fishSouthInSchool) schoolDir = (int)Direction::SOUTH;
            }
        }

        // Apply BP-specific direction logic
        if (nextState.behavior == 0) {
            // SCHOOLING
            nextState.direction = inSchool ? 0 : schoolDir;
        }
        else if (nextState.behavior == 1) {
            // COOPERATIVE ESCAPE: consensus flee direction = oppositeDir(nearestPredDir).
            // All schooled fish compute the same fleeDir and shift together via the
            // platoon-vacating rule in canMoveTo. If the consensus direction is blocked
            // (wall or incoming predator), prefer a current-assisted perpendicular
            // before falling back to schoolDir — lets the school exploit currents
            // when pushed against a wall.
            
            // Reluctance: each cooperatively-escaping fish independently rolls; with
            // probability (1 - P_FLEE) it holds station (direction=0) this tick.
            // Lowers the school's effective flee speed below the predator's, so the
            // gap closes and captures happen in open water rather than against a wall.
            // Independent rolls intentionally fragment the school via the platoon
            // bottleneck in canMoveTo — stragglers become easier targets.
            constexpr double P_FLEE = 0.8;
            std::uniform_real_distribution<double> reluctance(0.0, 1.0);
            if (reluctance(rng) >= P_FLEE) {
                nextState.direction = 0;
            } else {
                int fleeDir = oppositeDir(nearestPredDir);
                int fdx, fdy;
                dirToDelta(fleeDir, fdx, fdy);
                bool fleeValid = fleeDir != 0
                              && getNeighbors(fdx, fdy).presence != -1
                              && !isPredatorHeadingTo(fdx, fdy);
                if (fleeValid) {
                    nextState.direction = fleeDir;
                } else {
                    int perpA, perpB;
                    if (fleeDir == (int)Direction::EAST || fleeDir == (int)Direction::WEST) {
                        perpA = (int)Direction::NORTH; perpB = (int)Direction::SOUTH;
                    } else {
                        perpA = (int)Direction::EAST;  perpB = (int)Direction::WEST;
                    }
                    int bestPerp = 0;
                    // Among the two perpendiculars, prefer the one with better vicinity (current-assisted)
                    double bestVic = -std::numeric_limits<double>::infinity();
                    for (int p : {perpA, perpB}) {
                        int pdx, pdy;
                        dirToDelta(p, pdx, pdy);
                        if (getNeighbors(pdx, pdy).presence == -1) continue;
                        if (isPredatorHeadingTo(pdx, pdy)) continue;
                        double v = getVicinityTo(pdx, pdy);
                        if (v > bestVic) { bestVic = v; bestPerp = p; }
                    }
                    nextState.direction = bestPerp != 0 ? bestPerp : schoolDir;
                }
            }
        }
        else {
            // SELFISH ESCAPE: swerve perpendicular to the predator's movement
            // direction (its orientation), overriding school anchor. If
            // the predator has no orientation yet, fall back to the approach
            // axis (direction FROM fish to predator).

            // "Predator Lunge" simulation: 30% chance the fish panics and
            // hesitates when a predator is this close, letting the predator
            // close the gap and strike in open water.
            std::uniform_real_distribution<double> panic(0.0, 1.0);
            if (panic(rng) < 0.30) {
                nextState.direction = 0;
            } else {
                int swerveAxis = nearestPredOrientation != 0 ? nearestPredOrientation
                                                             : nearestPredDir;
                int perpA, perpB;
                if (swerveAxis == (int)Direction::EAST || swerveAxis == (int)Direction::WEST) {
                    perpA = (int)Direction::NORTH;
                    perpB = (int)Direction::SOUTH;
                } else {
                    perpA = (int)Direction::EAST;
                    perpB = (int)Direction::WEST;
                }

                int adx, ady, bdx, bdy;
                dirToDelta(perpA, adx, ady);
                dirToDelta(perpB, bdx, bdy);
                bool validA = getNeighbors(adx, ady).presence != -1 && !isPredatorHeadingTo(adx, ady);
                bool validB = getNeighbors(bdx, bdy).presence != -1 && !isPredatorHeadingTo(bdx, bdy);

                if (validA && validB) {
                    // Prefer the current-assisted perpendicular 80% of the time;
                    // 20% ignore the current (random coin flip) to avoid the fish
                    // becoming perfectly predictable in strong-current zones.
                    double vA = getVicinityTo(adx, ady);
                    double vB = getVicinityTo(bdx, bdy);
                    std::uniform_real_distribution<double> prob(0.0, 1.0);
                    if (vA > vB && prob(rng) < 0.8) {
                        nextState.direction = perpA;
                    } else if (vB > vA && prob(rng) < 0.8) {
                        nextState.direction = perpB;
                    } else {
                        std::uniform_int_distribution<int> coin(0, 1);
                        nextState.direction = coin(rng) == 0 ? perpA : perpB;
                    }
                } else if (validA) {
                    nextState.direction = perpA;
                } else if (validB) {
                    nextState.direction = perpB;
                } else {
                    // Both perpendiculars blocked — try direct flee, then any escape
                    int fleeDir = oppositeDir(nearestPredDir);
                    int fdx, fdy;
                    dirToDelta(fleeDir, fdx, fdy);
                    if (fleeDir != 0 && getNeighbors(fdx, fdy).presence != -1
                        && !isPredatorHeadingTo(fdx, fdy)) {
                        nextState.direction = fleeDir;
                    } else {
                        // Last-ditch: pick valid direction with the best vicinity
                        // (current-assisted), random among ties.
                        std::vector<int> bestDirs;
                        double bestVic = -std::numeric_limits<double>::infinity();
                        for (int d = 1; d <= 4; d++) {
                            int ddx, ddy;
                            dirToDelta(d, ddx, ddy);
                            if (getNeighbors(ddx, ddy).presence == -1) continue;
                            if (isPredatorHeadingTo(ddx, ddy)) continue;
                            double v = getVicinityTo(ddx, ddy);
                            if (v > bestVic) { bestVic = v; bestDirs = {d}; }
                            else if (v == bestVic) { bestDirs.push_back(d); }
                        }
                        if (!bestDirs.empty()) {
                            std::uniform_int_distribution<int> pick(0, (int)bestDirs.size() - 1);
                            nextState.direction = bestDirs[pick(rng)];
                        } else {
                            nextState.direction = 0;
                        }
                    }
                }
            }
        }
    } else {
        // Empty cell — clear all transient fields
        nextState.direction = 0;
        nextState.orientation = 0;
        nextState.behavior = 0;
        nextState.predatorDist = 0;
        nextState.predatorDir = 0;
    }

    return nextState;
}

#endif // CELL_LOGIC_HPP

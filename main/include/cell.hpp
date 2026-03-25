#ifndef CELL_HPP
#define CELL_HPP

#include <random>

#include <cadmium/modeling/celldevs/grid/cell.hpp>
#include <cadmium/modeling/celldevs/grid/config.hpp>

#include "state.hpp"

using namespace cadmium::celldevs;

// atomic model definition
class FishCell : public GridCell<FishState, double> {
    public: 
        FishCell(const std::vector<int>&id, 
                 const std::shared_ptr<const GridCellConfig<FishState, double>>&config)
        : GridCell<FishState, double>(id, config) {}

        // local computation function (tau)
        [[nodiscard]] FishState localComputation(FishState state, const std::unordered_map<std::vector<int>, NeighborData<FishState, double>>& neighborhood) const override {
            
            /*
            Basic flow:
            1. Movement: Determine if a fish wins a priority movement, or if an empty cell will have a fish move into it
            2. Vision: If the cell is occupied after movement, determine the fish's new direction based on its neighbors in the next step.
                - fish will either anchor or orient in a direction based on the presence of neighbors, with a 2-cell vision range and blind spot directly behind them.
            */
            FishState nextState = state;

            // helper to loop through neighbors — offset is relative; convert to absolute first
            auto getNeighbors = [&](int dx, int dy) -> FishState {
                try {
                    std::vector<int> position = cellTo({dx, dy});
                    if (neighborhood.find(position) != neighborhood.end()) {
                        if (neighborhood.at(position).state != nullptr) {
                            return *neighborhood.at(position).state;
                        }
                    }
                } catch (...) {}
                FishState wall;
                wall.presence = -1; // out of bounds, fish has reached a border cell
                return wall;
            };

            // helper to check if a neighbor fish at (dx, dy) is part of a school.
            // Uses range-2 neighborhood to inspect the target fish's own von neumann neighbors,
            // excluding the current cell (0,0) which would always be adjacent to the target.
            auto isInSchool = [&](int dx, int dy) -> bool {
                if (getNeighbors(dx, dy).presence != 5) return false;
                if (getNeighbors(dx + 1, dy).presence == 5 && !(dx + 1 == 0 && dy == 0)) return true; // East neighbor
                if (getNeighbors(dx - 1, dy).presence == 5 && !(dx - 1 == 0 && dy == 0)) return true; // West neighbor
                if (getNeighbors(dx, dy + 1).presence == 5 && !(dx == 0 && dy + 1 == 0)) return true; // South neighbor
                if (getNeighbors(dx, dy - 1).presence == 5 && !(dx == 0 && dy - 1 == 0)) return true; // North neighbor
                return false;
            };

            // generate a random direction for a fish. Need to check out of bounds first to see valid directions
            static thread_local std::mt19937 rng(std::random_device{}());
            std::vector<int> validDirs;
            if (getNeighbors( 1,  0).presence != -1) validDirs.push_back((int)Direction::EAST);
            if (getNeighbors(-1,  0).presence != -1) validDirs.push_back((int)Direction::WEST);
            if (getNeighbors( 0,  1).presence != -1) validDirs.push_back((int)Direction::SOUTH);
            if (getNeighbors( 0, -1).presence != -1) validDirs.push_back((int)Direction::NORTH);
            if (validDirs.empty()) validDirs = {1, 2, 3, 4}; // fallback
            std::uniform_int_distribution<int> dist(0, (int)validDirs.size() - 1);
            int randomDirection = validDirs[dist(rng)];

            // movement helper (West > East > North > South)
            // Returns true if a fish at (fromX, fromY) is the priority winner to move to (toX, toY)
            auto canMoveTo = [&](int fromX, int fromY, int toX, int toY, int dir) -> bool {
                FishState fish = getNeighbors(fromX, fromY);
                // Must be a fish, not in a school, intending to move to the target, which must be empty
                if (fish.presence != 5 || isInSchool(fromX, fromY) || fish.direction != dir) return false;
                if (getNeighbors(toX, toY).presence != 0) return false;

                // Priority Check: Is anyone with higher priority moving to (toX, toY)?
                if (dir == (int)Direction::EAST) { 
                    // West-moving (from East) has higher priority
                    if (getNeighbors(toX + 1, toY).presence == 5 && getNeighbors(toX + 1, toY).direction == (int)Direction::WEST) return false;
                }
                else if (dir == (int)Direction::NORTH) { // North-moving
                    if (getNeighbors(toX + 1, toY).presence == 5 && getNeighbors(toX + 1, toY).direction == (int)Direction::WEST) return false;
                    if (getNeighbors(toX - 1, toY).presence == 5 && getNeighbors(toX - 1, toY).direction == (int)Direction::EAST) return false;
                }
                else if (dir == (int)Direction::SOUTH) { // South-moving
                    if (getNeighbors(toX + 1, toY).presence == 5 && getNeighbors(toX + 1, toY).direction == (int)Direction::WEST) return false;
                    if (getNeighbors(toX - 1, toY).presence == 5 && getNeighbors(toX - 1, toY).direction == (int)Direction::EAST) return false;
                    if (getNeighbors(toX, toY + 1).presence == 5 && getNeighbors(toX, toY + 1).direction == (int)Direction::NORTH) return false;                
                }
                return true; // No higher priority fish found
            };

            /*
            There are two scenarios to consider:
            1. If the cell is occupied
            2. If the cell is empty
            */

            // Scenario 1: Cell is occupied by a fish
            if (state.presence == 5) {
                nextState.orientation = 0;
                // Only vacate if the fish is the winner for its intended move
                if (canMoveTo(0, 0,  1,  0, (int)Direction::EAST)  || canMoveTo(0, 0, -1,  0, (int)Direction::WEST) ||
                    canMoveTo(0, 0,  0,  1, (int)Direction::SOUTH) || canMoveTo(0, 0,  0, -1, (int)Direction::NORTH)) {
                    nextState.presence = 0;
                }
            }
            // Scenario 2: Cell is empty
            else if (state.presence == 0) {
                // Priorities: West > East > North > South
                if      (canMoveTo( 1,  0, 0, 0, (int)Direction::WEST))  { nextState.presence = 5; nextState.orientation = (int)Direction::WEST;  }
                else if (canMoveTo(-1,  0, 0, 0, (int)Direction::EAST))  { nextState.presence = 5; nextState.orientation = (int)Direction::EAST;  }
                else if (canMoveTo( 0,  1, 0, 0, (int)Direction::NORTH)) { nextState.presence = 5; nextState.orientation = (int)Direction::NORTH; }
                else if (canMoveTo( 0, -1, 0, 0, (int)Direction::SOUTH)) { nextState.presence = 5; nextState.orientation = (int)Direction::SOUTH; }
            }
            
            if (nextState.presence == 5) {
                /*
                srcX/srcY identify the cell the fish just moved from, which is seen as a ghost cell
                Only relevant when the fish JUST ARRIVED this step (state.presence == 0).
                A fish that was already here has no ghost and must see all directions freely
                */ 
                int srcX = 0, srcY = 0;
                bool inSchool;

                if (state.presence == 0) {
                    /*
                    Fish just arrived — get source cell from the orientation and
                    use the stricter isSchoolmate check: exclude the ghost cell and require
                    the neighbor to be anchored or approaching

                    This prevents two fish from getting into a chase with each other
                    */  
                    if      (nextState.orientation == (int)Direction::WEST)  srcX =  1;
                    else if (nextState.orientation == (int)Direction::EAST)  srcX = -1;
                    else if (nextState.orientation == (int)Direction::NORTH) srcY =  1;
                    else if (nextState.orientation == (int)Direction::SOUTH) srcY = -1;

                    auto isSchoolmate = [&](int dx, int dy, int towardDir) -> bool {
                        if (dx == srcX && dy == srcY) return false; // exclude source cell (ghost cell)
                        FishState n = getNeighbors(dx, dy);
                        return n.presence == 5 && (n.direction == 0 || n.direction == towardDir); // must be anchored or moving toward this cell to be considered a schoolmate for an arriving fish
                    };

                    inSchool = isSchoolmate( 1,  0, (int)Direction::WEST)  ||
                               isSchoolmate(-1,  0, (int)Direction::EAST)  ||
                               isSchoolmate( 0,  1, (int)Direction::NORTH) ||
                               isSchoolmate( 0, -1, (int)Direction::SOUTH);
                } else {
                    // Fish was already here — get their blindspot based on their orientation
                    if      (state.orientation == (int)Direction::EAST)  { srcX = -1; srcY =  0; }
                    else if (state.orientation == (int)Direction::WEST)  { srcX =  1; srcY =  0; }
                    else if (state.orientation == (int)Direction::NORTH) { srcX =  0; srcY =  1; }
                    else if (state.orientation == (int)Direction::SOUTH) { srcX =  0; srcY = -1; }
                    // orientation == 0 means no prior movement, no blind spot (srcX/srcY remain 0,0)

                    // Any adjacent fish means we are in a school
                    inSchool = getNeighbors( 1,  0).presence == 5 ||
                               getNeighbors(-1,  0).presence == 5 ||
                               getNeighbors( 0,  1).presence == 5 ||
                               getNeighbors( 0, -1).presence == 5;
                }

                if (inSchool) {
                    nextState.direction = 0; // anchored fish have no movement 
                } else {
                    // 2-cell vision grouping rules (W > E > N > S), blind spot excluded
                    auto checkPresence = [&](int dx, int dy) -> bool {
                        if (dx == srcX && dy == srcY) return false; // exclude source cell
                        FishState n = getNeighbors(dx, dy);
                        if (n.presence != 5) return false;

                        /*
                        For neighbors at range 1, examine their intended move direction. 
                        If they are moving away from this cell, ignore them as potential schoolmates. 
                        This prevents chase cycles where two fish see each other, both move, 
                        and then see each other again in their new positions, endlessly chasing each other around.
                        */

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
                    // Check VN neighbors first for direct attraction, then range-2 for secondary attraction.
                    // No diagonal checks - maybe implement in term assignment 
                    bool fishWest  = checkPresence(-1, 0) || checkPresence(-2, 0);
                    bool fishEast  = checkPresence( 1, 0) || checkPresence( 2, 0);
                    bool fishNorth = checkPresence( 0,-1) || checkPresence( 0,-2);
                    bool fishSouth = checkPresence( 0, 1) || checkPresence( 0, 2);

                    /*
                    According to rules, a fish is attracted to an adjacent fish in the EAST or SOUTH direction
                    only if that fish is part of a school.

                    Allows the west/north-priority fish to move first and create a school before the east/south fish decide whether to move.
                    Prevents a chase scenario.
                    */
                    bool fishEastInSchool  = (checkPresence( 1, 0) && isInSchool( 1, 0)) ||
                                             (checkPresence( 2, 0) && isInSchool( 2, 0));
                    bool fishSouthInSchool = (checkPresence( 0, 1) && isInSchool( 0, 1)) ||
                                             (checkPresence( 0, 2) && isInSchool( 0, 2));

                    int moveDir = randomDirection;
                    if (fishWest) {
                        moveDir = (int)Direction::WEST;
                    } else if (fishEastInSchool) {
                        moveDir = (int)Direction::EAST;
                    } else if (!fishEast) {
                        // No fish horizontally at all — check vertical 
                        if      (fishNorth)         { moveDir = (int)Direction::NORTH; }
                        else if (fishSouthInSchool)  { moveDir = (int)Direction::SOUTH; }
                    }
                    nextState.direction = moveDir;
                }
            } else {
                // empty cell: reset direction to 0 to prevent phantom attraction
                nextState.direction = 0;
            }
            return nextState;
        }

        // delay function
        [[nodiscard]] double outputDelay(const FishState& state) const override {
            return 1.0; 
        }
    };

    #endif // CELL_HPP
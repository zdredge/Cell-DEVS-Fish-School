#ifndef STATE_HPP
#define STATE_HPP

#include <iostream>
#include <nlohmann/json.hpp>


// enum to define movement logic
enum class Direction {NONE = 0, EAST = 1, NORTH = 2, WEST = 3, SOUTH = 4};

struct CellState{
    int presence;     // 0=empty, 5=fish, 10=predator
    int direction;    // 0=none, 1=East, 2=North, 3=West, 4=South
    int orientation;  // previous movement direction
    int behavior;     // 0=schooling, 1=cooperative_escape, 2=selfish_escape
    int predatorDist; // Manhattan distance to nearest predator, 0=none
    int predatorDir;  // direction FROM which predator approaches, 0=none

    CellState() : presence(0), direction(0), orientation(0), behavior(0), predatorDist(0), predatorDir(0) {}
};

// operator overload to print cell state (Aligned to JSON Insertion Order)
std::ostream& operator<<(std::ostream& os, const CellState& state) {
    os << "<" << state.presence << "," << state.direction << "," << state.orientation
       << "," << state.behavior << "," << state.predatorDist << "," << state.predatorDir << ">";
    return os;
}

// operator!= overload to compare two CellState objects
bool operator!=(const CellState& c1, const CellState& c2) {
    return (c1.presence != c2.presence) || (c1.direction != c2.direction) || (c1.orientation != c2.orientation)
        || (c1.behavior != c2.behavior) || (c1.predatorDist != c2.predatorDist) || (c1.predatorDir != c2.predatorDir);
}

// parse JSON config to populate CellState
[[maybe_unused]] void from_json(const nlohmann::json& j, CellState& s) {
    j.at("presence").get_to(s.presence);
    j.at("direction").get_to(s.direction);
    j.at("orientation").get_to(s.orientation);
    s.behavior = j.value("behavior", 0);
    s.predatorDist = j.value("predatorDist", 0);
    s.predatorDir = j.value("predatorDir", 0);
}

#endif // STATE_HPP

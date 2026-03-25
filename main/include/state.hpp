#ifndef STATE_HPP
#define STATE_HPP

#include <iostream>
#include <nlohmann/json.hpp>


// enum to define movement logic
enum class Direction {NONE = 0, EAST = 1, NORTH = 2, WEST = 3, SOUTH = 4};

struct FishState{
    int presence;
    int direction;
    int orientation;

    FishState() : presence(0), direction(0), orientation(0) {}
};

// operator overload to print cell state (Aligned to JSON Insertion Order)
std::ostream& operator<<(std::ostream& os, const FishState& state) {
    // Order MUST match JSON exactly: presence, direction, orientation
    os << "<" << state.presence << "," << state.direction << "," << state.orientation << ">";
    return os;
}

// operator!= overload to compare two FishState objects
bool operator!=(const FishState& c1, const FishState& c2) {
    return (c1.presence != c2.presence) || (c1.direction != c2.direction) || (c1.orientation != c2.orientation);
}

// parse JSON config to populate FishState
[[maybe_unused]] void from_json(const nlohmann::json& j, FishState& s) {
    j.at("presence").get_to(s.presence);
    j.at("direction").get_to(s.direction);
    j.at("orientation").get_to(s.orientation);
}

#endif // STATE_HPP
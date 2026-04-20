#ifndef PREDATOR_CELL_HPP
#define PREDATOR_CELL_HPP

#include <string>

#include <cadmium/modeling/celldevs/asymm/cell.hpp>
#include <cadmium/modeling/celldevs/asymm/config.hpp>

#include "cell_logic.hpp"
#include "state.hpp"

using namespace cadmium::celldevs;

// PredatorCell — pursuit and capture logic.
// Shares its local computation with FishCell because predators move between
// cells each step, so any cell may host a predator at some point in the
// simulation. The class exists to tag predator starting positions in the
// configuration and to route them through a distinct factory branch.
class PredatorCell : public AsymmCell<CellState, double> {
    public:
        PredatorCell(const std::string& id,
                     const std::shared_ptr<const AsymmCellConfig<CellState, double>>& config)
        : AsymmCell<CellState, double>(id, config) {}

        [[nodiscard]] CellState localComputation(
            CellState state,
            const std::unordered_map<std::string, NeighborData<CellState, double>>& neighborhood) const override
        {
            return computeCellLocal(this->id, state, neighborhood);
        }

        [[nodiscard]] double outputDelay(const CellState& state) const override {
            return 1.0;
        }
};

#endif // PREDATOR_CELL_HPP

#ifndef FISH_CELL_HPP
#define FISH_CELL_HPP

#include <string>

#include <cadmium/modeling/celldevs/asymm/cell.hpp>
#include <cadmium/modeling/celldevs/asymm/config.hpp>

#include "cell_logic.hpp"
#include "state.hpp"

using namespace cadmium::celldevs;

// FishCell — schooling and BP-based evasion logic.
// Shares its local computation with PredatorCell because any cell may host a
// predator at runtime (predators move each step).
class FishCell : public AsymmCell<CellState, double> {
    public:
        FishCell(const std::string& id,
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

#endif // FISH_CELL_HPP

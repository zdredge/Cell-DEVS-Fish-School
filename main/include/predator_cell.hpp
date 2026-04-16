#ifndef PREDATOR_CELL_HPP
#define PREDATOR_CELL_HPP

#include <string>

#include <cadmium/modeling/celldevs/asymm/cell.hpp>
#include <cadmium/modeling/celldevs/asymm/config.hpp>

#include "state.hpp"

using namespace cadmium::celldevs;

// Predator cell stub — passes through current state unchanged.
// Full pursuit/capture logic will be implemented later
class PredatorCell : public AsymmCell<CellState, double> {
    public:
        PredatorCell(const std::string& id,
                     const std::shared_ptr<const AsymmCellConfig<CellState, double>>& config)
        : AsymmCell<CellState, double>(id, config) {}

        [[nodiscard]] CellState localComputation(CellState state, const std::unordered_map<std::string, NeighborData<CellState, double>>& neighborhood) const override {
            // Stub: predator stays in place, no behavior yet
            return state;
        }

        [[nodiscard]] double outputDelay(const CellState& state) const override {
            return 1.0;
        }
    };

#endif // PREDATOR_CELL_HPP

#include <cadmium/modeling/celldevs/asymm/coupled.hpp>
#include <cadmium/simulation/logger/csv.hpp>
#include <cadmium/simulation/root_coordinator.hpp>
#include <iostream>
#include <string>

#include "include/fish_cell.hpp"
#include "include/predator_cell.hpp"
#include "include/state.hpp"

using namespace cadmium::celldevs;

// Factory routes by "model" key in JSON config: "predator" -> PredatorCell,
// anything else -> FishCell. Both classes share their local computation because
// predators move between cells each timestep; the split is used so predator
// starting positions are tagged distinctly in the configuration.
std::shared_ptr<AsymmCell<CellState, double>> addCell(
    const std::string& cellId,
    const std::shared_ptr<const AsymmCellConfig<CellState, double>>& cellConfig)
{
    if (cellConfig->cellModel == "predator") {
        return std::make_shared<PredatorCell>(cellId, cellConfig);
    }
    return std::make_shared<FishCell>(cellId, cellConfig);
}

int main(int argc, char** argv) {
    if (argc < 2) {
        std::cout << "Usage: " << argv[0]
                  << " SCENARIO_CONFIG.json [MAX_SIMULATION_TIME (default: 50)]" << std::endl;
        return -1;
    }

    std::string configFilePath = argv[1];
    double simTime = (argc > 2) ? std::stod(argv[2]) : 50.0;
    std::string logFilePath = (argc > 3) ? argv[3] : "fish_school_log.csv";
    std::cout << "Starting simulation with config: " << configFilePath
              << " and max simulation time: " << simTime << std::endl;

    auto model = std::make_shared<AsymmCellDEVSCoupled<CellState, double>>(
        "fish_school", addCell, configFilePath);
    model->buildModel();

    auto rootCoordinator = cadmium::RootCoordinator(model);
    rootCoordinator.setLogger<cadmium::CSVLogger>(logFilePath, ";");
    rootCoordinator.start();
    rootCoordinator.simulate(simTime);
    rootCoordinator.stop();

    std::cout << "Simulation complete. Output written to " << logFilePath << std::endl;
    return 0;
}

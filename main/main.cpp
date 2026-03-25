#include <cadmium/modeling/celldevs/grid/coupled.hpp>
#include <cadmium/simulation/logger/csv.hpp>
#include <cadmium/simulation/root_coordinator.hpp>
#include <iostream>
#include <string>

#include "include/cell.hpp"
#include "include/state.hpp"

using namespace cadmium::celldevs;

std::shared_ptr<GridCell<FishState, double>> addGridCell(
    const coordinates& cellId,
    const std::shared_ptr<const GridCellConfig<FishState, double>>& cellConfig)
{
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
    std::cout << "Starting simulation with config: " << configFilePath
              << " and max simulation time: " << simTime << std::endl;

    auto model = std::make_shared<GridCellDEVSCoupled<FishState, double>>(
        "fish_school", addGridCell, configFilePath);
    model->buildModel();

    auto rootCoordinator = cadmium::RootCoordinator(model);
    rootCoordinator.setLogger<cadmium::CSVLogger>("fish_school_log.csv", ";");
    rootCoordinator.start();
    rootCoordinator.simulate(simTime);
    rootCoordinator.stop();

    std::cout << "Simulation complete. Output written to fish_school_log.csv" << std::endl;
    return 0;
}

#!/bin/bash

# Clean up previous build directory and old simulation logs
if [ -d "build" ]; then rm -Rf build; fi
rm -f *.csv

# Create a fresh build directory
mkdir -p build
cd build || exit

# Clean the build folder just in case
rm -rf *

# Configure the project using CMake
cmake ..

# Compile the executables
make

# Return to the root project folder
cd ..

echo "Compilation done. Executable is located in the bin/ folder."
echo "Run a scenario with: ./bin/fish_school config/<scenario>.json [sim_time]"

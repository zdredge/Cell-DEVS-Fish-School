cmake_minimum_required(VERSION 3.16)

project(Fish_School)

# Route all compiled executables to the bin directory
set(CMAKE_RUNTIME_OUTPUT_DIRECTORY ${CMAKE_CURRENT_SOURCE_DIR}/bin)

# Cadmium path — resolve include/ and json/include relative to the cadmium root.
# Cadmium's own CMakeLists exposes both via: target_include_directories(cadmium INTERFACE include/ json/include)
if(DEFINED ENV{CADMIUM})
    # $CADMIUM may point to the repo root or directly to the include/ subfolder
    set(CADMIUM_ROOT "$ENV{CADMIUM}/..")
    set(CADMIUM_PATHS "$ENV{CADMIUM}" "$ENV{CADMIUM}/include" "${CADMIUM_ROOT}/json/include")
else()
    set(CADMIUM_ROOT "${CMAKE_CURRENT_SOURCE_DIR}/../cadmium_v2")
    set(CADMIUM_PATHS "${CADMIUM_ROOT}/include" "${CADMIUM_ROOT}/json/include")
endif()

# Simulation executable
add_executable(fish_school main/main.cpp)

target_include_directories(fish_school PRIVATE "." "main/include" ${CADMIUM_PATHS})
target_compile_options(fish_school PUBLIC -std=gnu++17)

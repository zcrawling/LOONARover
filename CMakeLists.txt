cmake_minimum_required(VERSION 3.22)

project(loonar VERSION 0.2.0 DESCRIPTION "LOONAR rover platforms" LANGUAGES C CXX)

include(CTest)

set(CMAKE_C_STANDARD 99)
set(CMAKE_C_STANDARD_REQUIRED ON)
set(CMAKE_C_EXTENSIONS OFF)
set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

option(LOONAR_WARNINGS_AS_ERRORS "Treat compiler warnings as errors" ON)
option(LOONAR_ENABLE_SANITIZERS "Enable address and undefined behavior sanitizers" OFF)

add_library(loonar_project_options INTERFACE)
target_compile_features(loonar_project_options INTERFACE c_std_99 cxx_std_20)

add_library(loonar_project_warnings INTERFACE)
if(CMAKE_C_COMPILER_ID MATCHES "GNU|Clang" OR CMAKE_CXX_COMPILER_ID MATCHES "GNU|Clang")
  target_compile_options(
    loonar_project_warnings
    INTERFACE -Wall -Wextra -Wpedantic -Wconversion -Wshadow
              $<$<BOOL:${LOONAR_WARNINGS_AS_ERRORS}>:-Werror>)
endif()

if(LOONAR_ENABLE_SANITIZERS)
  if(CMAKE_C_COMPILER_ID MATCHES "GNU|Clang" OR CMAKE_CXX_COMPILER_ID MATCHES "GNU|Clang")
    target_compile_options(loonar_project_options INTERFACE -fno-omit-frame-pointer
                                                            -fsanitize=address,undefined)
    target_link_options(loonar_project_options INTERFACE -fno-omit-frame-pointer
                                                         -fsanitize=address,undefined)
  else()
    message(FATAL_ERROR "LOONAR_ENABLE_SANITIZERS requires GCC or Clang")
  endif()
endif()

# This build validates retained final-rover firmware reference assets only.
add_subdirectory(common/vehicle_gateway)
add_subdirectory(platforms/loonar/interfaces)
add_subdirectory(platforms/loonar/libs/wire_c)
add_subdirectory(platforms/loonar/firmware/control)

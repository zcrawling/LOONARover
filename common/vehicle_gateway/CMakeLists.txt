if(CMAKE_SOURCE_DIR STREQUAL CMAKE_CURRENT_SOURCE_DIR)
  cmake_minimum_required(VERSION 3.22)
  project(loonar_vehicle_gateway LANGUAGES CXX)
  include(CTest)
  add_library(loonar_project_options INTERFACE)
  add_library(loonar_project_warnings INTERFACE)
  target_compile_features(loonar_project_options INTERFACE cxx_std_20)
  target_compile_options(loonar_project_warnings INTERFACE -Wall -Wextra -Wpedantic -Werror)
endif()

add_library(loonar_gateway_core STATIC
  src/core.cpp
  src/protocol.cpp)
target_include_directories(loonar_gateway_core PUBLIC ${CMAKE_CURRENT_SOURCE_DIR}/include)
target_link_libraries(loonar_gateway_core PUBLIC loonar_project_options loonar_project_warnings)

add_executable(vehicle_gatewayd src/main.cpp)
target_link_libraries(vehicle_gatewayd PRIVATE loonar_gateway_core)

add_executable(vehicle_gatewayctl src/ctl.cpp)
target_link_libraries(vehicle_gatewayctl PRIVATE loonar_gateway_core)

if(BUILD_TESTING)
  foreach(test_name IN ITEMS gateway_core gateway_protocol)
    add_executable(test_${test_name} tests/test_${test_name}.cpp)
    target_link_libraries(test_${test_name} PRIVATE loonar_gateway_core)
    add_test(NAME gateway.${test_name} COMMAND test_${test_name})
  endforeach()
  add_executable(test_gateway_daemon tests/test_gateway_daemon.cpp)
  target_link_libraries(test_gateway_daemon PRIVATE loonar_gateway_core)
  add_test(NAME gateway.gateway_daemon COMMAND test_gateway_daemon $<TARGET_FILE:vehicle_gatewayd>)
endif()

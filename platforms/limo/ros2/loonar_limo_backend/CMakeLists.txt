cmake_minimum_required(VERSION 3.22)
project(loonar_limo_backend)

find_package(ament_cmake REQUIRED)
find_package(rclcpp REQUIRED)
find_package(geometry_msgs REQUIRED)
find_package(nav_msgs REQUIRED)
find_package(sensor_msgs REQUIRED)
find_package(limo_msgs REQUIRED)

get_filename_component(LOONAR_ROOT "${CMAKE_CURRENT_SOURCE_DIR}/../../../.." ABSOLUTE)
add_executable(loonar_limo_backend
  src/limo_backend_node.cpp
  ${LOONAR_ROOT}/common/vehicle_gateway/src/protocol.cpp)
target_include_directories(loonar_limo_backend PRIVATE ${LOONAR_ROOT}/common/vehicle_gateway/include)
ament_target_dependencies(loonar_limo_backend rclcpp geometry_msgs nav_msgs sensor_msgs limo_msgs)
target_compile_features(loonar_limo_backend PRIVATE cxx_std_20)
target_compile_options(loonar_limo_backend PRIVATE -Wall -Wextra -Wpedantic -Werror)
install(TARGETS loonar_limo_backend DESTINATION lib/${PROJECT_NAME})
install(DIRECTORY config DESTINATION share/${PROJECT_NAME})
ament_package()

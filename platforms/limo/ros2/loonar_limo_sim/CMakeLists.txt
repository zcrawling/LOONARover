cmake_minimum_required(VERSION 3.22)
project(loonar_limo_sim)

find_package(ament_cmake REQUIRED)
find_package(rclcpp REQUIRED)
find_package(sensor_msgs REQUIRED)

add_executable(tof_depth_adapter src/tof_depth_adapter.cpp)
ament_target_dependencies(tof_depth_adapter rclcpp sensor_msgs)
target_compile_features(tof_depth_adapter PRIVATE cxx_std_20)
target_compile_options(tof_depth_adapter PRIVATE -Wall -Wextra -Wpedantic -Werror)

install(TARGETS tof_depth_adapter DESTINATION lib/${PROJECT_NAME})
install(DIRECTORY launch urdf worlds config models DESTINATION share/${PROJECT_NAME})

ament_package()

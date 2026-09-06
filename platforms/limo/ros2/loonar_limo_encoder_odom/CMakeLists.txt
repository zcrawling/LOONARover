cmake_minimum_required(VERSION 3.8)
project(loonar_limo_encoder_odom)

find_package(ament_cmake REQUIRED)
find_package(geometry_msgs REQUIRED)
find_package(nav_msgs REQUIRED)
find_package(rclcpp REQUIRED)
find_package(sensor_msgs REQUIRED)
find_package(tf2 REQUIRED)

add_executable(wheel_odometer_node src/wheel_odometer_node.cpp)
ament_target_dependencies(wheel_odometer_node geometry_msgs nav_msgs rclcpp sensor_msgs tf2)
target_compile_features(wheel_odometer_node PRIVATE cxx_std_20)
target_compile_options(wheel_odometer_node PRIVATE -Wall -Wextra -Wpedantic -Werror)

install(TARGETS wheel_odometer_node DESTINATION lib/${PROJECT_NAME})
ament_package()

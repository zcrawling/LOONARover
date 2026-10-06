cmake_minimum_required(VERSION 3.16)
project(loonar_msgs)
find_package(ament_cmake REQUIRED)
find_package(rosidl_default_generators REQUIRED)
find_package(std_msgs REQUIRED)
find_package(geometry_msgs REQUIRED)
rosidl_generate_interfaces(${PROJECT_NAME}
  "msg/Stationary.msg"
  "msg/SafetyState.msg"
  "msg/BaseState.msg"
  "msg/TerrainCell.msg"
  "msg/TerrainMap.msg"
  "msg/TerrainDecision.msg"
  "msg/MotionStatus.msg"
  "msg/MotionResult.msg"
  "action/BuildTerrainMap.action"
  "action/ExecuteMotionPrimitive.action"
  "srv/PlanTerrain.srv"
  "srv/StopRegistration.srv"
  DEPENDENCIES std_msgs geometry_msgs)
ament_export_dependencies(rosidl_default_runtime)
ament_package()

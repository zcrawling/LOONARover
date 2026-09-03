project(LOONAR_VEHICLE_ADAPTER C)
add_cfe_app(loonar_vehicle_adapter fsw/src/loonar_vehicle_adapter_app.c)
set_target_properties(loonar_vehicle_adapter PROPERTIES OUTPUT_NAME lnr_vehicle)
target_include_directories(loonar_vehicle_adapter PUBLIC fsw/inc ${CMAKE_CURRENT_SOURCE_DIR}/../common)

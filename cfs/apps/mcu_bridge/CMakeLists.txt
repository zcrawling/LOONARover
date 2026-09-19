project(LOONAR_MCU_BRIDGE C)
add_cfe_app(loonar_mcu_bridge fsw/src/loonar_mcu_bridge_app.c)
set_target_properties(loonar_mcu_bridge PROPERTIES OUTPUT_NAME lnr_mcu)
target_include_directories(loonar_mcu_bridge PUBLIC ${CMAKE_CURRENT_SOURCE_DIR}/../common)

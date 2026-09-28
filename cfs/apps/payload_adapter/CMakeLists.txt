project(LOONAR_PAYLOAD_ADAPTER C)
add_cfe_app(loonar_payload_adapter fsw/src/loonar_payload_adapter_app.c)
set_target_properties(loonar_payload_adapter PROPERTIES OUTPUT_NAME lnr_payload)
target_include_directories(loonar_payload_adapter PUBLIC ${CMAKE_CURRENT_SOURCE_DIR}/../common)

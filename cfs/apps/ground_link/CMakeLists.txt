project(LOONAR_GROUND_LINK C)
add_cfe_app(loonar_ground_link
  fsw/src/loonar_ground_link_app.c
  ${CMAKE_CURRENT_SOURCE_DIR}/../common/loonar_ground_wire.c)
set_target_properties(loonar_ground_link PROPERTIES OUTPUT_NAME lnr_ground)
target_include_directories(loonar_ground_link PUBLIC fsw/inc ${CMAKE_CURRENT_SOURCE_DIR}/../common)

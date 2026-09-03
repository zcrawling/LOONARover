add_library(
  loonar_control_core STATIC
  src/controller_tbd.c
  src/control_core.c
  src/control_rx.c
  src/control_tx.c)
add_dependencies(loonar_control_core loonar_catalog)
target_include_directories(loonar_control_core PUBLIC ${CMAKE_CURRENT_SOURCE_DIR}/include)
target_link_libraries(
  loonar_control_core
  PUBLIC loonar_wire_c loonar_project_options loonar_project_warnings)

if(BUILD_TESTING)
  add_executable(test_control_core tests/test_control_core.c)
  target_link_libraries(test_control_core PRIVATE loonar_control_core m)
  target_include_directories(
    test_control_core
    PRIVATE ${CMAKE_SOURCE_DIR}/platforms/loonar/libs/wire_c/tests)
  add_test(NAME firmware.test_control_core COMMAND test_control_core)

  add_executable(test_control_pipeline tests/test_control_pipeline.c)
  target_link_libraries(test_control_pipeline PRIVATE loonar_control_core m)
  target_include_directories(
    test_control_pipeline
    PRIVATE ${CMAKE_SOURCE_DIR}/platforms/loonar/libs/wire_c/tests)
  add_test(NAME firmware.test_control_pipeline COMMAND test_control_pipeline)

  add_library(loonar_control_freertos_compile OBJECT src/freertos_app.c)
  target_include_directories(
    loonar_control_freertos_compile
    PRIVATE ${CMAKE_CURRENT_SOURCE_DIR}/tests/freertos_mock)
  target_link_libraries(
    loonar_control_freertos_compile
    PRIVATE loonar_control_core loonar_project_options loonar_project_warnings)
endif()

add_library(
  loonar_wire_c STATIC
  src/byte_codec.c
  src/control_messages.c
  src/crc32c.c
  src/packet.c
  src/stream_parser.c)
add_dependencies(loonar_wire_c loonar_catalog)
  target_include_directories(
  loonar_wire_c
  PUBLIC ${CMAKE_CURRENT_SOURCE_DIR}/include
         ${CMAKE_SOURCE_DIR}/platforms/loonar/interfaces/generated/c)
target_link_libraries(loonar_wire_c PUBLIC loonar_project_options loonar_project_warnings)

if(BUILD_TESTING)
  function(loonar_add_wire_test name source)
    add_executable(${name} ${source})
    target_link_libraries(${name} PRIVATE loonar_wire_c)
    target_include_directories(${name} PRIVATE ${CMAKE_CURRENT_SOURCE_DIR}/tests)
    add_test(NAME wire.${name} COMMAND ${name})
  endfunction()

  loonar_add_wire_test(test_byte_codec tests/test_byte_codec.c)
  loonar_add_wire_test(test_control_messages tests/test_control_messages.c)
  loonar_add_wire_test(test_crc32c tests/test_crc32c.c)
  loonar_add_wire_test(test_packet tests/test_packet.c)
  loonar_add_wire_test(test_stream_parser tests/test_stream_parser.c)
  loonar_add_wire_test(test_stream_soak tests/test_stream_soak.c)
endif()

find_package(Python3 REQUIRED COMPONENTS Interpreter)

set(LOONAR_CATALOG_GENERATOR ${CMAKE_SOURCE_DIR}/common/tools/gen_catalog.py)
set(LOONAR_CATALOG_INPUTS
    ${CMAKE_SOURCE_DIR}/common/interfaces/catalog/source_ids.yaml
    ${CMAKE_SOURCE_DIR}/common/interfaces/catalog/reason_codes.yaml
    ${CMAKE_CURRENT_SOURCE_DIR}/catalog/wire_messages.yaml)
set(LOONAR_CATALOG_OUTPUTS
    ${CMAKE_CURRENT_SOURCE_DIR}/generated/c/loonar/interface_ids.h
    ${CMAKE_CURRENT_SOURCE_DIR}/generated/cpp/loonar/interface_ids.hpp
    ${CMAKE_CURRENT_SOURCE_DIR}/generated/interface_catalog.md)

add_custom_command(
  OUTPUT ${LOONAR_CATALOG_OUTPUTS}
  COMMAND ${Python3_EXECUTABLE} ${LOONAR_CATALOG_GENERATOR} --root ${CMAKE_SOURCE_DIR}
  DEPENDS ${LOONAR_CATALOG_GENERATOR} ${LOONAR_CATALOG_INPUTS}
  COMMENT "Generating LOONAR platform interface constants"
  VERBATIM)

add_custom_target(loonar_catalog DEPENDS ${LOONAR_CATALOG_OUTPUTS})

if(BUILD_TESTING)
  add_test(
    NAME contract.loonar_catalog
    COMMAND ${Python3_EXECUTABLE}
            ${CMAKE_SOURCE_DIR}/platforms/loonar/tests/contract/test_catalog.py
            --repo-root ${CMAKE_SOURCE_DIR})
endif()

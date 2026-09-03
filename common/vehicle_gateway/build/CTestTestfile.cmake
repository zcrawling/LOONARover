# CMake generated Testfile for 
# Source directory: /home/sb/LOONAR/common/vehicle_gateway
# Build directory: /home/sb/LOONAR/common/vehicle_gateway/build
# 
# This file includes the relevant testing commands required for 
# testing this directory and lists subdirectories to be tested as well.
add_test([=[gateway.gateway_core]=] "/home/sb/LOONAR/common/vehicle_gateway/build/test_gateway_core")
set_tests_properties([=[gateway.gateway_core]=] PROPERTIES  _BACKTRACE_TRIPLES "/home/sb/LOONAR/common/vehicle_gateway/CMakeLists.txt;27;add_test;/home/sb/LOONAR/common/vehicle_gateway/CMakeLists.txt;0;")
add_test([=[gateway.gateway_protocol]=] "/home/sb/LOONAR/common/vehicle_gateway/build/test_gateway_protocol")
set_tests_properties([=[gateway.gateway_protocol]=] PROPERTIES  _BACKTRACE_TRIPLES "/home/sb/LOONAR/common/vehicle_gateway/CMakeLists.txt;27;add_test;/home/sb/LOONAR/common/vehicle_gateway/CMakeLists.txt;0;")
add_test([=[gateway.gateway_daemon]=] "/home/sb/LOONAR/common/vehicle_gateway/build/test_gateway_daemon" "/home/sb/LOONAR/common/vehicle_gateway/build/vehicle_gatewayd")
set_tests_properties([=[gateway.gateway_daemon]=] PROPERTIES  _BACKTRACE_TRIPLES "/home/sb/LOONAR/common/vehicle_gateway/CMakeLists.txt;31;add_test;/home/sb/LOONAR/common/vehicle_gateway/CMakeLists.txt;0;")

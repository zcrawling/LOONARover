if(CMAKE_SOURCE_DIR STREQUAL CMAKE_CURRENT_SOURCE_DIR)
  cmake_minimum_required(VERSION 3.22)
  project(loonar_video_tools LANGUAGES NONE)
  include(CTest)
endif()

if(BUILD_TESTING)
  add_test(
    NAME video.pipeline
    COMMAND bash ${CMAKE_CURRENT_SOURCE_DIR}/tests/test_video_stream.sh
            ${CMAKE_CURRENT_SOURCE_DIR}/loonar-video-stream)
endif()

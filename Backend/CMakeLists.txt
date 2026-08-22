cmake_minimum_required(VERSION 3.16)
project(AutoReloader LANGUAGES CXX)

set(CMAKE_DISABLE_PRECOMPILE_HEADERS ON)
set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# 强制使用静态运行时库（如果你之前用的是 /MT）
set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded")

add_library(AutoReloader SHARED
  src/dllmain.cpp
)

target_include_directories(AutoReloader PRIVATE
  ${CMAKE_CURRENT_SOURCE_DIR}/YRpp
  ${CMAKE_CURRENT_SOURCE_DIR}/src
)

if(MSVC)
  target_compile_options(AutoReloader PRIVATE
    /std:c++latest
    /permissive-
    $<$<CONFIG:Release>:/O2 /GL>      # 全程序优化
  )
  target_link_options(AutoReloader PRIVATE
    $<$<CONFIG:Release>:/LTCG /INCREMENTAL:NO>
  )
  target_compile_definitions(AutoReloader PRIVATE
    WIN32_LEAN_AND_MEAN
    NOMINMAX
    _WIN32_WINNT=0x0601               # 兼容 Windows 7
  )
endif()

set_target_properties(AutoReloader PROPERTIES
  OUTPUT_NAME "AutoReloader"
  RUNTIME_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/bin"
)

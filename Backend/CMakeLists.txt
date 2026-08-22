cmake_minimum_required(VERSION 3.16)
project(AutoReloader LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# 显式指定使用最新 C++ 标准（覆盖默认）
if(MSVC)
  add_compile_options(/std:c++latest)
endif()

add_library(AutoReloader SHARED
  src/dllmain.cpp
)

target_include_directories(AutoReloader PRIVATE
  ${CMAKE_CURRENT_SOURCE_DIR}/YRpp
  ${CMAKE_CURRENT_SOURCE_DIR}/src
)

if(MSVC)
  target_compile_options(AutoReloader PRIVATE /permissive)
endif()

set_target_properties(AutoReloader PROPERTIES
  OUTPUT_NAME "AutoReloader"
  RUNTIME_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/bin"
)

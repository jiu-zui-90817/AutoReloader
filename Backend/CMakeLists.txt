cmake_minimum_required(VERSION 3.16)
project(AutoReloader LANGUAGES CXX)

# 禁用预编译头（简化构建）
set(CMAKE_DISABLE_PRECOMPILE_HEADERS ON)

# 设置 C++20
set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

add_library(AutoReloader SHARED
  src/dllmain.cpp
)

target_include_directories(AutoReloader PRIVATE
  ${CMAKE_CURRENT_SOURCE_DIR}/YRpp
  ${CMAKE_CURRENT_SOURCE_DIR}/src
)

if(MSVC)
  target_compile_options(AutoReloader PRIVATE
    /std:c++latest          # 强制启用所有最新 C++ 标准
    /permissive-            # 严格符合标准
  )
  target_compile_definitions(AutoReloader PRIVATE
    WIN32_LEAN_AND_MEAN
    NOMINMAX
  )
endif()

set_target_properties(AutoReloader PROPERTIES
  OUTPUT_NAME "AutoReloader"
  RUNTIME_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/bin"
)

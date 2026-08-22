cmake_minimum_required(VERSION 3.16)
project(AutoReloader LANGUAGES CXX)

# 禁用预编译头（避免 pch.cpp 干扰）
set(CMAKE_DISABLE_PRECOMPILE_HEADERS ON)

# 强制 C++20
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
    /std:c++latest          # 保证所有 C++20 特性可用
    /permissive-            # 严格标准符合
  )
  target_compile_definitions(AutoReloader PRIVATE
    WIN32_LEAN_AND_MEAN     # 由 CMake 统一定义，避免源文件重复
    NOMINMAX
  )
endif()

set_target_properties(AutoReloader PROPERTIES
  OUTPUT_NAME "AutoReloader"
  RUNTIME_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/bin"
)

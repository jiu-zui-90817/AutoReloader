cmake_minimum_required(VERSION 3.16)
project(AutoReloader LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# 强制 32 位（在 Windows 上用 Win32 生成器时更自然）
if(MSVC)
endif()

add_library(AutoReloader SHARED
  src/dllmain.cpp
)

target_include_directories(AutoReloader PRIVATE
  ${CMAKE_CURRENT_SOURCE_DIR}/YRpp
  ${CMAKE_CURRENT_SOURCE_DIR}/src
)

# 关闭强制符合模式
if(MSVC)
  target_compile_options(AutoReloader PRIVATE /permissive)
endif()

# 输出名固定
set_target_properties(AutoReloader PROPERTIES
  OUTPUT_NAME "AutoReloader"
  RUNTIME_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/bin"
)

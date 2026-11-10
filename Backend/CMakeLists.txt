cmake_minimum_required(VERSION 3.16)
project(AutoReloader LANGUAGES C CXX)

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

# Experimental hook DLL: injected into MentalOmegaClient.exe to rewrite the
# Syringe command line. Built from vendored MinHook (MIT).
set(MINHOOK_DIR "${CMAKE_CURRENT_SOURCE_DIR}/tools/SyringeHook/minhook")
add_library(minhook STATIC
  ${MINHOOK_DIR}/src/hook.c
  ${MINHOOK_DIR}/src/trampoline.c
  ${MINHOOK_DIR}/src/buffer.c
  ${MINHOOK_DIR}/src/hde/hde32.c
  ${MINHOOK_DIR}/src/hde/hde64.c
)
target_include_directories(minhook PUBLIC
  ${MINHOOK_DIR}/include
  ${MINHOOK_DIR}/src
)
if(MSVC)
  target_compile_options(minhook PRIVATE /O2)
  target_compile_definitions(minhook PRIVATE WIN32_LEAN_AND_MEAN NOMINMAX)
endif()

add_library(SyringeHook SHARED
  tools/SyringeHook/SyringeHook.cpp
)
target_include_directories(SyringeHook PRIVATE
  ${MINHOOK_DIR}/include
  ${CMAKE_CURRENT_SOURCE_DIR}/../Launcher
)
target_link_libraries(SyringeHook PRIVATE minhook shell32 user32 version.lib)
if(MSVC)
  target_compile_options(SyringeHook PRIVATE
    /std:c++latest
    /permissive-
    /utf-8
    $<$<CONFIG:Release>:/O2 /GL>
  )
  target_link_options(SyringeHook PRIVATE
    $<$<CONFIG:Release>:/LTCG /INCREMENTAL:NO>
  )
  target_compile_definitions(SyringeHook PRIVATE
    WIN32_LEAN_AND_MEAN
    NOMINMAX
    _WIN32_WINNT=0x0601
  )
endif()
set_target_properties(SyringeHook PROPERTIES
  OUTPUT_NAME "AutoReloader.SyringeHook"
  RUNTIME_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/bin"
)


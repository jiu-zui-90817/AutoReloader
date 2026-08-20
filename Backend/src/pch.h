/**
 * 最小预编译头 — 若 VS 工程启用「预编译头」则使用本文件。
 * 也可在 dllmain.cpp 中删除 #include "pch.h" 并直接包含下方头。
 */
#pragma once

#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif

#include <windows.h>
#include <string>
#include <iostream>
#include <vector>
#include <sstream>
#include <map>
#include <fstream>

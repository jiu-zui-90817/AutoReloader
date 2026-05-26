/**
 * =========================================================================================
 * Project Name: YR/MO Hot Reloader (独立热重载组件)
 * Description:  A standalone dynamic reloader for C&C Red Alert 2: Yuri's Revenge.
 * =========================================================================================
 */

#include "pch.h"                  
#define WIN32_LEAN_AND_MEAN       

#include <windows.h>
#include <string>
#include <iostream>
#include <vector>
#include <sstream>
#include <map>

 // YRpp Headers
#include <YRpp.h>
#include <CCINIClass.h>
#include <CCFileClass.h>
#include <WeaponTypeClass.h>
#include <WarheadTypeClass.h>
#include <BulletTypeClass.h>
#include <InfantryTypeClass.h>
#include <UnitTypeClass.h>
#include <AircraftTypeClass.h>
#include <BuildingTypeClass.h>
#include <SuperWeaponTypeClass.h>
#include <AnimTypeClass.h>
#include <ParticleTypeClass.h>
#include <ParticleSystemTypeClass.h>
#include <VoxelAnimTypeClass.h>

// ========================================================
// Global Configuration Variables
// ========================================================
int g_HotKey = VK_F5;
bool g_AutoMonitor = true;
bool g_ShowConsole = true;
bool g_ConsoleAllocated = false;
std::vector<std::string> g_TargetINIs;

// ========================================================
// Module 1: Console Management
// ========================================================
void ToggleConsole(bool show)
{
    if (show && !g_ConsoleAllocated) {
        AllocConsole();
        FILE* fDummy;
        freopen_s(&fDummy, "CONOUT$", "w", stdout);
        freopen_s(&fDummy, "CONIN$", "r", stdin);

        SetConsoleTitleA("YR/MO Hot Reloader - Debug Console");
        SetConsoleOutputCP(936);

        std::cout << "========================================================" << std::endl;
        std::cout << " [INFO] Hot Reloader Thread Injected Successfully!" << std::endl;
        std::cout << "========================================================\n" << std::endl;

        g_ConsoleAllocated = true;
    }
    else if (!show && g_ConsoleAllocated) {
        FreeConsole();
        g_ConsoleAllocated = false;
    }
}

// ========================================================
// Module 2: Configuration Loader
// ========================================================
void LoadReloaderConfig(const std::string& gameDir)
{
    std::string configPath = gameDir + "\\ReloaderConfig.ini";

    g_HotKey = GetPrivateProfileIntA("Settings", "HotKey", VK_F5, configPath.c_str());

    char autoMonStr[16] = { 0 };
    GetPrivateProfileStringA("Settings", "AutoMonitor", "true", autoMonStr, sizeof(autoMonStr), configPath.c_str());
    g_AutoMonitor = (_stricmp(autoMonStr, "true") == 0 || _stricmp(autoMonStr, "1") == 0);

    char consoleStr[16] = { 0 };
    GetPrivateProfileStringA("Settings", "ShowConsole", "true", consoleStr, sizeof(consoleStr), configPath.c_str());
    g_ShowConsole = (_stricmp(consoleStr, "true") == 0 || _stricmp(consoleStr, "1") == 0);

    char targetIniStr[1024] = { 0 };
    GetPrivateProfileStringA("Settings", "TargetINI", "hotfix.ini", targetIniStr, sizeof(targetIniStr), configPath.c_str());

    g_TargetINIs.clear();
    std::stringstream ss(targetIniStr);
    std::string item;
    while (std::getline(ss, item, ',')) {
        item.erase(0, item.find_first_not_of(" \t"));
        item.erase(item.find_last_not_of(" \t") + 1);
        if (!item.empty()) {
            g_TargetINIs.push_back(item);
        }
    }

    if (g_TargetINIs.empty()) {
        g_TargetINIs.push_back("hotfix.ini");
    }
}

// ========================================================
// Module 3: File Utilities
// ========================================================
FILETIME GetFileLastWriteTime(const std::string& path)
{
    WIN32_FILE_ATTRIBUTE_DATA fileInfo;
    if (GetFileAttributesExA(path.c_str(), GetFileExInfoStandard, &fileInfo)) {
        return fileInfo.ftLastWriteTime;
    }
    FILETIME emptyTime = { 0 };
    return emptyTime;
}

// ========================================================
// Module 4: Core Injection Engine
// ========================================================
template <typename T>
bool TryReloadType(const std::string& targetID, CCINIClass* pINI, const char* typeName) {
    for (int i = 0; i < T::Array.Count; ++i) {
        auto pItem = T::Array.Items[i];
        if (pItem && _stricmp(pItem->ID, targetID.c_str()) == 0) {
            pItem->LoadFromINI(pINI);
            if (g_ConsoleAllocated) {
                std::cout << "  -> Reloaded [" << typeName << "]: " << targetID << std::endl;
            }
            return true;
        }
    }
    return false;
}

void ExecuteUniversalHotReload(const std::string& iniPath, const std::string& fileName)
{
    char sectionBuffer[4096] = { 0 };
    if (GetPrivateProfileSectionNamesA(sectionBuffer, sizeof(sectionBuffer), iniPath.c_str()) == 0) return;

    CCFileClass file(iniPath.c_str());
    CCINIClass ini;

    if (ini.ReadCCFile(&file))
    {
        if (g_ConsoleAllocated) {
            std::cout << "[PARSE] Capturing data stream from: " << fileName << std::endl;
        }

        char* currentSection = sectionBuffer;

        while (*currentSection != '\0')
        {
            std::string targetID = currentSection;

            bool matched =
                TryReloadType<UnitTypeClass>(targetID, &ini, "Vehicle") ||
                TryReloadType<InfantryTypeClass>(targetID, &ini, "Infantry") ||
                TryReloadType<BuildingTypeClass>(targetID, &ini, "Building") ||
                TryReloadType<AircraftTypeClass>(targetID, &ini, "Aircraft") ||
                TryReloadType<WeaponTypeClass>(targetID, &ini, "Weapon") ||
                TryReloadType<WarheadTypeClass>(targetID, &ini, "Warhead") ||
                TryReloadType<BulletTypeClass>(targetID, &ini, "Projectile") ||
                TryReloadType<SuperWeaponTypeClass>(targetID, &ini, "SuperWeapon") ||
                TryReloadType<AnimTypeClass>(targetID, &ini, "Animation") ||
                TryReloadType<ParticleTypeClass>(targetID, &ini, "Particle") ||
                TryReloadType<ParticleSystemTypeClass>(targetID, &ini, "ParticleSys") ||
                TryReloadType<VoxelAnimTypeClass>(targetID, &ini, "VoxelAnim");

            if (!matched && g_ConsoleAllocated) {
                std::cout << "  [WARN] Entity ID not found in memory: " << targetID << std::endl;
            }

            currentSection += targetID.length() + 1;
        }

        if (g_ConsoleAllocated) {
            std::cout << "[OK] " << fileName << " injection completed.\n" << std::endl;
        }
    }
}

// ========================================================
// Module 5: Thread Monitor (Logic Fixed!)
// ========================================================
DWORD WINAPI HotReloadMonitorThread(LPVOID lpParam)
{
    char exePath[MAX_PATH];
    GetModuleFileNameA(NULL, exePath, MAX_PATH);
    std::string pathStr = exePath;
    std::string gameDir = pathStr.substr(0, pathStr.find_last_of("\\/"));

    // 🚨 修复点：立刻读取配置并拉起控制台，绝对不等待引擎加载！
    LoadReloaderConfig(gameDir);
    ToggleConsole(g_ShowConsole);

    if (g_ConsoleAllocated) {
        std::cout << "[SYSTEM] Waiting for Yuri's Revenge Engine to initialize..." << std::endl;
    }

    bool engineReady = false;
    bool lastMonitorState = g_AutoMonitor;
    std::map<std::string, FILETIME> fileTimes;

    while (true)
    {
        // 阶段 1：死磕引擎是否就绪
        if (!engineReady) {
            if (UnitTypeClass::Array.Count > 0) {
                engineReady = true;
                if (g_ConsoleAllocated) {
                    std::cout << "[SYSTEM] Engine Ready! Loaded Entities: " << UnitTypeClass::Array.Count << std::endl;
                    std::cout << "[SYSTEM] Protocol Mode: " << (g_AutoMonitor ? "Auto-Monitor" : "Manual Hotkey") << std::endl;
                }
                // 引擎就绪后，初始化文件时间戳基准线
                if (g_AutoMonitor) {
                    for (const auto& fileName : g_TargetINIs) {
                        fileTimes[fileName] = GetFileLastWriteTime(gameDir + "\\" + fileName);
                    }
                }
            }
            else {
                Sleep(500); // 引擎还没好，继续等
                continue;
            }
        }

        // 阶段 2：引擎就绪后的热重载轮询
        LoadReloaderConfig(gameDir); // 支持运行时动态改配置文件

        if (lastMonitorState != g_AutoMonitor) {
            lastMonitorState = g_AutoMonitor;
            if (g_ConsoleAllocated) {
                std::cout << "[SYSTEM] Protocol Mode Switched -> "
                    << (g_AutoMonitor ? "Auto-Monitor" : "Manual Hotkey") << std::endl;
            }
            if (g_AutoMonitor) {
                for (const auto& fileName : g_TargetINIs) {
                    fileTimes[fileName] = GetFileLastWriteTime(gameDir + "\\" + fileName);
                }
            }
        }

        if (g_AutoMonitor)
        {
            bool anyFileReloaded = false;
            for (const auto& fileName : g_TargetINIs)
            {
                std::string fullPath = gameDir + "\\" + fileName;
                FILETIME currentWriteTime = GetFileLastWriteTime(fullPath);

                if (fileTimes[fileName].dwLowDateTime == 0 && fileTimes[fileName].dwHighDateTime == 0) {
                    fileTimes[fileName] = currentWriteTime;
                }
                else if (CompareFileTime(&fileTimes[fileName], &currentWriteTime) != 0) {
                    fileTimes[fileName] = currentWriteTime;
                    Sleep(100);
                    ExecuteUniversalHotReload(fullPath, fileName);
                    anyFileReloaded = true;
                }
            }
            if (anyFileReloaded) MessageBeep(MB_ICONINFORMATION);
            Sleep(500);
        }
        else
        {
            if (GetAsyncKeyState(g_HotKey) & 0x8000)
            {
                if (g_ConsoleAllocated) std::cout << "\n[>>>] Manual reload triggered via Hotkey!" << std::endl;
                for (const auto& fileName : g_TargetINIs) {
                    std::string fullPath = gameDir + "\\" + fileName;
                    ExecuteUniversalHotReload(fullPath, fileName);
                }
                MessageBeep(MB_ICONWARNING);
                Sleep(500);
            }
            Sleep(50);
        }
    }
    return 0;
}

// ========================================================
// Standard Entry Point
// ========================================================
BOOL APIENTRY DllMain(HMODULE hModule, DWORD ul_reason_for_call, LPVOID lpReserved)
{
    if (ul_reason_for_call == DLL_PROCESS_ATTACH)
    {
        DisableThreadLibraryCalls(hModule);
        CreateThread(NULL, 0, HotReloadMonitorThread, NULL, 0, NULL);
    }
    return TRUE;
}

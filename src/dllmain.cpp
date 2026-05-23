/**
 * =========================================================================================
 * 项目名称: YR/MO Ultimate Auto-Reloader (热重载系统)
 * 核心机制: 利用内存 Hook 多米诺效应，纯 YRpp 即可触发 Ares/Phobos 的全属性解析。
 * 支持对象: 八大核心图纸 (包含超级武器、弹头、弹道等)，支持多文件阵列与 CMD 监控。
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

 // ⚡ 只需纯正的 YRpp 库，决不引入任何繁杂的第三方库！
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
#include <SuperWeaponTypeClass.h> // 新增：超级武器支持！

// ========================================================
// 全局控制变量
// ========================================================
int g_HotKey = VK_F5;
bool g_AutoMonitor = true;
std::vector<std::string> g_TargetINIs;

// ========================================================
// 模块 1：CMD 终端
// ========================================================
void InitDebugConsole()
{
    AllocConsole();
    FILE* fDummy;
    freopen_s(&fDummy, "CONOUT$", "w", stdout);
    freopen_s(&fDummy, "CONIN$", "r", stdin);

    SetConsoleTitleA("Mental Omega 热重载终端");
    SetConsoleOutputCP(936);

    std::cout << "========================================================" << std::endl;
    std::cout << " [系统] DLL 加载成功！终端已激活。" << std::endl;
    std::cout << " [火力] 已覆盖: 载具/步兵/建筑/战机/武器/弹头/弹道/超武" << std::endl;
    std::cout << "========================================================\n" << std::endl;
}

// ========================================================
// 模块 2：动态列阵配置读取
// ========================================================
void LoadReloaderConfig(const std::string& gameDir)
{
    std::string configPath = gameDir + "\\ReloaderConfig.ini";

    g_HotKey = GetPrivateProfileIntA("Settings", "HotKey", VK_F5, configPath.c_str());

    char autoMonStr[16] = { 0 };
    GetPrivateProfileStringA("Settings", "AutoMonitor", "true", autoMonStr, sizeof(autoMonStr), configPath.c_str());
    g_AutoMonitor = (_stricmp(autoMonStr, "true") == 0 || _stricmp(autoMonStr, "1") == 0);

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
// 模块 3：获取文件时间戳
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
// 模块 4：终极八核解析引擎！
// ========================================================
void ExecuteUniversalHotReload(const std::string& iniPath, const std::string& fileName)
{
    char sectionBuffer[4096] = { 0 };
    if (GetPrivateProfileSectionNamesA(sectionBuffer, sizeof(sectionBuffer), iniPath.c_str()) == 0) return;

    CCFileClass file(iniPath.c_str());
    CCINIClass ini;

    if (ini.ReadCCFile(&file))
    {
        std::cout << "[解析] 捕获数据流 -> [" << fileName << "]" << std::endl;
        char* currentSection = sectionBuffer;

        while (*currentSection != '\0')
        {
            std::string targetID = currentSection;
            bool matched = false;

            // 1. 武器大池
            for (int i = 0; i < WeaponTypeClass::Array.Count; ++i) {
                if (WeaponTypeClass::Array.Items[i] && _stricmp(WeaponTypeClass::Array.Items[i]->ID, targetID.c_str()) == 0) {
                    WeaponTypeClass::Array.Items[i]->LoadFromINI(&ini);
                    std::cout << "  -> 覆写 [武器]: " << targetID << std::endl;
                    matched = true; break;
                }
            }
            // 2. 弹头大池
            if (!matched) {
                for (int i = 0; i < WarheadTypeClass::Array.Count; ++i) {
                    if (WarheadTypeClass::Array.Items[i] && _stricmp(WarheadTypeClass::Array.Items[i]->ID, targetID.c_str()) == 0) {
                        WarheadTypeClass::Array.Items[i]->LoadFromINI(&ini);
                        std::cout << "  -> 覆写 [弹头]: " << targetID << std::endl;
                        matched = true; break;
                    }
                }
            }
            // 3. 抛射体大池
            if (!matched) {
                for (int i = 0; i < BulletTypeClass::Array.Count; ++i) {
                    if (BulletTypeClass::Array.Items[i] && _stricmp(BulletTypeClass::Array.Items[i]->ID, targetID.c_str()) == 0) {
                        BulletTypeClass::Array.Items[i]->LoadFromINI(&ini);
                        std::cout << "  -> 覆写 [抛射体]: " << targetID << std::endl;
                        matched = true; break;
                    }
                }
            }
            // 4. 载具大池
            if (!matched) {
                for (int i = 0; i < UnitTypeClass::Array.Count; ++i) {
                    if (UnitTypeClass::Array.Items[i] && _stricmp(UnitTypeClass::Array.Items[i]->ID, targetID.c_str()) == 0) {
                        UnitTypeClass::Array.Items[i]->LoadFromINI(&ini);
                        std::cout << "  -> 覆写 [载具]: " << targetID << std::endl;
                        matched = true; break;
                    }
                }
            }
            // 5. 步兵大池
            if (!matched) {
                for (int i = 0; i < InfantryTypeClass::Array.Count; ++i) {
                    if (InfantryTypeClass::Array.Items[i] && _stricmp(InfantryTypeClass::Array.Items[i]->ID, targetID.c_str()) == 0) {
                        InfantryTypeClass::Array.Items[i]->LoadFromINI(&ini);
                        std::cout << "  -> 覆写 [步兵]: " << targetID << std::endl;
                        matched = true; break;
                    }
                }
            }
            // 6. 建筑大池
            if (!matched) {
                for (int i = 0; i < BuildingTypeClass::Array.Count; ++i) {
                    if (BuildingTypeClass::Array.Items[i] && _stricmp(BuildingTypeClass::Array.Items[i]->ID, targetID.c_str()) == 0) {
                        BuildingTypeClass::Array.Items[i]->LoadFromINI(&ini);
                        std::cout << "  -> 覆写 [建筑]: " << targetID << std::endl;
                        matched = true; break;
                    }
                }
            }
            // 7. 战机大池
            if (!matched) {
                for (int i = 0; i < AircraftTypeClass::Array.Count; ++i) {
                    if (AircraftTypeClass::Array.Items[i] && _stricmp(AircraftTypeClass::Array.Items[i]->ID, targetID.c_str()) == 0) {
                        AircraftTypeClass::Array.Items[i]->LoadFromINI(&ini);
                        std::cout << "  -> 覆写 [战机]: " << targetID << std::endl;
                        matched = true; break;
                    }
                }
            }
            // 8. 超级武器大池 (SuperWeapon)
            if (!matched) {
                for (int i = 0; i < SuperWeaponTypeClass::Array.Count; ++i) {
                    if (SuperWeaponTypeClass::Array.Items[i] && _stricmp(SuperWeaponTypeClass::Array.Items[i]->ID, targetID.c_str()) == 0) {
                        SuperWeaponTypeClass::Array.Items[i]->LoadFromINI(&ini);
                        std::cout << "  -> 覆写 [超级武器]: " << targetID << std::endl;
                        matched = true; break;
                    }
                }
            }

            if (!matched) {
                std::cout << "  [警告] 内存中未找到实体图纸: " << targetID << std::endl;
            }

            currentSection += targetID.length() + 1;
        }
        std::cout << "[OK] " << fileName << " 注入完毕，规则已改写！\n" << std::endl;
    }
}

// ========================================================
// 模块 5：多维监控线程
// ========================================================
DWORD WINAPI HotReloadMonitorThread(LPVOID lpParam)
{
    InitDebugConsole();

    char exePath[MAX_PATH];
    GetModuleFileNameA(NULL, exePath, MAX_PATH);
    std::string pathStr = exePath;
    std::string gameDir = pathStr.substr(0, pathStr.find_last_of("\\/"));

    bool lastMonitorState = true;
    std::map<std::string, FILETIME> fileTimes;

    while (true)
    {
        if (UnitTypeClass::Array.Count > 0)
        {
            LoadReloaderConfig(gameDir);

            if (lastMonitorState != g_AutoMonitor) {
                lastMonitorState = g_AutoMonitor;
                std::cout << "[系统] 切换协议 -> " << (g_AutoMonitor ? "监控 (保存即刻生效)" : "手动控制 (F5热键打击)") << std::endl;

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
                    std::cout << "\n[>>>] 执行全阵列饱和式重载..." << std::endl;
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
        else {
            Sleep(500);
        }
    }
    return 0;
}

// ========================================================
// 标准入口
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
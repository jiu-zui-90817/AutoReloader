/**
 * =========================================================================================
 * AutoReloader.dll — YR / MO 热重载引擎
 *
 * 设计要点：
 *  - 配置缓存：只在 ReloaderConfig.ini 变化时重读
 *  - 节头解析：兼容 BOM / 行尾注释 / 节名内外空格
 *  - 类型索引：引擎就绪后建立 ID -> 类型 的哈希索引，避免每次全表扫描
 *  - 稳定读取：mtime + size 双采样，读失败重试
 *  - 文件日志：Reloader_Log.txt（带轮转），不再依赖控制台
 *  - 热键：边沿触发；AutoMonitor 下也可强制重载；可限制仅游戏前台
 *  - 扩展集成：
 *      Ares   —— 无导出 API；基础类型的 LoadFromINI hook 会自动读取 Ares 扩展字段
 *      Phobos —— 通过其 Interop 导出调用 GetInteropAPIVersion / ConvertToType_Phobos
 *  - [AutoReloader] 节：在 hotfix 中声明实时类型转换
 *      [AutoReloader]
 *      Convert=M60>MTNK
 *    转换使用 Phobos 接口；若装有 Ares 3.0，Phobos 会转调 Ares 的转换实现。
 * =========================================================================================
 */

// ---------- 务必放在所有包含之前 ----------
#ifdef byte
#undef byte
#endif

#include <cstddef>
#include <cstdint>
#include <cstdarg>
#include <concepts>
#include <type_traits>
#include <bit>
#include <utility>

using byte = unsigned char;

#include <windows.h>
#include <string>
#include <vector>
#include <map>
#include <unordered_map>
#include <unordered_set>
#include <set>
#include <fstream>
#include <sstream>
#include <iostream>
#include <mutex>
#include <atomic>
#include <chrono>
#include <algorithm>
#include <filesystem>
#include <iterator>
#include <cstring>
#include <cstdio>
#include <cstdlib>
#include <ctime>
#include <cwctype>
#include <cwchar>
#include <objidl.h>

#include "YRPPCore.h"
#include "Unsorted.h"
#include "CCINIClass.h"
#include "CCFileClass.h"
#include "WeaponTypeClass.h"
#include "WarheadTypeClass.h"
#include "BulletTypeClass.h"
#include "InfantryTypeClass.h"
#include "UnitTypeClass.h"
#include "AircraftTypeClass.h"
#include "BuildingTypeClass.h"
#include "SuperWeaponTypeClass.h"
#include "AnimTypeClass.h"
#include "ParticleTypeClass.h"
#include "ParticleSystemTypeClass.h"
#include "VoxelAnimTypeClass.h"
#include "TechnoClass.h"
#include "FootClass.h"
#include "UnitClass.h"
#include "InfantryClass.h"
#include "AircraftClass.h"
#include "BuildingClass.h"
#include "LocomotionClass.h"
#include "MapClass.h"

namespace fs = std::filesystem;

#define AUTORELOADER_VERSION "2.1.5"
#define AR_LOG_NAME L"Reloader_Log.txt"

// ========================================================
// Globals
// ========================================================
bool g_ConsoleAllocated = false;
std::atomic<bool> g_Stop{ false };
std::atomic<bool> g_ForceReload{ false };

namespace {

// ========================================================
// Small helpers
// ========================================================
std::string TrimA(const std::string& s)
{
    size_t a = s.find_first_not_of(" \t\r\n");
    if (a == std::string::npos) return {};
    size_t b = s.find_last_not_of(" \t\r\n");
    return s.substr(a, b - a + 1);
}

std::wstring TrimW(const std::wstring& s)
{
    size_t a = s.find_first_not_of(L" \t\r\n");
    if (a == std::wstring::npos) return {};
    size_t b = s.find_last_not_of(L" \t\r\n");
    return s.substr(a, b - a + 1);
}

std::string LowerAscii(const std::string& s)
{
    std::string out = s;
    for (char& c : out) c = static_cast<char>(tolower(static_cast<unsigned char>(c)));
    return out;
}

std::string WideToUtf8(const std::wstring& w)
{
    if (w.empty()) return {};
    int need = WideCharToMultiByte(CP_UTF8, 0, w.c_str(), static_cast<int>(w.size()), nullptr, 0, nullptr, nullptr);
    if (need <= 0) return {};
    std::string out(static_cast<size_t>(need), '\0');
    WideCharToMultiByte(CP_UTF8, 0, w.c_str(), static_cast<int>(w.size()), out.data(), need, nullptr, nullptr);
    return out;
}

std::string WideToAnsi(const std::wstring& w)
{
    if (w.empty()) return {};
    int need = WideCharToMultiByte(CP_ACP, 0, w.c_str(), static_cast<int>(w.size()), nullptr, 0, nullptr, nullptr);
    if (need <= 0) return {};
    std::string out(static_cast<size_t>(need), '\0');
    WideCharToMultiByte(CP_ACP, 0, w.c_str(), static_cast<int>(w.size()), out.data(), need, nullptr, nullptr);
    return out;
}

bool FileExistsW(const fs::path& p)
{
    DWORD attr = GetFileAttributesW(p.c_str());
    return attr != INVALID_FILE_ATTRIBUTES && !(attr & FILE_ATTRIBUTE_DIRECTORY);
}

struct FileMeta
{
    bool exists = false;
    FILETIME mtime{};
    ULONGLONG size = 0;
};

bool GetFileMetaW(const fs::path& p, FileMeta& out)
{
    WIN32_FILE_ATTRIBUTE_DATA data{};
    if (!GetFileAttributesExW(p.c_str(), GetFileExInfoStandard, &data)) {
        out = FileMeta{};
        return false;
    }
    out.exists = true;
    out.mtime = data.ftLastWriteTime;
    out.size = (static_cast<ULONGLONG>(data.nFileSizeHigh) << 32) | data.nFileSizeLow;
    return true;
}

bool SameMeta(const FileMeta& a, const FileMeta& b)
{
    return a.exists && b.exists
        && CompareFileTime(&a.mtime, &b.mtime) == 0
        && a.size == b.size;
}

FILETIME GetWriteTimeW(const fs::path& p)
{
    FileMeta m;
    if (!GetFileMetaW(p, m)) {
        FILETIME zero{};
        return zero;
    }
    return m.mtime;
}

bool ReadAllBytesW(const fs::path& p, std::string& out)
{
    HANDLE h = CreateFileW(
        p.c_str(), GENERIC_READ,
        FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE,
        nullptr, OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, nullptr);
    if (h == INVALID_HANDLE_VALUE) return false;

    LARGE_INTEGER size{};
    if (!GetFileSizeEx(h, &size) || size.QuadPart < 0 || size.QuadPart > 64LL * 1024 * 1024) {
        CloseHandle(h);
        return false;
    }

    out.clear();
    out.resize(static_cast<size_t>(size.QuadPart));
    size_t total = 0;
    while (total < out.size()) {
        DWORD chunk = static_cast<DWORD>(std::min<size_t>(out.size() - total, 1u << 20));
        DWORD read = 0;
        if (!ReadFile(h, out.data() + total, chunk, &read, nullptr) || read == 0) break;
        total += read;
    }
    CloseHandle(h);
    out.resize(total);
    return total == static_cast<size_t>(size.QuadPart);
}

bool WriteAllBytesW(const fs::path& p, const std::string& data)
{
    HANDLE h = CreateFileW(
        p.c_str(), GENERIC_WRITE, FILE_SHARE_READ,
        nullptr, CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, nullptr);
    if (h == INVALID_HANDLE_VALUE) return false;

    size_t total = 0;
    bool ok = true;
    while (total < data.size()) {
        DWORD chunk = static_cast<DWORD>(std::min<size_t>(data.size() - total, 1u << 20));
        DWORD written = 0;
        if (!WriteFile(h, data.data() + total, chunk, &written, nullptr) || written == 0) {
            ok = false;
            break;
        }
        total += written;
    }
    FlushFileBuffers(h);
    CloseHandle(h);
    return ok && total == data.size();
}

bool AppendNewlineW(const fs::path& p)
{
    HANDLE h = CreateFileW(
        p.c_str(), FILE_APPEND_DATA, FILE_SHARE_READ | FILE_SHARE_WRITE,
        nullptr, OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, nullptr);
    if (h == INVALID_HANDLE_VALUE) return false;
    DWORD written = 0;
    const char crlf[2] = { '\r', '\n' };
    bool ok = WriteFile(h, crlf, 2, &written, nullptr) != FALSE && written == 2;
    CloseHandle(h);
    return ok;
}

bool ReadAllBytesRetry(const fs::path& p, std::string& out, int attempts)
{
    for (int i = 0; i < attempts; ++i) {
        if (ReadAllBytesW(p, out)) return true;
        Sleep(60);
    }
    return false;
}

// ========================================================
// Logger
// ========================================================
std::mutex g_LogMutex;
std::ofstream g_LogFile;
fs::path g_LogPath;
bool g_LogEnabled = false;
size_t g_LogMaxBytes = 1024 * 1024;

std::string Timestamp()
{
    auto now = std::chrono::system_clock::now();
    auto tt = std::chrono::system_clock::to_time_t(now);
    tm local{};
    localtime_s(&local, &tt);
    auto ms = std::chrono::duration_cast<std::chrono::milliseconds>(
        now.time_since_epoch()).count() % 1000;
    char buf[32];
    strftime(buf, sizeof(buf), "%H:%M:%S", &local);
    char full[48];
    sprintf_s(full, sizeof(full), "[%s.%03d] ", buf, static_cast<int>(ms));
    return full;
}

void LoggerInit(const fs::path& gameDir, bool enabled, int maxKB)
{
    std::lock_guard<std::mutex> lock(g_LogMutex);
    if (g_LogFile.is_open()) g_LogFile.close();
    g_LogEnabled = false;
    g_LogPath = gameDir / AR_LOG_NAME;
    g_LogMaxBytes = static_cast<size_t>(std::max(64, maxKB)) * 1024;
    if (!enabled) return;

    std::error_code ec;
    auto size = fs::file_size(g_LogPath, ec);
    if (!ec && size > g_LogMaxBytes) {
        fs::path backup = g_LogPath;
        backup += L".1";
        fs::remove(backup, ec);
        fs::rename(g_LogPath, backup, ec);
    }
    g_LogFile.open(g_LogPath, std::ios::out | std::ios::app | std::ios::binary);
    g_LogEnabled = g_LogFile.is_open();
}

void WriteLog(const std::string& msg)
{
    std::lock_guard<std::mutex> lock(g_LogMutex);
    std::string line = Timestamp() + msg + "\n";
    if (g_LogEnabled && g_LogFile.is_open()) {
        g_LogFile << line;
        g_LogFile.flush();
    }
    if (g_ConsoleAllocated) {
        std::cout << line;
        std::cout.flush();
    }
}

void LogF(const char* fmt, ...)
{
    char buf[2048];
    va_list args;
    va_start(args, fmt);
    vsnprintf_s(buf, sizeof(buf), _TRUNCATE, fmt, args);
    va_end(args);
    WriteLog(buf);
}

// ========================================================
// Console
// ========================================================
void ToggleConsole(bool show)
{
    if (show && !g_ConsoleAllocated) {
        AllocConsole();
        FILE* dummy = nullptr;
        freopen_s(&dummy, "CONOUT$", "w", stdout);
        freopen_s(&dummy, "CONIN$", "r", stdin);
        SetConsoleTitleA("AutoReloader - Debug Console");
        SetConsoleOutputCP(CP_UTF8);
        g_ConsoleAllocated = true;
        LogF("[console] allocated");
    }
    else if (!show && g_ConsoleAllocated) {
        LogF("[console] released");
        FreeConsole();
        g_ConsoleAllocated = false;
    }
}

// ========================================================
// Configuration
// ========================================================
struct Config
{
    int hotKey = VK_F5;
    bool autoMonitor = true;
    bool showConsole = false;
    bool beep = true;
    bool hotkeyOnlyInGame = true;
    bool liveConvert = true;
    bool autoSyncAE = true;
    bool refreshExisting = false;
    bool logFile = true;
    int logMaxKB = 1024;
    int pollMs = 500;
    std::vector<fs::path> targets;
};

std::wstring IniStringW(const fs::path& path, const wchar_t* section, const wchar_t* key, const wchar_t* def, DWORD cap = 4096)
{
    std::vector<wchar_t> buf(static_cast<size_t>(cap), L'\0');
    GetPrivateProfileStringW(section, key, def, buf.data(), cap, path.c_str());
    return std::wstring(buf.data());
}

int IniIntW(const fs::path& path, const wchar_t* section, const wchar_t* key, int def)
{
    return static_cast<int>(GetPrivateProfileIntW(section, key, def, path.c_str()));
}

bool ParseBoolW(const std::wstring& value, bool def)
{
    std::wstring v = TrimW(value);
    if (v.empty()) return def;
    return _wcsicmp(v.c_str(), L"true") == 0
        || _wcsicmp(v.c_str(), L"yes") == 0
        || v == L"1";
}

Config LoadConfig(const fs::path& configPath, std::wstring& error)
{
    Config cfg;
    error.clear();
    if (!FileExistsW(configPath)) {
        error = L"ReloaderConfig.ini not found, using defaults";
    }

    cfg.hotKey = IniIntW(configPath, L"Settings", L"HotKey", VK_F5);
    if (cfg.hotKey <= 0 || cfg.hotKey > 255) cfg.hotKey = VK_F5;

    cfg.autoMonitor = ParseBoolW(IniStringW(configPath, L"Settings", L"AutoMonitor", L"true"), true);
    cfg.showConsole = ParseBoolW(IniStringW(configPath, L"Settings", L"ShowConsole", L"false"), false);
    cfg.beep = ParseBoolW(IniStringW(configPath, L"Settings", L"Beep", L"true"), true);
    cfg.hotkeyOnlyInGame = ParseBoolW(IniStringW(configPath, L"Settings", L"HotkeyOnlyInGame", L"true"), true);
    cfg.pollMs = IniIntW(configPath, L"Settings", L"PollIntervalMs", 500);
    if (cfg.pollMs < 100) cfg.pollMs = 100;
    if (cfg.pollMs > 5000) cfg.pollMs = 5000;

    cfg.logFile = ParseBoolW(IniStringW(configPath, L"Logging", L"LogFile", L"true"), true);
    cfg.logMaxKB = IniIntW(configPath, L"Logging", L"LogMaxKB", 1024);
    if (cfg.logMaxKB < 64) cfg.logMaxKB = 64;
    if (cfg.logMaxKB > 10240) cfg.logMaxKB = 10240;

    cfg.liveConvert = ParseBoolW(IniStringW(configPath, L"Extensions", L"LiveConvert", L"true"), true);
    cfg.autoSyncAE = ParseBoolW(IniStringW(configPath, L"Extensions", L"AutoSyncAttachEffects", L"true"), true);
    cfg.refreshExisting = ParseBoolW(IniStringW(configPath, L"Experimental", L"RefreshExistingUnits", L"false"), false);

    std::wstring list = IniStringW(configPath, L"Settings", L"TargetINI", L"hotfix.ini", 8192);
    std::wstringstream ss(list);
    std::wstring item;
    while (std::getline(ss, item, L',')) {
        std::wstring name = TrimW(item);
        if (!name.empty()) cfg.targets.emplace_back(name);
    }
    if (cfg.targets.empty()) cfg.targets.emplace_back(L"hotfix.ini");
    return cfg;
}

fs::path ResolveTarget(const fs::path& gameDir, const fs::path& target)
{
    if (target.is_absolute()) return target;
    return gameDir / target;
}

// ========================================================
// INI section scanner
// ========================================================
struct ScanResult
{
    std::vector<std::string> sections;
    std::vector<std::pair<std::string, std::string>> commands;
};

void NormalizeTextEncoding(std::string& data)
{
    if (data.size() >= 2
        && static_cast<unsigned char>(data[0]) == 0xFF
        && static_cast<unsigned char>(data[1]) == 0xFE) {
        std::wstring wide((data.size() - 2) / sizeof(wchar_t), L'\0');
        if (!wide.empty()) {
            std::memcpy(wide.data(), data.data() + 2, wide.size() * sizeof(wchar_t));
        }
        data = WideToUtf8(wide);
        return;
    }
    if (data.size() >= 3
        && static_cast<unsigned char>(data[0]) == 0xEF
        && static_cast<unsigned char>(data[1]) == 0xBB
        && static_cast<unsigned char>(data[2]) == 0xBF) {
        data.erase(0, 3);
    }
}

void ScanIniText(std::string data, ScanResult& out)
{
    NormalizeTextEncoding(data);

    bool inAutoSection = false;
    std::unordered_set<std::string> seen;
    size_t pos = 0;
    while (pos < data.size()) {
        size_t end = data.find('\n', pos);
        std::string line = data.substr(pos, end == std::string::npos ? std::string::npos : end - pos);
        pos = (end == std::string::npos) ? data.size() : end + 1;

        line = TrimA(line);
        if (line.empty() || line[0] == ';' || line[0] == '#') continue;

        if (line[0] == '[') {
            size_t close = line.find(']');
            if (close == std::string::npos) continue;
            std::string name = TrimA(line.substr(1, close - 1));
            if (name.empty()) continue;
            inAutoSection = (LowerAscii(name) == "autoreloader");
            if (!inAutoSection && name[0] != '#') {
                if (seen.insert(LowerAscii(name)).second) {
                    out.sections.push_back(name);
                }
            }
            continue;
        }

        if (inAutoSection) {
            size_t eq = line.find('=');
            if (eq == std::string::npos) continue;
            std::string key = LowerAscii(TrimA(line.substr(0, eq)));
            std::string value = TrimA(line.substr(eq + 1));
            size_t semi = value.find(';');
            if (semi != std::string::npos) value = TrimA(value.substr(0, semi));
            if (!key.empty() && !value.empty()) out.commands.emplace_back(key, value);
        }
    }
}

// ========================================================
// Type registry / index
// ========================================================
template <typename T>
int TypeCount() { return T::Array.Count; }

template <typename T>
void* TypeAt(int index) { return T::Array.Items[index]; }

template <typename T>
const char* TypeId(void* item) { return static_cast<T*>(item)->ID; }

template <typename T>
bool TypeLoad(void* item, CCINIClass* ini) { return static_cast<T*>(item)->LoadFromINI(ini); }

template <typename T>
TechnoTypeClass* TypeAsTechno(void* item) { return static_cast<T*>(item); }

struct TypeSlot
{
    const char* name;
    int (*count)();
    void* (*at)(int);
    const char* (*id)(void*);
    bool (*load)(void*, CCINIClass*);
    TechnoTypeClass* (*asTechno)(void*);
};

const TypeSlot kTypeSlots[] = {
    { "Vehicle",      &TypeCount<UnitTypeClass>,           &TypeAt<UnitTypeClass>,           &TypeId<UnitTypeClass>,           &TypeLoad<UnitTypeClass>,           &TypeAsTechno<UnitTypeClass> },
    { "Infantry",     &TypeCount<InfantryTypeClass>,       &TypeAt<InfantryTypeClass>,       &TypeId<InfantryTypeClass>,       &TypeLoad<InfantryTypeClass>,       &TypeAsTechno<InfantryTypeClass> },
    { "Building",     &TypeCount<BuildingTypeClass>,       &TypeAt<BuildingTypeClass>,       &TypeId<BuildingTypeClass>,       &TypeLoad<BuildingTypeClass>,       &TypeAsTechno<BuildingTypeClass> },
    { "Aircraft",     &TypeCount<AircraftTypeClass>,       &TypeAt<AircraftTypeClass>,       &TypeId<AircraftTypeClass>,       &TypeLoad<AircraftTypeClass>,       &TypeAsTechno<AircraftTypeClass> },
    { "Weapon",       &TypeCount<WeaponTypeClass>,         &TypeAt<WeaponTypeClass>,         &TypeId<WeaponTypeClass>,         &TypeLoad<WeaponTypeClass>,         nullptr },
    { "Warhead",      &TypeCount<WarheadTypeClass>,        &TypeAt<WarheadTypeClass>,        &TypeId<WarheadTypeClass>,        &TypeLoad<WarheadTypeClass>,        nullptr },
    { "Projectile",   &TypeCount<BulletTypeClass>,         &TypeAt<BulletTypeClass>,         &TypeId<BulletTypeClass>,         &TypeLoad<BulletTypeClass>,         nullptr },
    { "SuperWeapon",  &TypeCount<SuperWeaponTypeClass>,    &TypeAt<SuperWeaponTypeClass>,    &TypeId<SuperWeaponTypeClass>,    &TypeLoad<SuperWeaponTypeClass>,    nullptr },
    { "Animation",    &TypeCount<AnimTypeClass>,           &TypeAt<AnimTypeClass>,           &TypeId<AnimTypeClass>,           &TypeLoad<AnimTypeClass>,           nullptr },
    { "Particle",     &TypeCount<ParticleTypeClass>,       &TypeAt<ParticleTypeClass>,       &TypeId<ParticleTypeClass>,       &TypeLoad<ParticleTypeClass>,       nullptr },
    { "ParticleSys",  &TypeCount<ParticleSystemTypeClass>, &TypeAt<ParticleSystemTypeClass>, &TypeId<ParticleSystemTypeClass>, &TypeLoad<ParticleSystemTypeClass>, nullptr },
    { "VoxelAnim",    &TypeCount<VoxelAnimTypeClass>,      &TypeAt<VoxelAnimTypeClass>,      &TypeId<VoxelAnimTypeClass>,      &TypeLoad<VoxelAnimTypeClass>,      nullptr },
};

struct TypeEntry
{
    const TypeSlot* slot;
    void* item;
};

std::unordered_map<std::string, std::vector<TypeEntry>> g_TypeIndex;
std::unordered_map<std::string, TechnoTypeClass*> g_TechnoTypes;
// Section(lower) -> last known "AttachEffect.AttachTypes" list.
std::unordered_map<std::string, std::vector<std::string>> g_typeAECache;
int g_TypeTotal = 0;

// Experimental: rebuild existing objects on the game thread after a type reload.
HWND g_gameWnd = nullptr;
WNDPROC g_oldWndProc = nullptr;
UINT g_refreshMessage = 0;
std::mutex g_refreshMutex;
struct RefreshRequest
{
    std::string typeId;
    std::vector<DWORD> uniqueIds;
};
std::vector<RefreshRequest> g_refreshRequests;
std::atomic<bool> g_refreshWindowMissingLogged{ false };
bool g_refreshDispatcherReady = false;

int CurrentTypeTotal()
{
    int total = 0;
    for (const auto& slot : kTypeSlots) total += slot.count();
    return total;
}

void BuildTypeIndex()
{
    g_TypeIndex.clear();
    g_TechnoTypes.clear();
    g_TypeTotal = 0;

    for (const auto& slot : kTypeSlots) {
        int count = slot.count();
        for (int i = 0; i < count; ++i) {
            void* item = slot.at(i);
            if (!item) continue;
            const char* id = slot.id(item);
            if (!id || !*id) continue;
            std::string key = LowerAscii(id);
            g_TypeIndex[key].push_back(TypeEntry{ &slot, item });
            if (slot.asTechno) {
                if (auto type = slot.asTechno(item)) g_TechnoTypes[key] = type;
            }
            ++g_TypeTotal;
        }
    }

    LogF("[types] indexed %d types (%zu IDs, %zu techno types)",
        g_TypeTotal, g_TypeIndex.size(), g_TechnoTypes.size());
}

// ========================================================
// Phobos / Ares integration
// ========================================================
struct InteropVersion
{
    unsigned int major = 0;
    unsigned int minor = 0;
    unsigned int patch = 0;
};

using GetInteropVersionFn = HRESULT(__stdcall*)(InteropVersion*);
using ConvertTypeFn = HRESULT(__stdcall*)(FootClass*, TechnoTypeClass*);
// Phobos Interop 1.1 (v0.5-alpha1/2): AE_Attach has 11 parameters.
using AEAttachFnV1 = HRESULT(__stdcall*)(TechnoClass*, HouseClass*, TechnoClass*, AbstractClass*,
                                        const char**, int, int, int, int, int, int*);
// Phobos Interop 1.2 (develop): adds selfOwned / hasDelay (13 parameters).
using AEAttachFnV2 = HRESULT(__stdcall*)(TechnoClass*, HouseClass*, TechnoClass*, AbstractClass*,
                                        const char**, int, int, int, int, int, int*, bool, bool);
using AEDetachFn = HRESULT(__stdcall*)(TechnoClass*, const char**, int, int*);
using AEDetachGroupsFn = HRESULT(__stdcall*)(TechnoClass*, const char**, int, int*);
using SetVarFn = HRESULT(__stdcall*)(int, int);

struct ExtensionInfo
{
    bool ares = false;
    bool phobos = false;
    bool interop = false;
    InteropVersion version{};
    ConvertTypeFn convertToType = nullptr;
    AEAttachFnV1 aeAttachV1 = nullptr;
    AEAttachFnV2 aeAttachV2 = nullptr;
    AEDetachFn aeDetach = nullptr;
    AEDetachGroupsFn aeDetachGroups = nullptr;
    SetVarFn setLocalVar = nullptr;
    SetVarFn setGlobalVar = nullptr;
};

ExtensionInfo g_Extensions;

template <typename Fn>
Fn ResolveExport(HMODULE module, const char* name, const char* decorated)
{
    if (!module || !name) return nullptr;
    Fn fn = reinterpret_cast<Fn>(GetProcAddress(module, name));
    if (!fn && decorated) fn = reinterpret_cast<Fn>(GetProcAddress(module, decorated));
    return fn;
}

void DetectExtensions()
{
    g_Extensions = ExtensionInfo{};

    if (GetModuleHandleW(L"Ares.dll")) {
        g_Extensions.ares = true;
    }

    HMODULE phobos = GetModuleHandleW(L"Phobos.dll");
    if (phobos) {
        g_Extensions.phobos = true;

        auto getVersion = ResolveExport<GetInteropVersionFn>(
            phobos, "GetInteropAPIVersion", "_GetInteropAPIVersion@4");
        if (getVersion) {
            InteropVersion version{};
            if (SUCCEEDED(getVersion(&version))) {
                g_Extensions.interop = true;
                g_Extensions.version = version;
            }
        }

        g_Extensions.convertToType = ResolveExport<ConvertTypeFn>(
            phobos, "ConvertToType_Phobos", "_ConvertToType_Phobos@8");

        const bool interop12 = g_Extensions.version.major > 1
            || (g_Extensions.version.major == 1 && g_Extensions.version.minor >= 2);
        if (interop12) {
            g_Extensions.aeAttachV2 = ResolveExport<AEAttachFnV2>(
                phobos, "AE_Attach", "_AE_Attach@52");
            if (!g_Extensions.aeAttachV2) {
                g_Extensions.aeAttachV2 = ResolveExport<AEAttachFnV2>(
                    phobos, "_AE_Attach@48", nullptr);
            }
        } else {
            g_Extensions.aeAttachV1 = ResolveExport<AEAttachFnV1>(
                phobos, "AE_Attach", "_AE_Attach@44");
        }

        g_Extensions.aeDetach = ResolveExport<AEDetachFn>(
            phobos, "AE_Detach", "_AE_Detach@16");
        g_Extensions.aeDetachGroups = ResolveExport<AEDetachGroupsFn>(
            phobos, "AE_DetachByGroups", "_AE_DetachByGroups@16");
        g_Extensions.setLocalVar = ResolveExport<SetVarFn>(
            phobos, "Variables_SetLocal_Phobos", "_Variables_SetLocal_Phobos@8");
        g_Extensions.setGlobalVar = ResolveExport<SetVarFn>(
            phobos, "Variables_SetGlobal_Phobos", "_Variables_SetGlobal_Phobos@8");
    }

    if (g_Extensions.ares) {
        LogF("[ext] Ares.dll detected. Ares has no exported reload API; base-type LoadFromINI hooks are used, "
             "so Ares-extended fields on existing types refresh with the normal reload. "
             "Ares-only type arrays (e.g. AttachEffect types) are not accessible.");
    }
    if (g_Extensions.phobos) {
        if (g_Extensions.interop) {
            LogF("[ext] Phobos.dll detected, Interop API %u.%u.%u, Convert=%d AE=%d/%d Vars=%d/%d",
                g_Extensions.version.major, g_Extensions.version.minor,
                g_Extensions.version.patch,
                g_Extensions.convertToType ? 1 : 0,
                (g_Extensions.aeAttachV1 || g_Extensions.aeAttachV2) ? 1 : 0,
                (g_Extensions.aeDetach ? 1 : 0) + (g_Extensions.aeDetachGroups ? 1 : 0),
                g_Extensions.setLocalVar ? 1 : 0,
                g_Extensions.setGlobalVar ? 1 : 0);
        } else {
            LogF("[ext] Phobos.dll detected but its Interop API was not found (old Phobos?)");
        }
    }
    if (!g_Extensions.ares && !g_Extensions.phobos) {
        LogF("[ext] Neither Ares.dll nor Phobos.dll is loaded; vanilla reload only");
    }
}

// ========================================================
// Reload engine
// ========================================================
struct ReloadOutcome
{
    bool ok = false;
    int sections = 0;
    int matchedTypes = 0;
    int unmatchedSections = 0;
    int failedLoads = 0;
    int conversions = 0;
    int conversionFailures = 0;
    int aeAttached = 0;
    int aeDetached = 0;
    int varsSet = 0;
    int actionFailures = 0;
    std::string error;
    long long durationMs = 0;
};

std::vector<std::string> SplitCsv(const std::string& value)
{
    std::vector<std::string> out;
    size_t pos = 0;
    while (pos <= value.size()) {
        size_t comma = value.find(',', pos);
        std::string item = TrimA(value.substr(pos, comma == std::string::npos
            ? std::string::npos : comma - pos));
        if (!item.empty()) out.push_back(item);
        if (comma == std::string::npos) break;
        pos = comma + 1;
    }
    return out;
}

bool SplitMapping(const std::string& value, std::string& left, std::string& right)
{
    size_t arrow = value.find("->");
    size_t arrowLen = 2;
    if (arrow == std::string::npos) {
        arrow = value.find('>');
        arrowLen = 1;
    }
    if (arrow == std::string::npos) return false;
    left = TrimA(value.substr(0, arrow));
    right = TrimA(value.substr(arrow + arrowLen));
    return !left.empty() && !right.empty();
}

bool SplitTypeSpec(const std::string& value, std::string& typeId, std::string& rest)
{
    size_t colon = value.find(':');
    if (colon == std::string::npos) return false;
    typeId = TrimA(value.substr(0, colon));
    rest = TrimA(value.substr(colon + 1));
    return !typeId.empty() && !rest.empty();
}

TechnoTypeClass* FindTechnoTypeById(const std::string& id)
{
    auto it = g_TechnoTypes.find(LowerAscii(id));
    return it == g_TechnoTypes.end() ? nullptr : it->second;
}

template <typename Fn>
void ForEachTechnoOfType(TechnoTypeClass* type, Fn fn)
{
    if (!type) return;
    for (int i = 0; i < TechnoClass::Array.Count; ++i) {
        TechnoClass* object = TechnoClass::Array.Items[i];
        if (!object || !object->IsAlive) continue;
        if (object->GetTechnoType() != type) continue;
        fn(object);
    }
}

std::wstring NarrowToWide(const std::string& value)
{
    if (value.empty()) return {};
    UINT codePage = CP_UTF8;
    int need = MultiByteToWideChar(codePage, MB_ERR_INVALID_CHARS, value.c_str(), -1, nullptr, 0);
    if (need <= 0) {
        codePage = CP_ACP;
        need = MultiByteToWideChar(codePage, 0, value.c_str(), -1, nullptr, 0);
    }
    if (need <= 0) return {};
    std::vector<wchar_t> buffer(static_cast<size_t>(need), L'\0');
    MultiByteToWideChar(codePage, 0, value.c_str(), -1, buffer.data(), need);
    return std::wstring(buffer.data());
}

// Minimal rules scanner used to seed the "old AttachEffect.AttachTypes" cache
// before the first hot reload. Follows [#include] recursively.
void CollectRulesAE(
    const fs::path& file,
    const fs::path& gameDir,
    std::unordered_set<std::wstring>& visited,
    std::unordered_map<std::string, std::string>& out)
{
    std::wstring visitKey = file.wstring();
    for (auto& ch : visitKey) ch = static_cast<wchar_t>(towlower(ch));
    if (!visited.insert(visitKey).second) return;

    std::string bytes;
    if (!ReadAllBytesW(file, bytes)) return;
    NormalizeTextEncoding(bytes);

    std::string section;
    std::vector<std::string> includes;
    size_t pos = 0;
    while (pos < bytes.size()) {
        size_t end = bytes.find('\n', pos);
        std::string line = bytes.substr(pos, end == std::string::npos ? std::string::npos : end - pos);
        pos = (end == std::string::npos) ? bytes.size() : end + 1;
        line = TrimA(line);
        if (line.empty() || line[0] == ';' || (line[0] == '#' && line.rfind("[", 0) != 0)) continue;

        if (line[0] == '[') {
            size_t close = line.find(']');
            if (close == std::string::npos) continue;
            section = LowerAscii(TrimA(line.substr(1, close - 1)));
            continue;
        }
        if (section.empty()) continue;

        size_t eq = line.find('=');
        if (eq == std::string::npos) continue;
        std::string key = LowerAscii(TrimA(line.substr(0, eq)));
        std::string value = TrimA(line.substr(eq + 1));

        if (section == "#include") {
            if (!value.empty()) includes.push_back(value);
        }
        else if (key == "attacheffect.attachtypes") {
            out[section] = value;
        }
    }

    for (const auto& includeName : includes) {
        std::wstring wideName = NarrowToWide(includeName);
        if (wideName.empty()) continue;
        fs::path rel(wideName);
        const fs::path candidates[] = {
            gameDir / rel,
            file.parent_path() / rel,
            gameDir / rel.filename(),
        };
        for (const auto& candidate : candidates) {
            if (FileExistsW(candidate)) {
                CollectRulesAE(candidate, gameDir, visited, out);
                break;
            }
        }
    }
}

void LoadAEBaseline(const fs::path& gameDir)
{
    g_typeAECache.clear();

    const wchar_t* names[] = { L"rulesmo.ini", L"rulesmd.ini", L"rules.ini" };
    fs::path rulesFile;
    for (const wchar_t* name : names) {
        fs::path candidate = gameDir / name;
        if (FileExistsW(candidate)) {
            rulesFile = candidate;
            break;
        }
    }
    if (rulesFile.empty()) {
        LogF("[ae-auto] no rules ini found; baseline AttachTypes cache is empty");
        return;
    }

    std::unordered_map<std::string, std::string> raw;
    std::unordered_set<std::wstring> visited;
    CollectRulesAE(rulesFile, gameDir, visited, raw);

    for (const auto& [section, value] : raw) {
        std::vector<std::string> namesList = SplitCsv(value);
        if (!namesList.empty()) g_typeAECache[section] = namesList;
    }
    LogF("[ae-auto] baseline loaded: %zu sections from %s",
        g_typeAECache.size(), WideToUtf8(rulesFile.wstring()).c_str());
}

std::vector<int> ReadIntList(CCINIClass& ini, const char* section, const char* key)
{
    char buffer[2048] = {};
    if (ini.ReadString(section, key, "", buffer, sizeof(buffer)) <= 0) return {};
    std::vector<int> out;
    for (const auto& item : SplitCsv(buffer)) {
        char* end = nullptr;
        long value = std::strtol(item.c_str(), &end, 10);
        if (end && *end == '\0') out.push_back(static_cast<int>(value));
    }
    return out;
}

int ParamAt(const std::vector<int>& values, int index, int fallback)
{
    if (values.empty()) return fallback;
    size_t i = index < 0 ? 0 : static_cast<size_t>(index);
    if (i >= values.size()) i = values.size() - 1;
    return values[i];
}

void ApplyConvert(const std::string& value, ReloadOutcome& outcome)
{
    if (!g_Extensions.convertToType) {
        LogF("[convert] skipped: Phobos ConvertToType_Phobos not available");
        return;
    }

    std::string from;
    std::string to;
    if (!SplitMapping(value, from, to)) {
        LogF("[convert] invalid mapping: %s", value.c_str());
        return;
    }

    TechnoTypeClass* fromType = FindTechnoTypeById(from);
    TechnoTypeClass* toType = FindTechnoTypeById(to);
    if (!fromType) {
        LogF("[convert] source type not found: %s", from.c_str());
        return;
    }
    if (!toType) {
        LogF("[convert] target type not found: %s", to.c_str());
        return;
    }
    if (fromType->WhatAmI() != toType->WhatAmI()) {
        LogF("[convert] incompatible types: %s -> %s", from.c_str(), to.c_str());
        return;
    }

    int converted = 0;
    int failed = 0;
    ForEachTechnoOfType(fromType, [&](TechnoClass* object) {
        FootClass* foot = nullptr;
        switch (object->WhatAmI()) {
            case AbstractType::Unit:
                foot = static_cast<UnitClass*>(object);
                break;
            case AbstractType::Infantry:
                foot = static_cast<InfantryClass*>(object);
                break;
            case AbstractType::Aircraft:
                foot = static_cast<AircraftClass*>(object);
                break;
            default:
                return;
        }
        HRESULT hr = g_Extensions.convertToType(foot, toType);
        if (SUCCEEDED(hr)) ++converted;
        else ++failed;
    });

    outcome.conversions += converted;
    outcome.conversionFailures += failed;
    LogF("[convert] %s -> %s: converted %d, failed %d", from.c_str(), to.c_str(), converted, failed);
}

bool HasAEAttach()
{
    return g_Extensions.aeAttachV1 != nullptr || g_Extensions.aeAttachV2 != nullptr;
}

HRESULT CallAEAttach(
    TechnoClass* target,
    const char** names,
    int count,
    int duration,
    int delay,
    int initial,
    int recreation,
    int* attached,
    bool selfOwned,
    bool hasDelay)
{
    if (g_Extensions.aeAttachV2) {
        return g_Extensions.aeAttachV2(
            target, nullptr, nullptr, nullptr,
            names, count, duration, delay, initial, recreation,
            attached, selfOwned, hasDelay);
    }
    if (g_Extensions.aeAttachV1) {
        // Interop 1.1 has no selfOwned / hasDelay parameters.
        return g_Extensions.aeAttachV1(
            target, nullptr, nullptr, nullptr,
            names, count, duration, delay, initial, recreation,
            attached);
    }
    return E_FAIL;
}

void ApplyAEAttach(const std::string& value, ReloadOutcome& outcome)
{
    if (!HasAEAttach()) {
        LogF("[ae] attach skipped: Phobos AE_Attach not available");
        return;
    }

    std::string typeId;
    std::string rest;
    if (!SplitTypeSpec(value, typeId, rest)) {
        LogF("[ae] invalid attach command: %s", value.c_str());
        return;
    }
    TechnoTypeClass* type = FindTechnoTypeById(typeId);
    if (!type) {
        LogF("[ae] attach type not found: %s", typeId.c_str());
        return;
    }

    std::vector<std::string> names = SplitCsv(rest);
    if (names.empty()) {
        LogF("[ae] attach has no effect names: %s", value.c_str());
        return;
    }
    std::vector<const char*> namePtrs;
    namePtrs.reserve(names.size());
    for (const auto& name : names) namePtrs.push_back(name.c_str());

    int attached = 0;
    int failed = 0;
    ForEachTechnoOfType(type, [&](TechnoClass* object) {
        int objectAttached = 0;
        HRESULT hr = CallAEAttach(
            object, namePtrs.data(), static_cast<int>(namePtrs.size()),
            0, -1, -1, -1, &objectAttached, false, true);
        if (SUCCEEDED(hr)) attached += objectAttached;
        else ++failed;
    });

    outcome.aeAttached += attached;
    outcome.actionFailures += failed;
    LogF("[ae] attach %s: effects=%zu attached=%d failed=%d",
        typeId.c_str(), names.size(), attached, failed);
}

void ApplyAEDetach(const std::string& value, ReloadOutcome& outcome, bool byGroup)
{
    AEDetachFn fn = byGroup
        ? reinterpret_cast<AEDetachFn>(g_Extensions.aeDetachGroups)
        : g_Extensions.aeDetach;
    if (!fn) {
        LogF("[ae] detach skipped: Phobos %s not available", byGroup ? "AE_DetachByGroups" : "AE_Detach");
        return;
    }

    std::string typeId;
    std::string rest;
    if (!SplitTypeSpec(value, typeId, rest)) {
        LogF("[ae] invalid detach command: %s", value.c_str());
        return;
    }
    TechnoTypeClass* type = FindTechnoTypeById(typeId);
    if (!type) {
        LogF("[ae] detach type not found: %s", typeId.c_str());
        return;
    }

    std::vector<std::string> names = SplitCsv(rest);
    if (names.empty()) return;
    std::vector<const char*> namePtrs;
    namePtrs.reserve(names.size());
    for (const auto& name : names) namePtrs.push_back(name.c_str());

    int removed = 0;
    int failed = 0;
    ForEachTechnoOfType(type, [&](TechnoClass* object) {
        int objectRemoved = 0;
        HRESULT hr = fn(object, namePtrs.data(), static_cast<int>(namePtrs.size()), &objectRemoved);
        if (SUCCEEDED(hr)) removed += objectRemoved;
        else ++failed;
    });

    outcome.aeDetached += removed;
    outcome.actionFailures += failed;
    LogF("[ae] detach%s %s: names=%zu removed=%d failed=%d",
        byGroup ? " group" : "", typeId.c_str(), names.size(), removed, failed);
}

void ApplyAEReplace(const std::string& value, ReloadOutcome& outcome, bool byGroup)
{
    if (!HasAEAttach()) {
        LogF("[ae] replace skipped: Phobos AE_Attach not available");
        return;
    }
    AEDetachFn detachFn = byGroup
        ? reinterpret_cast<AEDetachFn>(g_Extensions.aeDetachGroups)
        : g_Extensions.aeDetach;
    if (!detachFn) {
        LogF("[ae] replace skipped: Phobos %s not available", byGroup ? "AE_DetachByGroups" : "AE_Detach");
        return;
    }

    std::string typeId;
    std::string rest;
    if (!SplitTypeSpec(value, typeId, rest)) {
        LogF("[ae] invalid replace command: %s", value.c_str());
        return;
    }
    TechnoTypeClass* type = FindTechnoTypeById(typeId);
    if (!type) {
        LogF("[ae] replace type not found: %s", typeId.c_str());
        return;
    }

    std::string oldSpec;
    std::string newSpec;
    if (!SplitMapping(rest, oldSpec, newSpec)) {
        LogF("[ae] invalid replace mapping: %s", value.c_str());
        return;
    }

    std::vector<std::string> oldNames = SplitCsv(oldSpec);
    std::vector<std::string> newNames = SplitCsv(newSpec);
    if (oldNames.empty() || newNames.empty()) {
        LogF("[ae] replace has empty side: %s", value.c_str());
        return;
    }
    std::vector<const char*> oldPtrs;
    oldPtrs.reserve(oldNames.size());
    for (const auto& name : oldNames) oldPtrs.push_back(name.c_str());
    std::vector<const char*> newPtrs;
    newPtrs.reserve(newNames.size());
    for (const auto& name : newNames) newPtrs.push_back(name.c_str());

    int removed = 0;
    int attached = 0;
    int failed = 0;
    ForEachTechnoOfType(type, [&](TechnoClass* object) {
        int objectRemoved = 0;
        HRESULT hr = detachFn(object, oldPtrs.data(), static_cast<int>(oldPtrs.size()), &objectRemoved);
        if (FAILED(hr)) {
            ++failed;
            return;
        }
        removed += objectRemoved;

        int objectAttached = 0;
        hr = CallAEAttach(
            object, newPtrs.data(), static_cast<int>(newPtrs.size()),
            0, -1, -1, -1, &objectAttached, false, true);
        if (FAILED(hr)) {
            ++failed;
            return;
        }
        attached += objectAttached;
    });

    outcome.aeDetached += removed;
    outcome.aeAttached += attached;
    outcome.actionFailures += failed;
    LogF("[ae] replace%s %s: removed=%d attached=%d failed=%d",
        byGroup ? " group" : "", typeId.c_str(), removed, attached, failed);
}

void ApplySetVariable(const std::string& value, ReloadOutcome& outcome, bool global)
{
    SetVarFn fn = global ? g_Extensions.setGlobalVar : g_Extensions.setLocalVar;
    if (!fn) {
        LogF("[var] %s skipped: Phobos %s not available",
            global ? "global" : "local",
            global ? "Variables_SetGlobal_Phobos" : "Variables_SetLocal_Phobos");
        return;
    }

    size_t eq = value.find('=');
    if (eq == std::string::npos) {
        LogF("[var] invalid command: %s", value.c_str());
        return;
    }
    std::string indexText = TrimA(value.substr(0, eq));
    std::string valueText = TrimA(value.substr(eq + 1));
    if (indexText.empty() || valueText.empty()) {
        LogF("[var] invalid command: %s", value.c_str());
        return;
    }

    char* end = nullptr;
    long index = std::strtol(indexText.c_str(), &end, 10);
    if (!end || *end != '\0') {
        LogF("[var] invalid index: %s", indexText.c_str());
        return;
    }
    end = nullptr;
    long number = std::strtol(valueText.c_str(), &end, 10);
    if (!end || *end != '\0') {
        LogF("[var] invalid value: %s", valueText.c_str());
        return;
    }

    HRESULT hr = fn(static_cast<int>(index), static_cast<int>(number));
    if (SUCCEEDED(hr)) {
        ++outcome.varsSet;
        LogF("[var] set %s[%ld] = %ld", global ? "global" : "local", index, number);
    } else {
        ++outcome.actionFailures;
        LogF("[var] set %s[%ld] failed (hr=0x%08X)",
            global ? "global" : "local", index, static_cast<unsigned int>(hr));
    }
}

void ApplyCommands(const std::vector<std::pair<std::string, std::string>>& commands,
                   const Config& cfg, ReloadOutcome& outcome)
{
    for (const auto& [key, value] : commands) {
        if (key.rfind("convert", 0) == 0) {
            if (!cfg.liveConvert) {
                LogF("[convert] skipped: LiveConvert=false");
            } else {
                ApplyConvert(value, outcome);
            }
        }
        else if (key == "attachae") {
            ApplyAEAttach(value, outcome);
        }
        else if (key == "detachae") {
            ApplyAEDetach(value, outcome, false);
        }
        else if (key == "detachaegroup") {
            ApplyAEDetach(value, outcome, true);
        }
        else if (key == "replaceae") {
            ApplyAEReplace(value, outcome, false);
        }
        else if (key == "replaceaegroup") {
            ApplyAEReplace(value, outcome, true);
        }
        else if (key == "setlocalvar") {
            ApplySetVariable(value, outcome, false);
        }
        else if (key == "setglobalvar") {
            ApplySetVariable(value, outcome, true);
        }
        else {
            LogF("[auto] unknown command: %s", key.c_str());
        }
    }
}

void SyncAttachEffectsForSection(
    const std::string& section,
    CCINIClass& ini,
    const Config& cfg,
    ReloadOutcome& outcome)
{
    if (!cfg.autoSyncAE || !HasAEAttach() || !g_Extensions.aeDetach) return;

    TechnoTypeClass* type = FindTechnoTypeById(section);
    if (!type) return;

    const char* attachKey = "AttachEffect.AttachTypes";
    if (!ini.Exists(section.c_str(), attachKey)) return;

    char buffer[4096] = {};
    ini.ReadString(section.c_str(), attachKey, "", buffer, sizeof(buffer));
    std::vector<std::string> newNames = SplitCsv(buffer);

    std::string sectionKey = LowerAscii(section);
    std::vector<std::string> oldNames;
    auto cacheIt = g_typeAECache.find(sectionKey);
    if (cacheIt != g_typeAECache.end()) oldNames = cacheIt->second;

    // Detach old and new type-owned names first, so a reload replaces instead of stacking.
    std::vector<std::string> detachNames = oldNames;
    std::unordered_set<std::string> seenNames;
    for (const auto& name : detachNames) seenNames.insert(LowerAscii(name));
    for (const auto& name : newNames) {
        if (seenNames.insert(LowerAscii(name)).second) detachNames.push_back(name);
    }

    int removedTotal = 0;
    int detachFailures = 0;
    if (!detachNames.empty()) {
        std::vector<const char*> namePtrs;
        namePtrs.reserve(detachNames.size());
        for (const auto& name : detachNames) namePtrs.push_back(name.c_str());

        ForEachTechnoOfType(type, [&](TechnoClass* object) {
            int removed = 0;
            HRESULT hr = g_Extensions.aeDetach(
                object, namePtrs.data(), static_cast<int>(namePtrs.size()), &removed);
            if (SUCCEEDED(hr)) removedTotal += removed;
            else ++detachFailures;
        });
    }

    const auto durationOverrides = ReadIntList(ini, section.c_str(), "AttachEffect.DurationOverrides");
    const auto delays = ReadIntList(ini, section.c_str(), "AttachEffect.Delays");
    const auto initialDelays = ReadIntList(ini, section.c_str(), "AttachEffect.InitialDelays");
    const auto recreationDelays = ReadIntList(ini, section.c_str(), "AttachEffect.RecreationDelays");

    int attachedTotal = 0;
    int attachFailures = 0;
    for (size_t i = 0; i < newNames.size(); ++i) {
        const char* namePtr = newNames[i].c_str();
        int duration = ParamAt(durationOverrides, static_cast<int>(i), 0);
        int delay = ParamAt(delays, static_cast<int>(i), -1);
        int initial = ParamAt(initialDelays, static_cast<int>(i), -1);
        int recreation = ParamAt(recreationDelays, static_cast<int>(i), -1);

        ForEachTechnoOfType(type, [&](TechnoClass* object) {
            int attached = 0;
            HRESULT hr = CallAEAttach(
                object, &namePtr, 1,
                duration, delay, initial, recreation,
                &attached, true, true);
            if (SUCCEEDED(hr)) attachedTotal += attached;
            else ++attachFailures;
        });
    }

    // Phobos also supports removing types/groups after the attach list.
    int removeFailures = 0;
    if (g_Extensions.aeDetach && ini.Exists(section.c_str(), "AttachEffect.RemoveTypes")) {
        char removeBuffer[2048] = {};
        ini.ReadString(section.c_str(), "AttachEffect.RemoveTypes", "", removeBuffer, sizeof(removeBuffer));
        std::vector<std::string> removeNames = SplitCsv(removeBuffer);
        if (!removeNames.empty()) {
            std::vector<const char*> namePtrs;
            for (const auto& name : removeNames) namePtrs.push_back(name.c_str());
            ForEachTechnoOfType(type, [&](TechnoClass* object) {
                int removed = 0;
                HRESULT hr = g_Extensions.aeDetach(
                    object, namePtrs.data(), static_cast<int>(namePtrs.size()), &removed);
                if (SUCCEEDED(hr)) removedTotal += removed;
                else ++removeFailures;
            });
        }
    }
    if (g_Extensions.aeDetachGroups && ini.Exists(section.c_str(), "AttachEffect.RemoveGroups")) {
        char removeBuffer[2048] = {};
        ini.ReadString(section.c_str(), "AttachEffect.RemoveGroups", "", removeBuffer, sizeof(removeBuffer));
        std::vector<std::string> removeGroups = SplitCsv(removeBuffer);
        if (!removeGroups.empty()) {
            std::vector<const char*> groupPtrs;
            for (const auto& group : removeGroups) groupPtrs.push_back(group.c_str());
            ForEachTechnoOfType(type, [&](TechnoClass* object) {
                int removed = 0;
                HRESULT hr = g_Extensions.aeDetachGroups(
                    object, groupPtrs.data(), static_cast<int>(groupPtrs.size()), &removed);
                if (SUCCEEDED(hr)) removedTotal += removed;
                else ++removeFailures;
            });
        }
    }

    g_typeAECache[sectionKey] = newNames;
    outcome.aeDetached += removedTotal;
    outcome.aeAttached += attachedTotal;
    outcome.actionFailures += detachFailures + attachFailures + removeFailures;

    LogF("[ae-auto] [%s] old=%zu new=%zu removed=%d attached=%d failed=%d",
        section.c_str(), oldNames.size(), newNames.size(),
        removedTotal, attachedTotal, detachFailures + attachFailures + removeFailures);
}

LRESULT CALLBACK GameWndProc(HWND hwnd, UINT msg, WPARAM wparam, LPARAM lparam);

struct WindowSearch
{
    DWORD processId;
    HWND best;
    long area;
};

BOOL CALLBACK FindGameWindowProc(HWND hwnd, LPARAM lparam)
{
    auto* search = reinterpret_cast<WindowSearch*>(lparam);
    DWORD processId = 0;
    GetWindowThreadProcessId(hwnd, &processId);
    if (processId != search->processId || !IsWindowVisible(hwnd)) return TRUE;

    wchar_t className[128] = {};
    wchar_t title[256] = {};
    GetClassNameW(hwnd, className, 128);
    GetWindowTextW(hwnd, title, 256);

    RECT rect = {};
    GetWindowRect(hwnd, &rect);
    const long area = (rect.right - rect.left) * (rect.bottom - rect.top);
    const bool likely = _wcsicmp(className, L"Game") == 0
        || wcsstr(title, L"Mental Omega") != nullptr
        || wcsstr(title, L"Yuri") != nullptr
        || wcsstr(title, L"Command") != nullptr;

    if (likely) {
        search->best = hwnd;
        search->area = area;
        return FALSE;
    }
    return TRUE;
}

void UninstallGameThreadDispatcher()
{
    if (g_gameWnd && g_oldWndProc && IsWindow(g_gameWnd)) {
        SetWindowLongPtrW(g_gameWnd, GWLP_WNDPROC, reinterpret_cast<LONG_PTR>(g_oldWndProc));
    }
    g_gameWnd = nullptr;
    g_oldWndProc = nullptr;
    g_refreshDispatcherReady = false;
}

void EnsureGameThreadDispatcher()
{
    if (g_refreshDispatcherReady && g_gameWnd && IsWindow(g_gameWnd)) return;

    if (!g_refreshMessage) {
        g_refreshMessage = RegisterWindowMessageW(L"AutoReloader_RefreshExistingUnits");
    }
    if (!g_refreshMessage) return;

    WindowSearch search{ GetCurrentProcessId(), nullptr, 0 };
    EnumWindows(FindGameWindowProc, reinterpret_cast<LPARAM>(&search));
    if (!search.best) {
        if (!g_refreshWindowMissingLogged.exchange(true)) {
            LogF("[rebuild] game window not found yet; existing-unit rebuild will retry on next reload");
        }
        return;
    }

    SetLastError(0);
    WNDPROC oldProc = reinterpret_cast<WNDPROC>(
        SetWindowLongPtrW(search.best, GWLP_WNDPROC, reinterpret_cast<LONG_PTR>(GameWndProc)));
    if (!oldProc && GetLastError() != 0) {
        LogF("[rebuild] could not subclass game window (error %lu)", GetLastError());
        return;
    }

    g_gameWnd = search.best;
    g_oldWndProc = oldProc;
    g_refreshDispatcherReady = true;
    g_refreshWindowMissingLogged = false;

    wchar_t className[128] = {};
    GetClassNameW(g_gameWnd, className, 128);
    LogF("[rebuild] game-thread dispatcher installed (window class=%s)", WideToUtf8(std::wstring(className)).c_str());
}

TechnoClass* FindTechnoByUniqueId(DWORD uniqueId)
{
    for (int i = 0; i < TechnoClass::Array.Count; ++i) {
        TechnoClass* object = TechnoClass::Array.Items[i];
        if (object && object->UniqueID == uniqueId) return object;
    }
    return nullptr;
}

bool CanRebuildExistingUnit(TechnoClass* old)
{
    if (!old || !old->IsAlive || old->InLimbo || old->Health <= 0) return false;
    if (old->Transporter || old->Passengers.NumPassengers > 0) return false;
    if (old->MindControlledBy || old->BunkerLinkedItem) return false;
    if (old->IsSinking || old->Deactivated) return false;
    if (old->CloakState != CloakState::Uncloaked) return false;
    if (old->IronCurtainTimer.GetTimeLeft() > 0 || old->ForceShielded) return false;
    if (old->TemporalTargetingMe || old->BeingWarpedOut) return false;
    if (old->SpawnManager || old->SpawnOwner || old->SlaveManager || old->SlaveOwner) return false;
    if (old->Airstrike) return false;

    auto* foot = static_cast<FootClass*>(old);
    if (foot->Team) return false;

    if (old->WhatAmI() == UnitClass::AbsID) {
        auto* unit = static_cast<UnitClass*>(old);
        if (unit->Deployed || unit->Deploying || unit->Undeploying
            || unit->IsHarvesting || unit->IsFollowerCar || unit->FollowerCar) {
            return false;
        }
    }
    else if (old->WhatAmI() == InfantryClass::AbsID) {
        auto* infantry = static_cast<InfantryClass*>(old);
        if (infantry->IsDeployed() || infantry->Crawling) return false;
    }
    else {
        return false;
    }

    return true;
}

bool RebuildOneExistingUnit(TechnoClass* old, TechnoTypeClass* type)
{
    if (!old || !type) return false;

    const CoordStruct location = old->Location;
    const DirStruct facing = old->PrimaryFacing.Current();
    const VeterancyStruct veterancy = old->Veterancy;
    const int health = old->Health;
    const int ammo = old->Ammo;
    const int group = old->Group;
    const bool selected = old->IsSelected;
    TagClass* tag = old->AttachedTag;
    const DWORD uniqueId = old->UniqueID;

    auto* oldFoot = static_cast<FootClass*>(old);
    const int oldMaxHealth = old->GetTechnoType()->Strength;

    ObjectClass* created = type->CreateObject(old->Owner);
    if (!created) {
        LogF("[rebuild] [%s] CreateObject failed", type->ID);
        return false;
    }

    auto* fresh = static_cast<FootClass*>(created);
    fresh->Veterancy = veterancy;
    fresh->Ammo = ammo;
    fresh->Group = group;
    fresh->PrimaryFacing.SetCurrent(facing);

    old->AttachedTag = nullptr;
    if (!old->Limbo()) {
        fresh->UnInit();
        old->AttachedTag = tag;
        return false;
    }

    ++Unsorted::ScenarioInit;
    const bool placed = fresh->Unlimbo(location, facing.GetDir());
    --Unsorted::ScenarioInit;

    if (!placed) {
        fresh->UnInit();
        old->Unlimbo(location, facing.GetDir());
        old->AttachedTag = tag;
        if (selected) old->Select();
        return false;
    }

    fresh->AttachedTag = tag;
    fresh->Veterancy = veterancy;
    fresh->Ammo = ammo;
    fresh->Group = group;
    fresh->PrimaryFacing.SetCurrent(facing);
    fresh->IsInitiated = true;

    int newHealth = health;
    const int newMaxHealth = type->Strength;
    if (oldMaxHealth > 0 && newMaxHealth > 0) {
        newHealth = static_cast<int>(
            (static_cast<long long>(health) * newMaxHealth + oldMaxHealth / 2) / oldMaxHealth);
    }
    fresh->Health = std::max(1, newHealth);
    if (type->Ammo > 0) fresh->Ammo = std::min(ammo, type->Ammo);

    // Do not carry stale move/attack state into the new object. A fresh unit that
    // keeps an old Destination without an old path can end up refusing move orders.
    fresh->Target = nullptr;
    fresh->ArchiveTarget = nullptr;
    fresh->Destination = nullptr;
    fresh->LastDestination = nullptr;
    fresh->MegaDestination = nullptr;

    // Unlimbo does not always create a locomotor for a freshly constructed
    // object; without it the unit renders but cannot move.
    if (fresh->Locomotor) {
        fresh->Locomotor->Link_To_Object(fresh);
        fresh->Locomotor->Unlimbo();
    } else {
        const CLSID& locomotorClass = reinterpret_cast<const CLSID&>(type->Locomotor);
        auto locomotor = LocomotionClass::CreateInstance(locomotorClass);
        if (locomotor) {
            locomotor->Link_To_Object(fresh);
            fresh->Locomotor = locomotor;
            fresh->Locomotor->Unlimbo();
            LogF("[rebuild] [%s] locomotor created", type->ID);
        } else {
            LogF("[rebuild] [%s] locomotor creation failed", type->ID);
        }
    }

    // A constructed object placed with Unlimbo is not guaranteed to join the
    // logic collection. Without this it can be selected, but it never receives
    // movement/attack orders (and can hang engine shutdown).
    if (!fresh->IsInLogic) {
        const bool added = LogicClass::Instance.AddObject(fresh, false);
        if (added) {
            fresh->IsInLogic = true;
            LogF("[rebuild] [%s] added to logic", type->ID);
        } else {
            LogF("[rebuild] [%s] failed to add to logic", type->ID);
        }
    }

    if (selected) {
        old->Deselect();
        fresh->Select();
    }

    old->UnInit();
    fresh->UniqueID = uniqueId;

    fresh->QueueMission(Mission::Guard, false);
    fresh->NextMission();
    return true;
}

void ProcessRefreshRequests()
{
    std::vector<RefreshRequest> requests;
    {
        std::lock_guard<std::mutex> lock(g_refreshMutex);
        requests.swap(g_refreshRequests);
    }

    for (const auto& request : requests) {
        auto found = g_TechnoTypes.find(request.typeId);
        if (found == g_TechnoTypes.end() || !found->second) continue;
        TechnoTypeClass* type = found->second;

        int rebuilt = 0;
        int skipped = 0;
        int failed = 0;

        std::vector<DWORD> uniqueIds = request.uniqueIds;
        if (uniqueIds.empty()) {
            for (int i = 0; i < TechnoClass::Array.Count; ++i) {
                TechnoClass* object = TechnoClass::Array.Items[i];
                if (!object || !object->IsAlive) continue;
                if (object->GetTechnoType() != type) continue;
                uniqueIds.push_back(object->UniqueID);
            }
        }

        for (DWORD uniqueId : uniqueIds) {
            TechnoClass* old = FindTechnoByUniqueId(uniqueId);
            if (!old || old->GetTechnoType() != type || !CanRebuildExistingUnit(old)) {
                ++skipped;
                continue;
            }
            if (RebuildOneExistingUnit(old, type)) ++rebuilt;
            else ++failed;
        }
        LogF("[rebuild] [%s] rebuilt=%d skipped=%d failed=%d",
            request.typeId.c_str(), rebuilt, skipped, failed);
    }
}

LRESULT CALLBACK GameWndProc(HWND hwnd, UINT msg, WPARAM wparam, LPARAM lparam)
{
    if (msg == g_refreshMessage) {
        ProcessRefreshRequests();
        return 0;
    }
    if (g_oldWndProc) {
        return CallWindowProcW(g_oldWndProc, hwnd, msg, wparam, lparam);
    }
    return DefWindowProcW(hwnd, msg, wparam, lparam);
}

void QueueExistingUnitRefresh(const std::string& section, TechnoTypeClass* type, const Config& cfg)
{
    if (!cfg.refreshExisting || !type) return;
    const AbstractType what = type->WhatAmI();
    if (what != InfantryTypeClass::AbsID && what != UnitTypeClass::AbsID) return;

    EnsureGameThreadDispatcher();
    if (!g_gameWnd) return;

    const std::string typeId = LowerAscii(section);
    {
        std::lock_guard<std::mutex> lock(g_refreshMutex);
        for (const auto& item : g_refreshRequests) {
            if (item.typeId == typeId) return;
        }
        g_refreshRequests.push_back(RefreshRequest{ typeId, {} });
    }

    if (!PostMessageW(g_gameWnd, g_refreshMessage, 0, 0)) {
        LogF("[rebuild] PostMessage failed (error %lu)", GetLastError());
    }
}

bool ReloadFile(const fs::path& target, const Config& cfg, ReloadOutcome& outcome)
{
    auto started = std::chrono::steady_clock::now();
    outcome = ReloadOutcome{};

    std::string bytes;
    if (!ReadAllBytesRetry(target, bytes, 3)) {
        outcome.error = "cannot read file";
        LogF("[reload] %s: cannot read file", WideToUtf8(target.wstring()).c_str());
        return false;
    }

    ScanResult scan;
    ScanIniText(bytes, scan);
    if (scan.sections.empty() && scan.commands.empty()) {
        outcome.ok = true;
        LogF("[reload] %s: no sections", WideToUtf8(target.wstring()).c_str());
        return true;
    }

    fs::path parsePath = target;
    fs::path tempPath;
    bool tempUsed = false;
    bool needNewline = !bytes.empty() && bytes.back() != '\n' && bytes.back() != '\r';

    if (!scan.sections.empty() && needNewline) {
        tempPath = target;
        tempPath += L".ar_tmp";
        std::string data = bytes;
        data += "\r\n";
        if (WriteAllBytesW(tempPath, data)) {
            parsePath = tempPath;
            tempUsed = true;
        } else if (AppendNewlineW(target)) {
            LogF("[reload] %s: appended trailing newline in place", WideToUtf8(target.wstring()).c_str());
        }
    }

    bool ok = true;
    if (!scan.sections.empty()) {
        std::string ansiPath = WideToAnsi(parsePath.wstring());
        if (ansiPath.empty()) {
            outcome.error = "path conversion failed";
            ok = false;
        } else {
            CCFileClass file(ansiPath.c_str());
            CCINIClass ini;
            if (!ini.ReadCCFile(&file)) {
                outcome.error = "CCINIClass::ReadCCFile failed";
                LogF("[reload] %s: ReadCCFile failed", WideToUtf8(parsePath.wstring()).c_str());
                ok = false;
            } else {
                outcome.sections = static_cast<int>(scan.sections.size());
                for (const auto& section : scan.sections) {
                    std::string key = LowerAscii(section);
                    auto found = g_TypeIndex.find(key);
                    if (found == g_TypeIndex.end()) {
                        ++outcome.unmatchedSections;
                        LogF("[reload]   [%s] -> not found", section.c_str());
                        continue;
                    }

                    for (const auto& entry : found->second) {
                        bool loaded = entry.slot->load(entry.item, &ini);
                        ++outcome.matchedTypes;
                        if (!loaded) {
                            ++outcome.failedLoads;
                            LogF("[reload]   [%s] -> %s: LoadFromINI failed",
                                section.c_str(), entry.slot->name);
                        } else {
                            LogF("[reload]   [%s] -> %s", section.c_str(), entry.slot->name);
                        }
                    }

                    SyncAttachEffectsForSection(section, ini, cfg, outcome);
                    if (auto* refreshedType = FindTechnoTypeById(section)) {
                        QueueExistingUnitRefresh(section, refreshedType, cfg);
                    }
                }
            }
        }
    }

    if (ok && !scan.commands.empty()) {
        ApplyCommands(scan.commands, cfg, outcome);
    }

    if (tempUsed) {
        std::error_code ec;
        fs::remove(tempPath, ec);
    }

    outcome.ok = ok;
    outcome.durationMs = std::chrono::duration_cast<std::chrono::milliseconds>(
        std::chrono::steady_clock::now() - started).count();
    LogF("[reload] %s: sections=%d types=%d unmatched=%d failed=%d convert=%d/%d ae=%d/%d vars=%d time=%lldms",
        WideToUtf8(target.wstring()).c_str(),
        outcome.sections, outcome.matchedTypes, outcome.unmatchedSections,
        outcome.failedLoads, outcome.conversions, outcome.conversionFailures,
        outcome.aeAttached, outcome.aeDetached, outcome.varsSet,
        outcome.durationMs);
    return ok;
}

// ========================================================
// Monitor
// ========================================================
struct FileState
{
    bool valid = false;
    FileMeta meta{};
};

fs::path g_GameDir;
fs::path g_ConfigPath;

bool IsGameForeground()
{
    HWND hwnd = GetForegroundWindow();
    if (!hwnd) return false;
    DWORD pid = 0;
    GetWindowThreadProcessId(hwnd, &pid);
    return pid == GetCurrentProcessId();
}

void InitFileStates(const Config& cfg, std::map<std::wstring, FileState>& states)
{
    states.clear();
    for (const auto& target : cfg.targets) {
        fs::path full = ResolveTarget(g_GameDir, target);
        FileState state;
        state.valid = GetFileMetaW(full, state.meta);
        states[full.wstring()] = state;
    }
}

void ReloadAll(const Config& cfg, std::map<std::wstring, FileState>& states, const char* reason)
{
    LogF("[reload] triggered by %s", reason);
    bool anyOk = false;
    for (const auto& target : cfg.targets) {
        fs::path full = ResolveTarget(g_GameDir, target);
        if (!FileExistsW(full)) continue;

        ReloadOutcome outcome;
        bool ok = ReloadFile(full, cfg, outcome);
        anyOk = anyOk || ok;

        FileState state;
        state.valid = GetFileMetaW(full, state.meta);
        states[full.wstring()] = state;
    }
    if (anyOk && cfg.beep) MessageBeep(MB_ICONINFORMATION);
}

void PollFiles(const Config& cfg, std::map<std::wstring, FileState>& states)
{
    bool anyOk = false;

    for (const auto& target : cfg.targets) {
        fs::path full = ResolveTarget(g_GameDir, target);
        std::wstring key = full.wstring();

        FileMeta first;
        if (!GetFileMetaW(full, first)) {
            states[key].valid = false;
            continue;
        }

        FileState& state = states[key];
        if (state.valid && SameMeta(state.meta, first)) continue;

        // 等写入稳定：两次采样一致再读，避免读到半截文件
        Sleep(80);
        FileMeta second;
        if (!GetFileMetaW(full, second) || !SameMeta(first, second)) continue;

        ReloadOutcome outcome;
        bool ok = ReloadFile(full, cfg, outcome);
        anyOk = anyOk || ok;

        FileMeta after;
        if (GetFileMetaW(full, after)) {
            state.valid = true;
            state.meta = after;
        } else {
            state.valid = false;
        }
    }

    if (anyOk && cfg.beep) MessageBeep(MB_ICONINFORMATION);
}

DWORD WINAPI MonitorThread(LPVOID)
{
    wchar_t exePath[32768] = {};
    DWORD len = GetModuleFileNameW(nullptr, exePath, static_cast<DWORD>(std::size(exePath)));
    if (len == 0) return 0;
    g_GameDir = fs::path(std::wstring(exePath, len)).parent_path();
    g_ConfigPath = g_GameDir / L"ReloaderConfig.ini";

    std::wstring configError;
    Config cfg = LoadConfig(g_ConfigPath, configError);
    LoggerInit(g_GameDir, cfg.logFile, cfg.logMaxKB);

    LogF("========================================================");
    LogF("[system] AutoReloader v%s", AUTORELOADER_VERSION);
    LogF("[system] game dir: %s", WideToUtf8(g_GameDir.wstring()).c_str());
    LogF("[system] config: %s", WideToUtf8(g_ConfigPath.wstring()).c_str());
    if (!configError.empty()) LogF("[system] config note: %s", WideToUtf8(configError).c_str());

    ToggleConsole(cfg.showConsole);
    DetectExtensions();

    LogF("[config] AutoMonitor=%d HotKey=%d ShowConsole=%d Beep=%d Poll=%dms LiveConvert=%d AutoSyncAE=%d RefreshExisting=%d",
        cfg.autoMonitor, cfg.hotKey, cfg.showConsole, cfg.beep, cfg.pollMs, cfg.liveConvert, cfg.autoSyncAE, cfg.refreshExisting);
    for (const auto& target : cfg.targets) {
        LogF("[config] target: %s", WideToUtf8(target.wstring()).c_str());
    }

    bool engineReady = false;
    bool keyWasDown = false;
    std::map<std::wstring, FileState> states;
    FILETIME configTime = GetWriteTimeW(g_ConfigPath);
    ULONGLONG lastPoll = 0;

    while (!g_Stop.load()) {
        // config hot reload
        FILETIME nowConfig = GetWriteTimeW(g_ConfigPath);
        if (CompareFileTime(&nowConfig, &configTime) != 0) {
            configTime = nowConfig;
            std::wstring error;
            Config next = LoadConfig(g_ConfigPath, error);

            bool targetsChanged = (next.targets.size() != cfg.targets.size());
            if (!targetsChanged) {
                for (size_t i = 0; i < next.targets.size(); ++i) {
                    if (next.targets[i] != cfg.targets[i]) {
                        targetsChanged = true;
                        break;
                    }
                }
            }
            bool consoleChanged = (next.showConsole != cfg.showConsole);
            bool logChanged = (next.logFile != cfg.logFile) || (next.logMaxKB != cfg.logMaxKB);

            cfg = next;
            if (consoleChanged) ToggleConsole(cfg.showConsole);
            if (logChanged) LoggerInit(g_GameDir, cfg.logFile, cfg.logMaxKB);
            if (engineReady && targetsChanged) InitFileStates(cfg, states);
            if (cfg.autoSyncAE && g_typeAECache.empty()
                && HasAEAttach() && g_Extensions.aeDetach) {
                LoadAEBaseline(g_GameDir);
            }

            LogF("[config] reloaded; AutoMonitor=%d HotKey=%d Poll=%dms targets=%zu",
                cfg.autoMonitor, cfg.hotKey, cfg.pollMs, cfg.targets.size());
        }

        if (!engineReady) {
            if (UnitTypeClass::Array.Count > 0) {
                engineReady = true;
                BuildTypeIndex();
                InitFileStates(cfg, states);
                DetectExtensions();
                if (cfg.autoSyncAE && HasAEAttach() && g_Extensions.aeDetach) {
                    LoadAEBaseline(g_GameDir);
                } else if (cfg.autoSyncAE) {
                    LogF("[ae-auto] AutoSyncAttachEffects is enabled but Phobos AE Interop "
                         "(v0.5-alpha1 / Interop 1.1+) is not available; existing-unit AE sync disabled");
                }
                if (cfg.refreshExisting) {
                    EnsureGameThreadDispatcher();
                    LogF("[rebuild] experimental RefreshExistingUnits enabled: "
                         "Infantry/Unit on the map will be rebuilt on reload");
                }
                LogF("[system] engine ready; loaded units=%d", UnitTypeClass::Array.Count);
            } else {
                Sleep(250);
                continue;
            }
        }

        if (CurrentTypeTotal() != g_TypeTotal) {
            BuildTypeIndex();
        }

        bool forced = g_ForceReload.exchange(false);

        bool keyDown = (GetAsyncKeyState(cfg.hotKey) & 0x8000) != 0;
        bool keyPressed = keyDown && !keyWasDown;
        keyWasDown = keyDown;
        if (keyPressed && (!cfg.hotkeyOnlyInGame || IsGameForeground())) {
            ReloadAll(cfg, states, "hotkey");
            lastPoll = GetTickCount64();
            forced = false;
        }

        if (forced) {
            ReloadAll(cfg, states, "external trigger");
            lastPoll = GetTickCount64();
        }

        if (cfg.autoMonitor) {
            ULONGLONG now = GetTickCount64();
            if (now - lastPoll >= static_cast<ULONGLONG>(cfg.pollMs)) {
                lastPoll = now;
                PollFiles(cfg, states);
            }
        }

        Sleep(25);
    }
    UninstallGameThreadDispatcher();
    return 0;
}

} // namespace

// ========================================================
// Exports (optional integration points)
// ========================================================
extern "C" __declspec(dllexport) void __cdecl AutoReloader_TriggerReload()
{
    g_ForceReload.store(true);
}

extern "C" __declspec(dllexport) const char* __cdecl AutoReloader_GetVersion()
{
    return AUTORELOADER_VERSION;
}

// ========================================================
// Entry point
// ========================================================
BOOL APIENTRY DllMain(HMODULE hModule, DWORD reason, LPVOID)
{
    if (reason == DLL_PROCESS_ATTACH) {
        DisableThreadLibraryCalls(hModule);
        CreateThread(nullptr, 0, MonitorThread, nullptr, 0, nullptr);
    }
    else if (reason == DLL_PROCESS_DETACH) {
        g_Stop.store(true);
    }
    return TRUE;
}

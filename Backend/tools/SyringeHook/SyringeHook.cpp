// AutoReloader Syringe hook DLL (experimental, offline only)
//
// Injected into MentalOmegaClient.exe by MOLauncher.exe when
// [Launcher] HookSyringeLaunch=true. It rewrites the command line the client
// passes to Syringe.exe, without editing any MO file.

#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#include <shellapi.h>

#include <algorithm>
#include <cstdio>
#include <cwchar>
#include <string>
#include <vector>

#include "SyringeCompat.h"
#include "MinHook.h"

namespace
{
    using CreateProcessW_t = BOOL(WINAPI*)(LPCWSTR, LPWSTR, LPSECURITY_ATTRIBUTES,
        LPSECURITY_ATTRIBUTES, BOOL, DWORD, LPVOID, LPCWSTR,
        LPSTARTUPINFOW, LPPROCESS_INFORMATION);
    using CreateProcessA_t = BOOL(WINAPI*)(LPCSTR, LPSTR, LPSECURITY_ATTRIBUTES,
        LPSECURITY_ATTRIBUTES, BOOL, DWORD, LPVOID, LPCSTR,
        LPSTARTUPINFOA, LPPROCESS_INFORMATION);
    using ShellExecuteExW_t = BOOL(WINAPI*)(LPSHELLEXECUTEINFOW);
    using ShellExecuteExA_t = BOOL(WINAPI*)(LPSHELLEXECUTEINFOA);
    using ShellExecuteW_t = HINSTANCE(WINAPI*)(HWND, LPCWSTR, LPCWSTR, LPCWSTR, LPCWSTR, INT);
    using ShellExecuteA_t = HINSTANCE(WINAPI*)(HWND, LPCSTR, LPCSTR, LPCSTR, LPCSTR, INT);
    using WinExec_t = UINT(WINAPI*)(LPCSTR, UINT);

    CreateProcessW_t RealCreateProcessW = nullptr;
    CreateProcessA_t RealCreateProcessA = nullptr;
    ShellExecuteExW_t RealShellExecuteExW = nullptr;
    ShellExecuteExA_t RealShellExecuteExA = nullptr;
    ShellExecuteW_t RealShellExecuteW = nullptr;
    ShellExecuteA_t RealShellExecuteA = nullptr;
    WinExec_t RealWinExec = nullptr;

    HANDLE g_readyEvent = nullptr;
    std::wstring g_dir;
    std::wstring g_logPath;

    std::wstring ExeDirectory()
    {
        std::vector<wchar_t> buffer(MAX_PATH);
        for (;;)
        {
            const DWORD len = GetModuleFileNameW(nullptr, buffer.data(),
                                                 static_cast<DWORD>(buffer.size()));
            if (len == 0)
                return L".";
            if (len < buffer.size() - 1)
            {
                std::wstring path(buffer.data(), len);
                const size_t slash = path.find_last_of(L"\\/");
                return slash == std::wstring::npos ? L"." : path.substr(0, slash);
            }
            buffer.resize(buffer.size() * 2);
        }
    }

    void LogLine(const std::wstring& line)
    {
        if (g_logPath.empty())
            return;

        HANDLE file = CreateFileW(g_logPath.c_str(), FILE_APPEND_DATA,
                                  FILE_SHARE_READ | FILE_SHARE_WRITE, nullptr,
                                  OPEN_ALWAYS, FILE_ATTRIBUTE_NORMAL, nullptr);
        if (file == INVALID_HANDLE_VALUE)
            return;

        SYSTEMTIME st{};
        GetLocalTime(&st);
        wchar_t stamp[64]{};
        swprintf_s(stamp, L"[%04u-%02u-%02u %02u:%02u:%02u] ",
                   st.wYear, st.wMonth, st.wDay, st.wHour, st.wMinute, st.wSecond);

        const std::wstring text = std::wstring(stamp) + line + L"\r\n";
        DWORD written = 0;
        WriteFile(file, text.data(), static_cast<DWORD>(text.size() * sizeof(wchar_t)),
                  &written, nullptr);
        CloseHandle(file);
    }

    std::wstring CurrentDirectory()
    {
        std::vector<wchar_t> buffer(MAX_PATH);
        for (;;)
        {
            const DWORD len = GetCurrentDirectoryW(static_cast<DWORD>(buffer.size()), buffer.data());
            if (len == 0)
                return L".";
            if (len < buffer.size())
                return std::wstring(buffer.data(), len);
            buffer.resize(buffer.size() * 2);
        }
    }

    bool EndsWithNoCase(const std::wstring& value, const wchar_t* suffix)
    {
        const size_t suffixLen = wcslen(suffix);
        if (value.size() < suffixLen)
            return false;
        return _wcsicmp(value.c_str() + value.size() - suffixLen, suffix) == 0;
    }

    bool IsSyringeExe(const std::wstring& path)
    {
        return EndsWithNoCase(path, L"Syringe.exe");
    }

    bool IsSyringeExFlag(const std::wstring& arg)
    {
        return arg.rfind(L"-i=", 0) == 0
            || _wcsicmp(arg.c_str(), L"--detach") == 0
            || _wcsicmp(arg.c_str(), L"--nodetach") == 0
            || _wcsicmp(arg.c_str(), L"--nowait") == 0;
    }

    std::wstring ResolvePath(const std::wstring& path, const std::wstring& directory)
    {
        if (path.empty())
            return path;
        if (path.size() >= 2 && path[1] == L':')
            return path;
        if (path.rfind(L"\\\\", 0) == 0)
            return path;

        const std::wstring cwd = directory.empty() ? CurrentDirectory() : directory;
        std::wstring candidate = cwd;
        if (!candidate.empty() && candidate.back() != L'\\' && candidate.back() != L'/')
            candidate.push_back(L'\\');
        candidate += path;

        std::vector<wchar_t> buffer(MAX_PATH);
        for (;;)
        {
            const DWORD len = GetFullPathNameW(candidate.c_str(),
                static_cast<DWORD>(buffer.size()), buffer.data(), nullptr);
            if (len == 0)
                return candidate;
            if (len < buffer.size())
                return std::wstring(buffer.data(), len);
            buffer.resize(buffer.size() * 2);
        }
    }

    bool IsHookHostPath(const std::wstring& path)
    {
        return EndsWithNoCase(path, L"clientdx.exe")
            || EndsWithNoCase(path, L"clientxna.exe")
            || EndsWithNoCase(path, L"clientogl.exe")
            || EndsWithNoCase(path, L"MOLauncher.exe");
    }

    bool InjectDllIntoProcess(HANDLE process, const std::wstring& dllPath)
    {
        const SIZE_T size = (dllPath.size() + 1) * sizeof(wchar_t);
        void* remote = VirtualAllocEx(process, nullptr, size, MEM_COMMIT | MEM_RESERVE, PAGE_READWRITE);
        if (!remote)
        {
            LogLine(L"child inject: VirtualAllocEx failed");
            return false;
        }

        if (!WriteProcessMemory(process, remote, dllPath.c_str(), size, nullptr))
        {
            LogLine(L"child inject: WriteProcessMemory failed");
            VirtualFreeEx(process, remote, 0, MEM_RELEASE);
            return false;
        }

        FARPROC loadLibrary = GetProcAddress(GetModuleHandleW(L"kernel32.dll"), "LoadLibraryW");
        HANDLE thread = CreateRemoteThread(process, nullptr, 0,
            reinterpret_cast<LPTHREAD_START_ROUTINE>(loadLibrary), remote, 0, nullptr);
        if (!thread)
        {
            LogLine(L"child inject: CreateRemoteThread failed");
            VirtualFreeEx(process, remote, 0, MEM_RELEASE);
            return false;
        }

        WaitForSingleObject(thread, 10000);
        DWORD module = 0;
        GetExitCodeThread(thread, &module);
        CloseHandle(thread);
        VirtualFreeEx(process, remote, 0, MEM_RELEASE);

        if (module == 0 || module == STILL_ACTIVE)
        {
            LogLine(L"child inject: LoadLibrary failed");
            return false;
        }

        LogLine(L"child inject: hook DLL injected");
        return true;
    }

    std::vector<std::wstring> ParseArguments(const wchar_t* commandLine)
    {
        std::vector<std::wstring> result;
        if (!commandLine || !*commandLine)
            return result;

        int argc = 0;
        LPWSTR* argv = CommandLineToArgvW(commandLine, &argc);
        if (!argv)
            return result;

        for (int i = 0; i < argc; ++i)
            result.emplace_back(argv[i]);
        LocalFree(argv);
        return result;
    }

    std::wstring BuildArgsFlag(const std::vector<std::wstring>& gameArgs)
    {
        std::wstring blob;
        for (const auto& arg : gameArgs)
        {
            if (!blob.empty())
                blob.push_back(L' ');
            blob += SyringeCompat::Quote(arg);
        }
        return L"--args=\"" + SyringeCompat::EscapeInsideQuotes(blob) + L"\"";
    }

    // Returns true if the command line was rewritten.
    bool RewriteCreateProcessCommand(const std::wstring& applicationName,
                                     const std::wstring& commandLine,
                                     const std::wstring& directory,
                                     std::wstring& rewritten)
    {
        const std::vector<std::wstring> args = ParseArguments(commandLine.c_str());
        if (args.empty())
            return false;

        std::wstring syringe = applicationName;
        std::wstring argv0;
        std::vector<std::wstring> rest;

        if (IsSyringeExe(syringe))
        {
            if (!args.empty() && IsSyringeExe(args[0]))
            {
                argv0 = args[0];
                rest.assign(args.begin() + 1, args.end());
            }
            else
            {
                argv0 = applicationName;
                rest = args;
            }
        }
        else
        {
            if (args.empty() || !IsSyringeExe(args[0]))
                return false;
            argv0 = args[0];
            rest.assign(args.begin() + 1, args.end());
        }

        if (syringe.empty())
            syringe = argv0;

        const std::wstring syringePath = ResolvePath(syringe, directory);
        if (!SyringeCompat::DetectSyringeEx(syringePath))
            return false;

        for (const auto& arg : args)
        {
            if (arg.rfind(L"--args=", 0) == 0)
                return false;
        }

        size_t targetIndex = 0;
        bool targetFound = false;
        for (size_t i = 0; i < rest.size(); ++i)
        {
            if (!rest[i].empty() && rest[i][0] != L'-')
            {
                targetIndex = i;
                targetFound = true;
                break;
            }
        }
        if (!targetFound)
            return false;

        std::vector<std::wstring> syringeFlags;
        std::vector<std::wstring> gameArgs;
        for (size_t i = 0; i < rest.size(); ++i)
        {
            if (i == targetIndex)
                continue;
            if (IsSyringeExFlag(rest[i]))
                syringeFlags.push_back(rest[i]);
            else
                gameArgs.push_back(rest[i]);
        }

        rewritten = SyringeCompat::Quote(argv0) + L" " + SyringeCompat::Quote(rest[targetIndex]);
        for (const auto& flag : syringeFlags)
            rewritten += L" " + SyringeCompat::Quote(flag);
        if (!gameArgs.empty())
            rewritten += L" " + BuildArgsFlag(gameArgs);

        return true;
    }

    std::wstring WideFromAnsi(const char* value)
    {
        if (!value)
            return L"";
        int need = MultiByteToWideChar(CP_ACP, 0, value, -1, nullptr, 0);
        if (need <= 0)
            return L"";
        std::vector<wchar_t> buffer(need);
        MultiByteToWideChar(CP_ACP, 0, value, -1, buffer.data(), need);
        return std::wstring(buffer.data());
    }

    std::string AnsiFromWide(const std::wstring& value)
    {
        int need = WideCharToMultiByte(CP_ACP, 0, value.c_str(), -1, nullptr, 0, nullptr, nullptr);
        if (need <= 0)
            return {};
        std::string buffer(need, '\0');
        WideCharToMultiByte(CP_ACP, 0, value.c_str(), -1, buffer.data(), need, nullptr, nullptr);
        return std::string(buffer.c_str());
    }

    BOOL WINAPI HookCreateProcessW(
        LPCWSTR applicationName, LPWSTR commandLine,
        LPSECURITY_ATTRIBUTES processAttributes, LPSECURITY_ATTRIBUTES threadAttributes,
        BOOL inheritHandles, DWORD creationFlags, LPVOID environment,
        LPCWSTR currentDirectory, LPSTARTUPINFOW startupInfo,
        LPPROCESS_INFORMATION processInformation)
    {
        std::wstring app = applicationName ? applicationName : L"";
        std::wstring cmd = commandLine ? commandLine : L"";
        const std::wstring directory = currentDirectory ? currentDirectory : L"";
        std::wstring rewritten;

        LogLine(L"CreateProcessW app=" + app + L" cmd=" + cmd);

        if (RewriteCreateProcessCommand(app, cmd, directory, rewritten))
        {
            LogLine(L"CreateProcessW rewritten: " + rewritten);
            return RealCreateProcessW(
                applicationName, rewritten.data(), processAttributes, threadAttributes,
                inheritHandles, creationFlags, environment, currentDirectory,
                startupInfo, processInformation);
        }

        return RealCreateProcessW(
            applicationName, commandLine, processAttributes, threadAttributes,
            inheritHandles, creationFlags, environment, currentDirectory,
            startupInfo, processInformation);
    }

    BOOL WINAPI HookCreateProcessA(
        LPCSTR applicationName, LPSTR commandLine,
        LPSECURITY_ATTRIBUTES processAttributes, LPSECURITY_ATTRIBUTES threadAttributes,
        BOOL inheritHandles, DWORD creationFlags, LPVOID environment,
        LPCSTR currentDirectory, LPSTARTUPINFOA startupInfo,
        LPPROCESS_INFORMATION processInformation)
    {
        std::wstring app = WideFromAnsi(applicationName);
        std::wstring cmd = WideFromAnsi(commandLine);
        std::wstring directory = WideFromAnsi(currentDirectory);
        std::wstring rewritten;

        LogLine(L"CreateProcessA app=" + app + L" cmd=" + cmd);

        if (RewriteCreateProcessCommand(app, cmd, directory, rewritten))
        {
            const std::string ansi = AnsiFromWide(rewritten);
            LogLine(L"CreateProcessA rewritten: " + rewritten);
            std::vector<char> buffer(ansi.begin(), ansi.end());
            buffer.push_back('\0');
            return RealCreateProcessA(
                applicationName, buffer.data(), processAttributes, threadAttributes,
                inheritHandles, creationFlags, environment, currentDirectory,
                startupInfo, processInformation);
        }

        return RealCreateProcessA(
            applicationName, commandLine, processAttributes, threadAttributes,
            inheritHandles, creationFlags, environment, currentDirectory,
            startupInfo, processInformation);
    }

    std::wstring RewriteShellParameters(const std::wstring& file,
                                        const std::wstring& parameters,
                                        const std::wstring& directory)
    {
        if (!IsSyringeExe(file))
            return parameters;

        const std::wstring syringePath = ResolvePath(file, directory);
        if (!SyringeCompat::DetectSyringeEx(syringePath))
            return parameters;

        const std::vector<std::wstring> args = ParseArguments(parameters.c_str());
        if (args.empty())
            return parameters;

        for (const auto& arg : args)
        {
            if (arg.rfind(L"--args=", 0) == 0)
                return parameters;
        }

        // ShellExecute parameters usually look like:
        //   "gamemd.exe" -SPAWN -CD ...
        // The first non-flag is the game executable, not a game argument.
        size_t targetIndex = 0;
        bool targetFound = false;
        for (size_t i = 0; i < args.size(); ++i)
        {
            if (!args[i].empty() && args[i][0] != L'-')
            {
                targetIndex = i;
                targetFound = true;
                break;
            }
        }
        if (!targetFound)
            return parameters;

        std::vector<std::wstring> flags;
        std::vector<std::wstring> gameArgs;
        for (size_t i = 0; i < args.size(); ++i)
        {
            if (i == targetIndex)
                continue;
            if (IsSyringeExFlag(args[i]))
                flags.push_back(args[i]);
            else
                gameArgs.push_back(args[i]);
        }

        std::wstring rewritten = SyringeCompat::Quote(args[targetIndex]);
        for (const auto& flag : flags)
            rewritten += L" " + SyringeCompat::Quote(flag);
        if (!gameArgs.empty())
            rewritten += L" " + BuildArgsFlag(gameArgs);
        return rewritten;
    }

    BOOL WINAPI HookShellExecuteExW(LPSHELLEXECUTEINFOW info)
    {
        if (info && info->lpFile)
        {
            const std::wstring directory = info->lpDirectory ? info->lpDirectory : L"";
            const std::wstring parameters = info->lpParameters ? info->lpParameters : L"";
            LogLine(L"ShellExecuteExW file=" + std::wstring(info->lpFile) + L" params=" + parameters);

            if (IsHookHostPath(info->lpFile))
            {
                SHELLEXECUTEINFOW copy = *info;
                copy.fMask |= SEE_MASK_NOCLOSEPROCESS;
                const BOOL ok = RealShellExecuteExW(&copy);
                if (ok && copy.hProcess)
                {
                    InjectDllIntoProcess(copy.hProcess,
                        g_dir + L"\\AutoReloader.SyringeHook.dll");
                    if (info->fMask & SEE_MASK_NOCLOSEPROCESS)
                        info->hProcess = copy.hProcess;
                    else
                        CloseHandle(copy.hProcess);
                }
                return ok;
            }

            const std::wstring rewritten = RewriteShellParameters(info->lpFile, parameters, directory);
            if (rewritten != parameters)
            {
                SHELLEXECUTEINFOW copy = *info;
                copy.lpParameters = rewritten.c_str();
                LogLine(L"ShellExecuteExW rewritten: " + rewritten);
                return RealShellExecuteExW(&copy);
            }
        }
        return RealShellExecuteExW(info);
    }

    BOOL WINAPI HookShellExecuteExA(LPSHELLEXECUTEINFOA info)
    {
        if (info && info->lpFile)
        {
            const std::wstring file = WideFromAnsi(info->lpFile);
            const std::wstring parameters = WideFromAnsi(info->lpParameters);
            const std::wstring directory = WideFromAnsi(info->lpDirectory);
            const std::wstring rewritten = RewriteShellParameters(file, parameters, directory);
            if (rewritten != parameters)
            {
                const std::string ansi = AnsiFromWide(rewritten);
                SHELLEXECUTEINFOA copy = *info;
                copy.lpParameters = const_cast<char*>(ansi.c_str());
                LogLine(L"ShellExecuteExA rewritten: " + rewritten);
                return RealShellExecuteExA(&copy);
            }
        }
        return RealShellExecuteExA(info);
    }

    HINSTANCE WINAPI HookShellExecuteW(HWND window, LPCWSTR operation, LPCWSTR file,
                                       LPCWSTR parameters, LPCWSTR directory, INT show)
    {
        const std::wstring fileValue = file ? file : L"";
        const std::wstring parametersValue = parameters ? parameters : L"";
        const std::wstring directoryValue = directory ? directory : L"";
        LogLine(L"ShellExecuteW file=" + fileValue + L" params=" + parametersValue);

        if (IsHookHostPath(fileValue))
        {
            SHELLEXECUTEINFOW info{};
            info.cbSize = sizeof(info);
            info.fMask = SEE_MASK_NOCLOSEPROCESS;
            info.lpVerb = operation;
            info.lpFile = file;
            info.lpParameters = parameters;
            info.lpDirectory = directory;
            info.nShow = show;
            const BOOL ok = RealShellExecuteExW(&info);
            if (ok && info.hProcess)
            {
                InjectDllIntoProcess(info.hProcess,
                    g_dir + L"\\AutoReloader.SyringeHook.dll");
                CloseHandle(info.hProcess);
            }
            return ok ? reinterpret_cast<HINSTANCE>(33) : reinterpret_cast<HINSTANCE>(2);
        }

        const std::wstring rewritten = RewriteShellParameters(fileValue, parametersValue, directoryValue);
        if (rewritten != parametersValue)
        {
            LogLine(L"ShellExecuteW rewritten: " + rewritten);
            return RealShellExecuteW(window, operation, file, rewritten.c_str(),
                                     directory, show);
        }
        return RealShellExecuteW(window, operation, file, parameters, directory, show);
    }

    HINSTANCE WINAPI HookShellExecuteA(HWND window, LPCSTR operation, LPCSTR file,
                                       LPCSTR parameters, LPCSTR directory, INT show)
    {
        const std::wstring fileValue = WideFromAnsi(file);
        const std::wstring parametersValue = WideFromAnsi(parameters);
        const std::wstring directoryValue = WideFromAnsi(directory);
        const std::wstring rewritten = RewriteShellParameters(fileValue, parametersValue, directoryValue);
        if (rewritten != parametersValue)
        {
            const std::string ansi = AnsiFromWide(rewritten);
            LogLine(L"ShellExecuteA rewritten: " + rewritten);
            return RealShellExecuteA(window, operation, file, ansi.c_str(),
                                     directory, show);
        }
        return RealShellExecuteA(window, operation, file, parameters, directory, show);
    }

    UINT WINAPI HookWinExec(LPCSTR commandLine, UINT show)
    {
        const std::wstring cmd = WideFromAnsi(commandLine);
        std::wstring rewritten;
        if (RewriteCreateProcessCommand(L"", cmd, L"", rewritten))
        {
            const std::string ansi = AnsiFromWide(rewritten);
            LogLine(L"WinExec rewritten: " + rewritten);
            return RealWinExec(ansi.c_str(), show);
        }
        return RealWinExec(commandLine, show);
    }

    void InstallHooks()
    {
        LogLine(L"installing hooks");
        if (MH_Initialize() != MH_OK)
        {
            LogLine(L"MH_Initialize failed");
            if (g_readyEvent) SetEvent(g_readyEvent);
            return;
        }

        LoadLibraryW(L"shell32.dll");

        const auto install = [](const wchar_t* module, const char* name,
                                LPVOID detour, LPVOID* original)
        {
            const MH_STATUS status = MH_CreateHookApi(module, name, detour, original);
            wchar_t buffer[256]{};
            swprintf_s(buffer, L"hook %s!%S status=%d", module, name,
                       static_cast<int>(status));
            LogLine(buffer);
        };

        install(L"kernel32.dll", "CreateProcessW",
                reinterpret_cast<LPVOID>(&HookCreateProcessW),
                reinterpret_cast<LPVOID*>(&RealCreateProcessW));
        install(L"kernel32.dll", "CreateProcessA",
                reinterpret_cast<LPVOID>(&HookCreateProcessA),
                reinterpret_cast<LPVOID*>(&RealCreateProcessA));
        install(L"shell32.dll", "ShellExecuteExW",
                reinterpret_cast<LPVOID>(&HookShellExecuteExW),
                reinterpret_cast<LPVOID*>(&RealShellExecuteExW));
        install(L"shell32.dll", "ShellExecuteExA",
                reinterpret_cast<LPVOID>(&HookShellExecuteExA),
                reinterpret_cast<LPVOID*>(&RealShellExecuteExA));
        install(L"shell32.dll", "ShellExecuteW",
                reinterpret_cast<LPVOID>(&HookShellExecuteW),
                reinterpret_cast<LPVOID*>(&RealShellExecuteW));
        install(L"shell32.dll", "ShellExecuteA",
                reinterpret_cast<LPVOID>(&HookShellExecuteA),
                reinterpret_cast<LPVOID*>(&RealShellExecuteA));
        install(L"kernel32.dll", "WinExec",
                reinterpret_cast<LPVOID>(&HookWinExec),
                reinterpret_cast<LPVOID*>(&RealWinExec));

        const MH_STATUS status = MH_EnableHook(MH_ALL_HOOKS);
        LogLine(L"MH_EnableHook status=" + std::to_wstring(status));
        if (g_readyEvent) SetEvent(g_readyEvent);
    }

    DWORD WINAPI InstallThread(LPVOID)
    {
        InstallHooks();
        return 0;
    }
}

BOOL APIENTRY DllMain(HMODULE module, DWORD reason, LPVOID)
{
    if (reason == DLL_PROCESS_ATTACH)
    {
        DisableThreadLibraryCalls(module);
        g_dir = ExeDirectory();
        g_logPath = g_dir + L"\\SyringeHook_Log.txt";
        g_readyEvent = OpenEventW(EVENT_MODIFY_STATE, FALSE, AUTORELOADER_HOOK_READY_EVENT);
        LogLine(L"hook DLL attached");
        CreateThread(nullptr, 0, InstallThread, nullptr, 0, nullptr);
    }
    return TRUE;
}

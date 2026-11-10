// AutoReloader Syringe shim
//
// MO's launcher invokes:  Syringe.exe gamemd.exe -SPAWN -CD ...
// Old Syringe passes everything after the exe to the game.
// SyringeEx (Phobos 0.5+) requires:  Syringe.exe gamemd.exe --args="-SPAWN -CD ..."
//
// This shim is installed AS Syringe.exe. It detects which real loader is present
// (SyringeEx.exe for new, SyringeLegacy.exe for old) and translates the command
// line without touching MOLauncher.exe, gamemd.exe or any MO file.

#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#include <shellapi.h>

#include <cstdio>
#include <iterator>
#include <string>
#include <vector>

namespace
{
    std::wstring g_dir;
    std::wstring g_logPath;

    bool FileExists(const std::wstring& path)
    {
        const DWORD attrs = GetFileAttributesW(path.c_str());
        return attrs != INVALID_FILE_ATTRIBUTES && !(attrs & FILE_ATTRIBUTE_DIRECTORY);
    }

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
        const DWORD bytes = static_cast<DWORD>(text.size() * sizeof(wchar_t));
        DWORD written = 0;
        WriteFile(file, text.data(), bytes, &written, nullptr);
        CloseHandle(file);
    }

    // Quote one token for a Windows command line.
    std::wstring Quote(const std::wstring& value)
    {
        if (value.empty())
            return L"\"\"";

        if (value.find_first_of(L" \t\n\v\"") == std::wstring::npos)
            return value;

        std::wstring out;
        out.push_back(L'"');
        size_t backslashes = 0;
        for (const wchar_t ch : value)
        {
            if (ch == L'\\')
            {
                ++backslashes;
            }
            else if (ch == L'"')
            {
                out.append(backslashes * 2 + 1, L'\\');
                out.push_back(L'"');
                backslashes = 0;
            }
            else
            {
                out.append(backslashes, L'\\');
                backslashes = 0;
                out.push_back(ch);
            }
        }
        out.append(backslashes * 2, L'\\');
        out.push_back(L'"');
        return out;
    }

    // Escape a value that will sit inside an outer pair of quotes.
    std::wstring EscapeInsideQuotes(const std::wstring& value)
    {
        std::wstring out;
        size_t backslashes = 0;
        for (const wchar_t ch : value)
        {
            if (ch == L'\\')
            {
                ++backslashes;
            }
            else if (ch == L'"')
            {
                out.append(backslashes * 2 + 1, L'\\');
                out.push_back(L'"');
                backslashes = 0;
            }
            else
            {
                out.append(backslashes, L'\\');
                backslashes = 0;
                out.push_back(ch);
            }
        }
        out.append(backslashes * 2, L'\\');
        return out;
    }

    std::vector<std::wstring> GetArguments()
    {
        int argc = 0;
        LPWSTR* argv = CommandLineToArgvW(GetCommandLineW(), &argc);
        std::vector<std::wstring> result;
        if (!argv)
            return result;

        for (int i = 1; i < argc; ++i)
            result.emplace_back(argv[i]);

        LocalFree(argv);
        return result;
    }

    bool StartsWith(const std::wstring& value, const wchar_t* prefix)
    {
        return value.rfind(prefix, 0) == 0;
    }

    bool IsSyringeExFlag(const std::wstring& arg)
    {
        return StartsWith(arg, L"-i=")
            || _wcsicmp(arg.c_str(), L"--detach") == 0
            || _wcsicmp(arg.c_str(), L"--nodetach") == 0
            || _wcsicmp(arg.c_str(), L"--nowait") == 0;
    }

    enum class LoaderKind
    {
        None,
        SyringeEx,
        Legacy,
    };

    struct LoaderChoice
    {
        LoaderKind kind = LoaderKind::None;
        std::wstring path;
    };

    std::wstring IniValue(const wchar_t* section, const wchar_t* key, const wchar_t* fallback)
    {
        wchar_t buffer[128]{};
        GetPrivateProfileStringW(section, key, fallback, buffer,
                                 static_cast<DWORD>(std::size(buffer)),
                                 (g_dir + L"\\SyringeShim.ini").c_str());
        return buffer;
    }

    LoaderChoice FindLoader()
    {
        const std::wstring use = IniValue(L"Loader", L"Use", L"auto");
        const std::wstring ex = g_dir + L"\\SyringeEx.exe";
        const std::wstring legacy1 = g_dir + L"\\SyringeLegacy.exe";
        const std::wstring legacy2 = g_dir + L"\\SyringeOld.exe";

        const bool hasEx = FileExists(ex);
        const bool hasLegacy = FileExists(legacy1) || FileExists(legacy2);
        const std::wstring legacy = FileExists(legacy1) ? legacy1 : legacy2;

        if (_wcsicmp(use.c_str(), L"ex") == 0 || _wcsicmp(use.c_str(), L"new") == 0)
        {
            if (hasEx)
                return { LoaderKind::SyringeEx, ex };
            return {};
        }
        if (_wcsicmp(use.c_str(), L"legacy") == 0 || _wcsicmp(use.c_str(), L"old") == 0)
        {
            if (hasLegacy)
                return { LoaderKind::Legacy, legacy };
            return {};
        }

        if (hasEx)
            return { LoaderKind::SyringeEx, ex };
        if (hasLegacy)
            return { LoaderKind::Legacy, legacy };
        return {};
    }

    std::wstring BuildArgsFlag(const std::vector<std::wstring>& gameArgs)
    {
        std::wstring blob;
        for (const auto& arg : gameArgs)
        {
            if (!blob.empty())
                blob.push_back(L' ');
            blob += Quote(arg);
        }
        return L"--args=\"" + EscapeInsideQuotes(blob) + L"\"";
    }

    std::wstring BuildNewCommand(const std::wstring& loader,
                                 const std::vector<std::wstring>& args)
    {
        for (const auto& arg : args)
        {
            // Already in SyringeEx syntax: pass through untouched.
            if (StartsWith(arg, L"--args="))
            {
                std::wstring command = Quote(loader);
                for (const auto& item : args)
                    command += L" " + Quote(item);
                return command;
            }
        }

        std::wstring target;
        std::vector<std::wstring> syringeFlags;
        std::vector<std::wstring> gameArgs;

        for (const auto& arg : args)
        {
            if (target.empty() && !StartsWith(arg, L"-"))
            {
                target = arg;
                continue;
            }
            if (IsSyringeExFlag(arg))
                syringeFlags.push_back(arg);
            else
                gameArgs.push_back(arg);
        }

        std::wstring command = Quote(loader);
        if (!target.empty())
            command += L" " + Quote(target);
        for (const auto& flag : syringeFlags)
            command += L" " + Quote(flag);
        if (!gameArgs.empty())
            command += L" " + BuildArgsFlag(gameArgs);
        return command;
    }

    std::wstring BuildLegacyCommand(const std::wstring& loader,
                                    const std::vector<std::wstring>& args)
    {
        std::wstring command = Quote(loader);
        for (const auto& arg : args)
            command += L" " + Quote(arg);
        return command;
    }

    int ShowError(const std::wstring& message)
    {
        LogLine(L"ERROR: " + message);
        MessageBoxW(nullptr, message.c_str(), L"AutoReloader Syringe Shim",
                    MB_OK | MB_ICONERROR);
        return 2;
    }
}

int WINAPI wWinMain(HINSTANCE, HINSTANCE, PWSTR, int)
{
    g_dir = ExeDirectory();
    g_logPath = g_dir + L"\\SyringeShim.log";
    SetCurrentDirectoryW(g_dir.c_str());

    LogLine(L"---- start ----");
    LogLine(L"command line: " + std::wstring(GetCommandLineW()));

    const std::vector<std::wstring> args = GetArguments();
    if (args.empty())
        return ShowError(L"Syringe was started without a target executable.\n\n"
                         L"Usage: Syringe.exe <game.exe> <game arguments>");

    const LoaderChoice loader = FindLoader();
    if (loader.kind == LoaderKind::None)
    {
        return ShowError(
            L"No real Syringe loader found next to Syringe.exe.\n\n"
            L"Install one of:\n"
            L"  SyringeEx.exe      - Phobos 0.5+ (SyringeEx)\n"
            L"  SyringeLegacy.exe  - old Syringe (Ares / Phobos 0.4)\n\n"
            L"Rename the bundled Syringe.exe to one of those names, then put\n"
            L"AutoReloader.SyringeShim.exe here as Syringe.exe.");
    }

    const std::wstring command = loader.kind == LoaderKind::SyringeEx
        ? BuildNewCommand(loader.path, args)
        : BuildLegacyCommand(loader.path, args);

    LogLine(L"loader: " + loader.path);
    LogLine(L"launch: " + command);

    std::vector<wchar_t> mutableCommand(command.begin(), command.end());
    mutableCommand.push_back(L'\0');

    STARTUPINFOW startup{};
    startup.cb = sizeof(startup);
    PROCESS_INFORMATION process{};

    if (!CreateProcessW(nullptr, mutableCommand.data(), nullptr, nullptr, FALSE,
                        CREATE_NO_WINDOW, nullptr, g_dir.c_str(), &startup, &process))
    {
        const DWORD error = GetLastError();
        wchar_t buffer[256]{};
        swprintf_s(buffer, L"CreateProcess failed: %lu\n\n%s", error, command.c_str());
        return ShowError(buffer);
    }

    WaitForSingleObject(process.hProcess, INFINITE);

    DWORD exitCode = 0;
    GetExitCodeProcess(process.hProcess, &exitCode);
    CloseHandle(process.hThread);
    CloseHandle(process.hProcess);

    LogLine(L"exit code: " + std::to_wstring(exitCode));
    return static_cast<int>(exitCode);
}

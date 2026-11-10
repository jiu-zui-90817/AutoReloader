/**
 * AutoReloader.SyringeLauncher
 *
 * Config-only compatibility wrapper for the MO CnCNet client.
 *
 * Point this file in Resources\ClientDefinitions.ini:
 *   GameLauncherExecutableName=AutoReloader.SyringeLauncher.exe
 *
 * The client then calls:
 *   AutoReloader.SyringeLauncher.exe gamemd.exe -SPAWN -CD ...
 *
 * This wrapper launches:
 *   Syringe.exe gamemd.exe --args="-SPAWN -CD ..."   (SyringeEx)
 *   Syringe.exe gamemd.exe -SPAWN -CD ...            (old Syringe)
 *
 * No injection, no file replacement.
 */

#include <windows.h>
#include <shellapi.h>

#include <string>
#include <vector>

#include "SyringeCompat.h"

namespace
{
    void WriteLog(const std::wstring& line)
    {
        HANDLE file = CreateFileW(L"SyringeLauncher_Log.txt", FILE_APPEND_DATA,
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

    std::wstring ModuleDirectory()
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

    std::wstring JoinQuoted(const std::vector<std::wstring>& args, size_t first)
    {
        std::wstring result;
        for (size_t i = first; i < args.size(); ++i)
        {
            if (!result.empty())
                result.push_back(L' ');
            result += SyringeCompat::Quote(args[i]);
        }
        return result;
    }
}

int WINAPI wWinMain(HINSTANCE, HINSTANCE, LPWSTR, int)
{
    const std::wstring directory = ModuleDirectory();
    const std::wstring syringePath = directory + L"\\Syringe.exe";

    int argc = 0;
    LPWSTR* argv = CommandLineToArgvW(GetCommandLineW(), &argc);
    std::vector<std::wstring> args;
    if (argv)
    {
        for (int i = 0; i < argc; ++i)
            args.emplace_back(argv[i]);
        LocalFree(argv);
    }

    std::wstring gameExe = L"gamemd.exe";
    size_t firstGameArg = 1;
    for (size_t i = 1; i < args.size(); ++i)
    {
        if (!args[i].empty() && args[i][0] != L'-')
        {
            gameExe = args[i];
            firstGameArg = i + 1;
            break;
        }
    }

    if (GetFileAttributesW(syringePath.c_str()) == INVALID_FILE_ATTRIBUTES)
    {
        WriteLog(L"Syringe.exe not found: " + syringePath);
        return 1;
    }

    const bool syringeEx = SyringeCompat::DetectSyringeEx(syringePath);
    std::wstring command = SyringeCompat::Quote(syringePath) + L" "
                         + SyringeCompat::Quote(gameExe);

    const std::wstring gameArgs = JoinQuoted(args, firstGameArg);
    if (syringeEx)
    {
        command += L" --args=\"" + SyringeCompat::EscapeInsideQuotes(gameArgs) + L"\"";
    }
    else if (!gameArgs.empty())
    {
        command += L" " + gameArgs;
    }

    WriteLog(L"syringeEx=" + std::to_wstring(syringeEx ? 1 : 0));
    WriteLog(L"cmd=" + command);

    std::vector<wchar_t> buffer(command.begin(), command.end());
    buffer.push_back(L'\0');

    STARTUPINFOW startup{};
    startup.cb = sizeof(startup);
    startup.dwFlags = STARTF_USESHOWWINDOW;
    startup.wShowWindow = SW_SHOWNORMAL;

    PROCESS_INFORMATION process{};
    if (!CreateProcessW(syringePath.c_str(), buffer.data(), nullptr, nullptr, FALSE,
                        0, nullptr, directory.c_str(), &startup, &process))
    {
        WriteLog(L"CreateProcess failed: " + std::to_wstring(GetLastError()));
        return 1;
    }

    WaitForSingleObject(process.hProcess, INFINITE);
    DWORD exitCode = 1;
    GetExitCodeProcess(process.hProcess, &exitCode);
    CloseHandle(process.hThread);
    CloseHandle(process.hProcess);

    WriteLog(L"exit=" + std::to_wstring(exitCode));
    return static_cast<int>(exitCode);
}

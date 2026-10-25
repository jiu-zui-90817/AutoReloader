/**
 * Tools 顶层壳程序（无控制台）。
 * 与真实 Nuitka/PyInstaller 产物同名，启动 _internal\<同名.exe>。
 * 工作目录为 Tools（配置/图标在顶层）；DLL 仍由 _internal 内真 exe 解析。
 */
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdio.h>

#pragma comment(linker, "/SUBSYSTEM:WINDOWS")

static void ShowErr(const wchar_t* msg) {
    MessageBoxW(NULL, msg, L"AutoReloader", MB_OK | MB_ICONERROR);
}

static int Launch(const wchar_t* toolsDir, const wchar_t* targetExe) {
    wchar_t cmd[32768];
    if (_snwprintf_s(cmd, _TRUNCATE, L"\"%s\"", targetExe) < 0) {
        ShowErr(L"Command line too long.");
        return 1;
    }

    STARTUPINFOW si;
    ZeroMemory(&si, sizeof(si));
    si.cb = sizeof(si);
    PROCESS_INFORMATION pi;
    ZeroMemory(&pi, sizeof(pi));

    BOOL ok = CreateProcessW(
        targetExe,
        cmd,
        NULL,
        NULL,
        FALSE,
        0,
        NULL,
        toolsDir,
        &si,
        &pi);
    if (!ok) {
        wchar_t buf[512];
        _snwprintf_s(
            buf,
            _TRUNCATE,
            L"无法启动：\n%s\n\n错误码 %lu",
            targetExe,
            GetLastError());
        ShowErr(buf);
        return 1;
    }
    CloseHandle(pi.hThread);
    CloseHandle(pi.hProcess);
    return 0;
}

static int Exists(const wchar_t* path) {
    DWORD a = GetFileAttributesW(path);
    return (a != INVALID_FILE_ATTRIBUTES) && !(a & FILE_ATTRIBUTE_DIRECTORY);
}

int WINAPI wWinMain(HINSTANCE, HINSTANCE, PWSTR, int) {
    wchar_t self[MAX_PATH];
    if (!GetModuleFileNameW(NULL, self, MAX_PATH)) {
        ShowErr(L"GetModuleFileName failed.");
        return 1;
    }

    wchar_t toolsDir[MAX_PATH];
    wchar_t baseName[MAX_PATH];
    wcsncpy_s(toolsDir, self, _TRUNCATE);
    wchar_t* slash = wcsrchr(toolsDir, L'\\');
    if (!slash) {
        ShowErr(L"Invalid module path.");
        return 1;
    }
    wcsncpy_s(baseName, slash + 1, _TRUNCATE);
    *slash = L'\0';

    wchar_t target[MAX_PATH];
    _snwprintf_s(target, _TRUNCATE, L"%s\\_internal\\%s", toolsDir, baseName);
    if (Exists(target)) {
        return Launch(toolsDir, target);
    }

    const wchar_t* alt = NULL;
    if (wcsstr(baseName, L"编辑") != NULL || wcsstr(baseName, L"INI") != NULL) {
        alt = L"INIEditor.exe";
    } else if (wcsstr(baseName, L"工坊") != NULL || wcsstr(baseName, L"Workshop") != NULL) {
        alt = L"Workshop.exe";
    }
    if (alt) {
        _snwprintf_s(target, _TRUNCATE, L"%s\\_internal\\%s", toolsDir, alt);
        if (Exists(target)) {
            return Launch(toolsDir, target);
        }
    }

    wchar_t buf[768];
    _snwprintf_s(
        buf,
        _TRUNCATE,
        L"找不到程序：\n%s\\_internal\\%s\n\n请保持 Tools 目录完整。",
        toolsDir,
        baseName);
    ShowErr(buf);
    return 1;
}

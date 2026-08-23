/**
 * =========================================================================================
 * 项目名称: AutoReloader - YR/Ares 独立可视化启动器
 * =========================================================================================
 */

#include <windows.h>
#include <shellapi.h>
#include <tlhelp32.h>
#include <string>

 // 启用现代 Windows 视觉样式
#pragma comment(linker,"\"/manifestdependency:type='win32' \
name='Microsoft.Windows.Common-Controls' version='6.0.0.0' \
processorArchitecture='*' publicKeyToken='6595b64144ccf1df' language='*'\"")

#define ID_RADIO_WIN   101
#define ID_RADIO_FULL  102
#define ID_RADIO_ARES  103
#define ID_BTN_LAUNCH  104

HWND hRadioWin, hRadioFull, hRadioAres, hBtnLaunch, hLblStatus;


// ==========================================
// UAC：清单 requireAdministrator + 运行时兜底提权
// ==========================================
static bool IsRunAsAdmin()
{
    BOOL isAdmin = FALSE;
    PSID adminGroup = NULL;
    SID_IDENTIFIER_AUTHORITY ntAuth = SECURITY_NT_AUTHORITY;
    if (AllocateAndInitializeSid(&ntAuth, 2, SECURITY_BUILTIN_DOMAIN_RID,
            DOMAIN_ALIAS_RID_ADMINS, 0, 0, 0, 0, 0, 0, &adminGroup))
    {
        CheckTokenMembership(NULL, adminGroup, &isAdmin);
        FreeSid(adminGroup);
    }
    return isAdmin == TRUE;
}

// 若当前不是管理员：用 runas 重启自身并退出（清单失效时的兜底）
static void EnsureAdminOrRelaunch()
{
    if (IsRunAsAdmin())
        return;

    wchar_t path[MAX_PATH];
    if (!GetModuleFileNameW(NULL, path, MAX_PATH))
        return;

    SHELLEXECUTEINFOW sei = {};
    sei.cbSize = sizeof(sei);
    sei.lpVerb = L"runas";
    sei.lpFile = path;
    sei.nShow = SW_SHOWNORMAL;
    if (ShellExecuteExW(&sei))
    {
        // 已请求提升，当前进程退出
        ExitProcess(0);
    }
    // 用户拒绝 UAC 等：继续跑（注入可能失败），写日志由调用方处理
}

// ==========================================
// 辅助函数
// ==========================================
bool EnableDebugPrivilege() {
    HANDLE hToken;
    LUID luid;
    TOKEN_PRIVILEGES tkp;
    if (!OpenProcessToken(GetCurrentProcess(), TOKEN_ADJUST_PRIVILEGES | TOKEN_QUERY, &hToken)) return false;
    if (!LookupPrivilegeValue(NULL, SE_DEBUG_NAME, &luid)) { CloseHandle(hToken); return false; }
    tkp.PrivilegeCount = 1;
    tkp.Privileges[0].Luid = luid;
    tkp.Privileges[0].Attributes = SE_PRIVILEGE_ENABLED;
    bool result = AdjustTokenPrivileges(hToken, FALSE, &tkp, sizeof(tkp), NULL, NULL);
    CloseHandle(hToken);
    return result;
}

DWORD GetProcessIdByName(const wchar_t* processName) {
    PROCESSENTRY32W pe32;
    pe32.dwSize = sizeof(PROCESSENTRY32W);
    HANDLE hSnapshot = CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0);
    if (hSnapshot == INVALID_HANDLE_VALUE) return 0;
    if (Process32FirstW(hSnapshot, &pe32)) {
        do {
            if (wcscmp(pe32.szExeFile, processName) == 0) {
                CloseHandle(hSnapshot);
                return pe32.th32ProcessID;
            }
        } while (Process32NextW(hSnapshot, &pe32));
    }
    CloseHandle(hSnapshot);
    return 0;
}

void SetStatusText(const wchar_t* text) {
    SetWindowTextW(hLblStatus, text);
}

// ==========================================
// 核心后台线程
// ==========================================
DWORD WINAPI LaunchThread(LPVOID lpParam) {
    int mode = (int)(INT_PTR)lpParam;

    EnableWindow(hBtnLaunch, FALSE);
    EnableWindow(hRadioWin, FALSE);
    EnableWindow(hRadioFull, FALSE);
    EnableWindow(hRadioAres, FALSE);

    EnableDebugPrivilege();

    // 1. 获取并锁定工作目录
    wchar_t currentDir[MAX_PATH];
    GetModuleFileNameW(NULL, currentDir, MAX_PATH);
    wchar_t* lastSlash = wcsrchr(currentDir, L'\\');
    if (lastSlash) *lastSlash = L'\0';

    // 2. INI 劫持：动态修改 ddraw.ini
    wchar_t iniPath[MAX_PATH];
    wcscpy_s(iniPath, MAX_PATH, currentDir);
    wcscat_s(iniPath, MAX_PATH, L"\\ddraw.ini");

    if (mode == 1) { // 窗口模式
        WritePrivateProfileStringW(L"ddraw", L"windowed", L"true", iniPath);
    }
    else if (mode == 2 || mode == 3) { // 全屏模式 或 纯净模式
        WritePrivateProfileStringW(L"ddraw", L"windowed", L"false", iniPath);
    }

    SetStatusText(L"状态: 正在呼叫 Syringe 启动引擎...");

    // 3. 统一使用纯净的启动参数
    wchar_t cmdArgs[] = L"Syringe.exe \"gamemd.exe\" -nospawn";

    STARTUPINFOW si = { sizeof(si) };
    PROCESS_INFORMATION pi;

    if (!CreateProcessW(NULL, cmdArgs, NULL, NULL, FALSE, 0, NULL, currentDir, &si, &pi)) {
        SetStatusText(L"状态: [错误] 找不到 Syringe.exe！请放在游戏根目录。");
        EnableWindow(hBtnLaunch, TRUE);
        return 1;
    }
    CloseHandle(pi.hThread);
    CloseHandle(pi.hProcess);

    if (mode == 3) {
        SetStatusText(L"状态: 纯净 Ares 已启动！");
        Sleep(2000);
        PostQuitMessage(0);
        return 0;
    }

    SetStatusText(L"状态: 正在侦测 gamemd.exe...");
    DWORD processId = 0;
    while (true) {
        processId = GetProcessIdByName(L"gamemd.exe");
        if (processId != 0) break;
        Sleep(1000);
    }

    SetStatusText(L"状态: 等待引擎内存展开 (3秒)...");
    Sleep(3000);

    SetStatusText(L"状态: 正在挂载AutoReloader核心...");
    wchar_t dllPath[MAX_PATH];
    wcscpy_s(dllPath, MAX_PATH, currentDir);
    wcscat_s(dllPath, MAX_PATH, L"\\AutoReloader.dll");

    HANDLE hProcess = OpenProcess(PROCESS_CREATE_THREAD | PROCESS_QUERY_INFORMATION | PROCESS_VM_OPERATION | PROCESS_VM_WRITE | PROCESS_VM_READ, FALSE, processId);
    if (!hProcess) {
        SetStatusText(L"状态: [致命错误] 无法获取进程操作权限！");
        EnableWindow(hBtnLaunch, TRUE);
        return 1;
    }

    void* pAlloc = VirtualAllocEx(hProcess, NULL, sizeof(dllPath), MEM_COMMIT | MEM_RESERVE, PAGE_READWRITE);
    if (pAlloc) {
        WriteProcessMemory(hProcess, pAlloc, dllPath, sizeof(dllPath), NULL);
        HMODULE hKernel32 = GetModuleHandleW(L"kernel32.dll");
        FARPROC loadLibraryAddr = GetProcAddress(hKernel32, "LoadLibraryW");
        HANDLE hThread = CreateRemoteThread(hProcess, NULL, 0, (LPTHREAD_START_ROUTINE)loadLibraryAddr, pAlloc, 0, NULL);

        if (hThread) {
            SetStatusText(L"状态: [成功] 热重载核心已挂载！");
            CloseHandle(hThread);
            Sleep(2000);
            PostQuitMessage(0);
        }
        else {
            SetStatusText(L"状态: [错误] 远程线程创建失败！");
        }
    }
    CloseHandle(hProcess);
    EnableWindow(hBtnLaunch, TRUE);
    return 0;
}

// ==========================================
// 窗口绘制过程
// ==========================================
LRESULT CALLBACK WndProc(HWND hwnd, UINT msg, WPARAM wParam, LPARAM lParam) {
    switch (msg) {
    case WM_CREATE: {
        HFONT hFont = (HFONT)GetStockObject(DEFAULT_GUI_FONT);

        HWND hLblTitle = CreateWindowW(L"STATIC", L"AutoReloader - YR引导程序",
            WS_VISIBLE | WS_CHILD | SS_CENTER, 10, 15, 310, 20, hwnd, NULL, NULL, NULL);
        SendMessage(hLblTitle, WM_SETFONT, (WPARAM)hFont, TRUE);

        HWND hGroup = CreateWindowW(L"BUTTON", L"启动模式选择",
            WS_VISIBLE | WS_CHILD | BS_GROUPBOX, 20, 45, 300, 110, hwnd, NULL, NULL, NULL);
        SendMessage(hGroup, WM_SETFONT, (WPARAM)hFont, TRUE);

        hRadioWin = CreateWindowW(L"BUTTON", L"1. 窗口模式 + 挂载核心 (推荐)",
            WS_VISIBLE | WS_CHILD | BS_AUTORADIOBUTTON | WS_GROUP, 35, 70, 260, 20, hwnd, (HMENU)ID_RADIO_WIN, NULL, NULL);
        SendMessage(hRadioWin, WM_SETFONT, (WPARAM)hFont, TRUE);
        SendMessage(hRadioWin, BM_SETCHECK, BST_CHECKED, 0);

        hRadioFull = CreateWindowW(L"BUTTON", L"2. 全屏模式 + 挂载核心",
            WS_VISIBLE | WS_CHILD | BS_AUTORADIOBUTTON, 35, 95, 260, 20, hwnd, (HMENU)ID_RADIO_FULL, NULL, NULL);
        SendMessage(hRadioFull, WM_SETFONT, (WPARAM)hFont, TRUE);

        hRadioAres = CreateWindowW(L"BUTTON", L"3. 仅启动纯净 ARES (不挂载)",
            WS_VISIBLE | WS_CHILD | BS_AUTORADIOBUTTON, 35, 120, 260, 20, hwnd, (HMENU)ID_RADIO_ARES, NULL, NULL);
        SendMessage(hRadioAres, WM_SETFONT, (WPARAM)hFont, TRUE);

        hLblStatus = CreateWindowW(L"STATIC", L"状态: 等待启动...",
            WS_VISIBLE | WS_CHILD, 20, 170, 290, 20, hwnd, NULL, NULL, NULL);
        SendMessage(hLblStatus, WM_SETFONT, (WPARAM)hFont, TRUE);

        hBtnLaunch = CreateWindowW(L"BUTTON", L"🚀 启动引擎",
            WS_VISIBLE | WS_CHILD | BS_PUSHBUTTON, 115, 200, 100, 35, hwnd, (HMENU)ID_BTN_LAUNCH, NULL, NULL);
        SendMessage(hBtnLaunch, WM_SETFONT, (WPARAM)hFont, TRUE);
        break;
    }
    case WM_COMMAND: {
        if (LOWORD(wParam) == ID_BTN_LAUNCH) {
            int mode = 1;
            if (SendMessage(hRadioFull, BM_GETCHECK, 0, 0) == BST_CHECKED) mode = 2;
            if (SendMessage(hRadioAres, BM_GETCHECK, 0, 0) == BST_CHECKED) mode = 3;
            CreateThread(NULL, 0, LaunchThread, (LPVOID)(INT_PTR)mode, 0, NULL);
        }
        break;
    }
    case WM_DESTROY:
        PostQuitMessage(0);
        break;
    default:
        return DefWindowProc(hwnd, msg, wParam, lParam);
    }
    return 0;
}

// ==========================================
// 主程序入口
// ==========================================
int WINAPI WinMain(HINSTANCE hInstance, HINSTANCE hPrevInstance, LPSTR lpCmdLine, int nCmdShow) {
    EnsureAdminOrRelaunch();

    const wchar_t CLASS_NAME[] = L"TacticalLauncherClass";

    WNDCLASSW wc = { 0 };
    wc.lpfnWndProc = WndProc;
    wc.hInstance = hInstance;
    wc.lpszClassName = CLASS_NAME;
    wc.hbrBackground = (HBRUSH)(COLOR_WINDOW);

    RegisterClassW(&wc);

    HWND hwnd = CreateWindowExW(
        0, CLASS_NAME, L"AutoReloader引导启动器",
        WS_OVERLAPPED | WS_CAPTION | WS_SYSMENU | WS_MINIMIZEBOX,
        CW_USEDEFAULT, CW_USEDEFAULT, 355, 290,
        NULL, NULL, hInstance, NULL
    );

    if (hwnd == NULL) return 0;

    RECT rc; GetWindowRect(hwnd, &rc);
    int xPos = (GetSystemMetrics(SM_CXSCREEN) - (rc.right - rc.left)) / 2;
    int yPos = (GetSystemMetrics(SM_CYSCREEN) - (rc.bottom - rc.top)) / 2;
    SetWindowPos(hwnd, 0, xPos, yPos, 0, 0, SWP_NOZORDER | SWP_NOSIZE);

    ShowWindow(hwnd, nCmdShow);

    MSG msg = { 0 };
    while (GetMessage(&msg, NULL, 0, 0)) {
        TranslateMessage(&msg);
        DispatchMessage(&msg);
    }

    return 0;
}
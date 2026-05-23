/**
 * =========================================================================================
 * 项目名称: MORandomizer Launcher (心灵终结武器引导器)
 * 功能描述: 自动化游戏引导与 DLL 内存静默注入工具。
 * 核心流程:
 * 1. 隐蔽运行: 启动时自动隐藏控制台黑框，化身后台幽灵进程。
 * 2. 官方引导: 唤起 MentalOmegaClient.exe，保证游戏原配环境与启动参数完整。
 * 3. 智能雷达: 轮询侦测底层实际对战进程 (gamemd.exe / YURI.exe)。
 * 4. 无缝注入: 战斗引擎初始化完毕后，通过 CreateRemoteThread 挂载并注入核心 DLL。
 * 5. 自动销毁: 持续监控客户端大厅 (clientdx.exe)，随玩家退出游戏而自动结束生命周期。
 * =========================================================================================
 */

#include <windows.h>
#include <tlhelp32.h>
#include <shellapi.h>

 // ==========================================
 // 辅助函数：雷达扫描进程是否存活
 // ==========================================
bool IsProcessRunning(const wchar_t* processName) {
    bool exists = false;
    PROCESSENTRY32W pe32;
    pe32.dwSize = sizeof(PROCESSENTRY32W);
    HANDLE hSnapshot = CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0);

    if (Process32FirstW(hSnapshot, &pe32)) {
        do {
            if (wcscmp(pe32.szExeFile, processName) == 0) {
                exists = true;
                break;
            }
        } while (Process32NextW(hSnapshot, &pe32));
    }
    CloseHandle(hSnapshot);
    return exists;
}

int main()
{
    // ==========================================
    // 1. 隐蔽运行：瞬间隐藏控制台黑框
    // ==========================================
    HWND hwnd = GetConsoleWindow();
    if (hwnd) {
        ShowWindow(hwnd, SW_HIDE);
    }

    // ==========================================
    // 2. 环境引导：通过官方引导器启动游戏
    // ==========================================
    ShellExecuteW(NULL, L"open", L"MentalOmegaClient.exe", NULL, NULL, SW_SHOW);

    // ==========================================
    // 3. 异步缓冲：等待套娃式启动链完成
    // ==========================================
    // 充分等待套娃过程：引导器启动 -> 检查更新 -> 唤醒真正的 clientdx.exe 战役大厅
    Sleep(10000);

    // ==========================================
    // 4. 核心挂载循环：持续监控对战状态
    // ==========================================
    while (true)
    {
        DWORD processId = 0;

        // 扫描当前是否进入了实际对战阶段
        PROCESSENTRY32W pe32;
        pe32.dwSize = sizeof(PROCESSENTRY32W);
        HANDLE hSnapshot = CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0);
        if (Process32FirstW(hSnapshot, &pe32)) {
            do {
                if (wcscmp(pe32.szExeFile, L"gamemd.exe") == 0 || wcscmp(pe32.szExeFile, L"YURI.exe") == 0) {
                    processId = pe32.th32ProcessID;
                    break;
                }
            } while (Process32NextW(hSnapshot, &pe32));
        }
        CloseHandle(hSnapshot);

        if (processId) {
            // ------------------------------------------
            // 状态：游戏对战引擎已启动
            // ------------------------------------------
            Sleep(3000); // 给予游戏引擎初始化内存的缓冲时间

            // 定位当前目录下的核心 DLL
            wchar_t dllPath[MAX_PATH];
            GetCurrentDirectoryW(MAX_PATH, dllPath);
		wcscat_s(dllPath, MAX_PATH, L"\\AutoReloader.dll"); // 加载的DLL

            // 执行硬核内存注入
            HANDLE hProcess = OpenProcess(PROCESS_ALL_ACCESS, FALSE, processId);
            if (hProcess) {
                // 在游戏进程中开辟内存空间
                void* pAlloc = VirtualAllocEx(hProcess, NULL, sizeof(dllPath), MEM_COMMIT, PAGE_READWRITE);
                // 写入 DLL 路径
                WriteProcessMemory(hProcess, pAlloc, dllPath, sizeof(dllPath), NULL);

                // 获取系统核心 API 地址
                HMODULE hKernel32 = GetModuleHandleW(L"kernel32.dll");
                FARPROC loadLibraryAddr = GetProcAddress(hKernel32, "LoadLibraryW");

                // 创建远线程，强制游戏进程加载我们的 DLL
                HANDLE hThread = CreateRemoteThread(hProcess, NULL, 0, (LPTHREAD_START_ROUTINE)loadLibraryAddr, pAlloc, 0, NULL);

                if (hThread) CloseHandle(hThread);

                // 死死盯住当前这局游戏，阻断循环，直到该局游戏结束（玩家退回大厅）
                WaitForSingleObject(hProcess, INFINITE);
                CloseHandle(hProcess);
            }
        }
        else {
            // ------------------------------------------
            // 状态：玩家在大厅选图，或已彻底退出游戏
            // ------------------------------------------
            // 侦测常驻大厅 clientdx.exe 是否存活
            if (!IsProcessRunning(L"clientdx.exe")) {
                // 大厅进程已消亡，说明玩家点击了右上角彻底退出
                // 引导器完美完成历史使命，安全下班！
                break;
            }
            // 还在选图阶段，休眠 1 秒后继续雷达扫描
            Sleep(1000);
        }
    }

    return 0;
}
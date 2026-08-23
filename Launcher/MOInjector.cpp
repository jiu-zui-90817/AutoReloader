/**
 * =========================================================================================
 * 项目名称: MORandomizer Launcher (心灵终结扩展引导器)
 * 核心功能:
 * 1. Win7 底层提权 (SeDebugPrivilege) + 精细化句柄权限。
 * 2. 全节点日志监控 (Injector_Log.txt)，精准定位注入断点。
 * 3. 智能雷达监控大厅，杜绝超时自杀。
 * 4. [新增] 多客户端兼容：同时兼容 Win10 的 clientdx.exe 与 Win7 的 clientxna.exe
 * =========================================================================================
 */
#include <windows.h>
#include <tlhelp32.h>
#include <shellapi.h>
#include <fstream>
#include <string>

 // ==========================================
 // 探针：日志记录功能
 // ==========================================
void WriteLog(const char* msg) {
    std::ofstream out("Injector_Log.txt", std::ios::app);
    if (!out.is_open()) return;
    SYSTEMTIME st;
    GetLocalTime(&st);
    char timeStr[64];
    sprintf_s(timeStr, "[%02d:%02d:%02d] ", st.wHour, st.wMinute, st.wSecond);
    out << timeStr << msg << std::endl;
    out.close();
}


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
// 提权：破除 Win7 UAC 隔离
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

// ==========================================
// 辅助：雷达扫描特定进程是否存活
// ==========================================
bool IsProcessRunning(const wchar_t* processName) {
    PROCESSENTRY32W pe32;
    pe32.dwSize = sizeof(PROCESSENTRY32W);
    HANDLE hSnapshot = CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0);
    if (Process32FirstW(hSnapshot, &pe32)) {
        do {
            if (wcscmp(pe32.szExeFile, processName) == 0) {
                CloseHandle(hSnapshot);
                return true;
            }
        } while (Process32NextW(hSnapshot, &pe32));
    }
    CloseHandle(hSnapshot);
    return false;
}

// ==========================================
// [新增] 辅助：判断任意 MO 大厅是否存活
// ==========================================
bool IsLobbyRunning() {
    // 同时兼容 DX、XNA 和 OGL 三种可能的大厅版本
    return IsProcessRunning(L"clientdx.exe") ||
        IsProcessRunning(L"clientxna.exe") ||
        IsProcessRunning(L"clientogl.exe");
}

int main()
{
    EnsureAdminOrRelaunch();

    // 每次启动清空旧日志
    std::ofstream clearLog("Injector_Log.txt", std::ios::trunc);
    clearLog << (IsRunAsAdmin() ? "[权限] 已以管理员运行\n" : "[权限] 未获得管理员（UAC 可能被拒绝）\n");
    clearLog.close();

    WriteLog("========== 战术工坊 MO 引导器启动 ==========");

    HWND hwnd = GetConsoleWindow();
    if (hwnd) ShowWindow(hwnd, SW_HIDE);

    if (EnableDebugPrivilege()) WriteLog("[系统] 提权成功 (获取 SeDebugPrivilege)");
    else WriteLog("[警告] 提权失败，后续可能遭遇拒绝访问");

    wchar_t currentDir[MAX_PATH];
    GetModuleFileNameW(NULL, currentDir, MAX_PATH);
    wchar_t* lastSlash = wcsrchr(currentDir, L'\\');
    if (lastSlash) *lastSlash = L'\0';
    WriteLog("[环境] 已锁定工作目录");

    WriteLog("[流程] 正在呼叫 MentalOmegaClient.exe...");
    ShellExecuteW(NULL, L"open", L"MentalOmegaClient.exe", NULL, currentDir, SW_SHOW);

    // ==========================================
    // 智能雷达：等待任意版本大厅载入
    // ==========================================
    WriteLog("[流程] 启动智能雷达：等待大厅 (DX/XNA/OGL) 载入...");
    int waitLobbyTime = 0;
    while (!IsLobbyRunning()) {
        Sleep(1000);
        waitLobbyTime++;

        if (waitLobbyTime > 120) {
            WriteLog("[警告] 等待大厅超时 (超过两分钟)，引导器安全退出。");
            return 0;
        }
    }
    WriteLog("[雷达] 大厅已就绪！开始轮询监控对战引擎...");

    // ==========================================
    // 核心挂载循环
    // ==========================================
    while (true)
    {
        DWORD processId = 0;
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
            char pidMsg[128];
            sprintf_s(pidMsg, "[雷达] 捕获引擎进程 PID: %lu", processId);
            WriteLog(pidMsg);

            WriteLog("[流程] 等待引擎完全解冻 (10秒缓冲)...");
            Sleep(10000);

            wchar_t dllPath[MAX_PATH];
            wcscpy_s(dllPath, MAX_PATH, currentDir);
            wcscat_s(dllPath, MAX_PATH, L"\\AutoReloader.dll");

            WriteLog("[注入] 尝试获取底层操作句柄...");
            HANDLE hProcess = OpenProcess(
                PROCESS_CREATE_THREAD | PROCESS_QUERY_INFORMATION | PROCESS_VM_OPERATION | PROCESS_VM_WRITE | PROCESS_VM_READ,
                FALSE,
                processId
            );

            if (hProcess) {
                WriteLog("[注入] 句柄获取成功，开始分配内存...");
                void* pAlloc = VirtualAllocEx(hProcess, NULL, sizeof(dllPath), MEM_COMMIT | MEM_RESERVE, PAGE_READWRITE);

                if (pAlloc) {
                    WriteLog("[注入] 内存分配成功，正在写入 DLL 路径...");
                    WriteProcessMemory(hProcess, pAlloc, dllPath, sizeof(dllPath), NULL);

                    HMODULE hKernel32 = GetModuleHandleW(L"kernel32.dll");
                    FARPROC loadLibraryAddr = GetProcAddress(hKernel32, "LoadLibraryW");

                    WriteLog("[注入] 正在调用 CreateRemoteThread 发射...");
                    HANDLE hThread = CreateRemoteThread(hProcess, NULL, 0, (LPTHREAD_START_ROUTINE)loadLibraryAddr, pAlloc, 0, NULL);

                    if (hThread) {
                        WriteLog(">>> [大捷] 远线程执行完毕，DLL 已发送至引擎内！ <<<");
                        CloseHandle(hThread);
                    }
                    else {
                        WriteLog("[错误] CreateRemoteThread 被拦截或失败！");
                    }
                }
                else {
                    WriteLog("[错误] VirtualAllocEx 内存分配失败！");
                }

                WriteLog("[状态] 挂载流程完毕，进入阻塞监听...");
                WaitForSingleObject(hProcess, INFINITE);
                WriteLog("[状态] 本局游戏结束，重新开启雷达...");
                CloseHandle(hProcess);
            }
            else {
                WriteLog("[错误] OpenProcess 被拒绝访问！");
            }
        }
        else {
            // 对战进程不在，检查所有可能的大厅还在不在
            if (!IsLobbyRunning()) {
                WriteLog("========== MO 大厅已关闭，引导器安全退出 ==========");
                break;
            }
            Sleep(1000);
        }
    }
    return 0;
}

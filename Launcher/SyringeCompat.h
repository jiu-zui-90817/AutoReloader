/**
 * AutoReloader - Syringe 版本自适应
 *
 * 只在启动器侧读取 Syringe.exe 的信息，不修改、不替换任何原版文件。
 * 新版 SyringeEx 使用 --args="..."，旧版 Syringe 直接跟游戏参数。
 */
#pragma once

#include <windows.h>
#include <algorithm>
#include <cstdint>
#include <cstdio>
#include <cwchar>
#include <string>
#include <vector>

namespace SyringeCompat
{
    inline bool ContainsNoCase(const std::wstring& haystack, const wchar_t* needle)
    {
        if (!needle || !*needle)
            return false;

        const size_t needleLen = wcslen(needle);
        if (haystack.size() < needleLen)
            return false;

        for (size_t i = 0; i + needleLen <= haystack.size(); ++i)
        {
            if (_wcsnicmp(haystack.c_str() + i, needle, needleLen) == 0)
                return true;
        }
        return false;
    }

    inline bool VersionInfoMentionsSyringeEx(const std::wstring& path)
    {
        DWORD dummy = 0;
        const DWORD size = GetFileVersionInfoSizeW(path.c_str(), &dummy);
        if (size == 0)
            return false;

        std::vector<BYTE> data(size);
        if (!GetFileVersionInfoW(path.c_str(), 0, size, data.data()))
            return false;

        struct Translation
        {
            WORD language;
            WORD codePage;
        };

        Translation* translations = nullptr;
        UINT translationBytes = 0;
        if (!VerQueryValueW(data.data(), L"\\VarFileInfo\\Translation",
                            reinterpret_cast<LPVOID*>(&translations), &translationBytes)
            || translationBytes < sizeof(Translation) || !translations)
        {
            return false;
        }

        const wchar_t* keys[] = {
            L"ProductName",
            L"FileDescription",
            L"OriginalFilename",
            L"InternalName",
            L"CompanyName",
            L"FileVersion",
        };

        const size_t count = translationBytes / sizeof(Translation);
        for (size_t i = 0; i < count; ++i)
        {
            for (const wchar_t* key : keys)
            {
                wchar_t subBlock[128]{};
                swprintf_s(subBlock, L"\\StringFileInfo\\%04x%04x\\%s",
                           translations[i].language, translations[i].codePage, key);

                wchar_t* value = nullptr;
                UINT valueBytes = 0;
                if (VerQueryValueW(data.data(), subBlock,
                                   reinterpret_cast<LPVOID*>(&value), &valueBytes)
                    && value && valueBytes >= sizeof(wchar_t))
                {
                    if (ContainsNoCase(value, L"SyringeEx"))
                        return true;
                }
            }
        }
        return false;
    }

    inline bool FileBytesMentionSyringeEx(const std::wstring& path)
    {
        HANDLE file = CreateFileW(path.c_str(), GENERIC_READ, FILE_SHARE_READ, nullptr,
                                  OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, nullptr);
        if (file == INVALID_HANDLE_VALUE)
            return false;

        constexpr DWORD chunkSize = 1u << 20;
        std::vector<char> buffer(chunkSize);
        std::string carry;
        DWORD read = 0;
        bool found = false;
        uint64_t total = 0;

        while (!found && ReadFile(file, buffer.data(), chunkSize, &read, nullptr) && read > 0)
        {
            total += read;
            std::string chunk(buffer.data(), read);
            std::string search = carry + chunk;

            // ASCII marker, and the same marker encoded as UTF-16LE.
            if (search.find("SyringeEx") != std::string::npos)
            {
                found = true;
                break;
            }

            const wchar_t wide[] = L"SyringeEx";
            const std::string wideBytes(reinterpret_cast<const char*>(wide),
                                        sizeof(wide) - sizeof(wchar_t));
            if (search.find(wideBytes) != std::string::npos)
            {
                found = true;
                break;
            }

            const size_t keep = std::min<size_t>(search.size(), 64);
            carry = search.substr(search.size() - keep);

            if (total > (64ull << 20)) // 64 MiB safety cap
                break;
        }

        CloseHandle(file);
        return found;
    }

    // 返回 true 表示这是 SyringeEx / 支持 --args 的新版。
    inline bool DetectSyringeEx(const std::wstring& syringePath)
    {
        if (VersionInfoMentionsSyringeEx(syringePath))
            return true;
        return FileBytesMentionSyringeEx(syringePath);
    }

    inline std::wstring Quote(const std::wstring& value)
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

    inline std::wstring EscapeInsideQuotes(const std::wstring& value)
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

    inline std::wstring BuildCommandLine(const std::wstring& syringePath,
                                         const std::wstring& gameExe,
                                         const std::vector<std::wstring>& gameArgs,
                                         bool syringeEx)
    {
        std::wstring command = Quote(syringePath) + L" " + Quote(gameExe);

        if (syringeEx)
        {
            if (!gameArgs.empty())
            {
                std::wstring blob;
                for (const auto& arg : gameArgs)
                {
                    if (!blob.empty())
                        blob.push_back(L' ');
                    blob += Quote(arg);
                }
                command += L" --args=\"" + EscapeInsideQuotes(blob) + L"\"";
            }
        }
        else
        {
            for (const auto& arg : gameArgs)
                command += L" " + Quote(arg);
        }

        return command;
    }
}

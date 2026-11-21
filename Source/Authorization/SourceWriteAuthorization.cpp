#include "SourceWriteAuthorization.h"

#include <fstream>
#include <iterator>
#include <stdexcept>
#include <string>

#ifdef _WIN32
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#endif

namespace WinyunqCodeSytle
{
#ifdef _WIN32
namespace
{
DWORD Request(const std::filesystem::path& argument, bool signature = false)
{
    wchar_t executable[32768];
    const auto length = GetModuleFileNameW(nullptr, executable, ARRAYSIZE(executable));
    if (!length || length >= ARRAYSIZE(executable))
        throw std::runtime_error("Cannot locate the MCP authorization executable.");
    const auto helper = std::filesystem::path(executable).parent_path() / "UnrealMcpAuthorization.exe";
    auto command = L"\"" + helper.wstring() + L"\"";
    if (signature)
        command += L" --signature";
    command += L" \"" + argument.wstring() + L"\"";
    STARTUPINFOW startup{};
    startup.cb = sizeof(startup);
    PROCESS_INFORMATION process{};
    if (!CreateProcessW(helper.c_str(), command.data(), nullptr, nullptr, FALSE, CREATE_NO_WINDOW,
                        nullptr, nullptr, &startup, &process))
        throw std::runtime_error("Cannot launch the Windows authorization notification.");
    CloseHandle(process.hThread);
    WaitForSingleObject(process.hProcess, INFINITE);
    DWORD decision = 2;
    GetExitCodeProcess(process.hProcess, &decision);
    CloseHandle(process.hProcess);
    return decision;
}
}
#endif

bool ConfirmSignatureChange(const std::filesystem::path& scratch, const std::string& review)
{
#ifdef _WIN32
    const auto request = scratch / "signature-review.json";
    std::ofstream output(request, std::ios::binary | std::ios::trunc);
    output.exceptions(std::ios::badbit | std::ios::failbit);
    output << review;
    output.close();
    const auto decision = Request(request, true);
    if (decision > 1)
        throw std::runtime_error("Windows could not show the signature review.");
    return decision == 0;
#else
    (void)scratch;
    (void)review;
    throw std::runtime_error("An interactive signature review is unavailable on this platform.");
#endif
}

void SourceWriteAuthorization::Require(const std::filesystem::path& project)
{
    if (Allowed)
        return;
#ifdef _WIN32
    namespace fs = std::filesystem;
    const auto directory = fs::canonical(project);
    wchar_t appData[32768];
    const auto appDataSize = GetEnvironmentVariableW(L"LOCALAPPDATA", appData, ARRAYSIZE(appData));
    if (!appDataSize || appDataSize >= ARRAYSIZE(appData))
        throw std::runtime_error("Cannot find the local MCP authorization directory.");
    const auto grantDirectory = fs::path(appData) / "WinyunqCodeSytle" / "SourceWrite";
    const auto key = directory.generic_u8string();
    unsigned long long hash = 14695981039346656037ull;
    for (unsigned char byte : key)
        hash = (hash ^ byte) * 1099511628211ull;
    const auto grantFile = grantDirectory / (std::to_string(hash) + ".grant");
    {
        std::ifstream input(grantFile, std::ios::binary);
        if (input && std::string(std::istreambuf_iterator<char>(input), {}) == key)
        {
            Allowed = true;
            return;
        }
    }

    const auto decision = Request(directory);
    if (decision != 0 && decision != 3)
        throw std::runtime_error(decision == 1 ? "Project write permission was not granted."
                                               : "Windows could not deliver the authorization notification.");
    if (decision == 3)
    {
        fs::create_directories(grantDirectory);
        std::ofstream output(grantFile, std::ios::binary | std::ios::trunc);
        output.write(key.data(), static_cast<std::streamsize>(key.size()));
        output.close();
        if (!output)
            throw std::runtime_error("Could not save the project write permission.");
    }
    Allowed = true;
#else
    (void)project;
    throw std::runtime_error("No interactive source-write authorization is available on this platform.");
#endif
}
}

#include "EditSource.h"

#include <fstream>
#include <stdexcept>
#include <system_error>

#ifdef _WIN32
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#endif

namespace WinyunqCodeSytle
{
SourceEdit EditSource(const NativeProject& project, const fs::path& path,
                      std::string_view oldCode, std::string_view newCode)
{
    const auto target = project.Resolve(path);
    auto before = ReadBytes(target);
    const auto offset = before.find(oldCode);
    if (oldCode.empty() || offset == std::string::npos || before.find(oldCode, offset + 1) != std::string::npos)
        throw std::runtime_error("The old C++ fragment must match exactly once.");
    auto after = before;
    after.replace(offset, oldCode.size(), newCode);
    return {target, std::move(before), std::move(after)};
}

void ApplySourceEdit(const NativeProject& project, const SourceEdit& edit, const std::string& plan)
{
    const auto path = project.Resolve(edit.Path);
    if (path != edit.Path || ReadBytes(path) != edit.Before)
        throw std::runtime_error("The source changed after preview.");
    auto temporary = path;
    temporary += "." + plan + ".tmp";
    try
    {
        std::ofstream output(temporary, std::ios::binary | std::ios::trunc);
        output.exceptions(std::ios::badbit | std::ios::failbit);
        output.write(edit.After.data(), static_cast<std::streamsize>(edit.After.size()));
        output.close();
        fs::permissions(temporary, fs::status(path).permissions());
        if (project.Resolve(path) != path || ReadBytes(path) != edit.Before)
            throw std::runtime_error("The source changed before commit.");
#ifdef _WIN32
        if (!MoveFileExW(temporary.c_str(), path.c_str(), MOVEFILE_REPLACE_EXISTING | MOVEFILE_WRITE_THROUGH))
            throw std::system_error(GetLastError(), std::system_category(), "Replace C++ source");
#else
        fs::rename(temporary, path);
#endif
    }
    catch (...)
    {
        std::error_code error;
        fs::remove(temporary, error);
        throw;
    }
}
}

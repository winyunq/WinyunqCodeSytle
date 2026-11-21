#pragma once

#include "Configure/NativeProject.h"

#include <string_view>

namespace WinyunqCodeSytle
{
struct SourceEdit
{
    fs::path Path;
    std::string Before;
    std::string After;
};

/// Preview an exact, unique source fragment edit against the current file.
SourceEdit EditSource(const NativeProject& project, const fs::path& path,
                      std::string_view oldCode, std::string_view newCode);

/// Apply an approved source edit if the file still matches its preview snapshot.
void ApplySourceEdit(const NativeProject& project, const SourceEdit& edit, const std::string& plan);
}

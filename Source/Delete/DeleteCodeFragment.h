#pragma once

#include "Write/EditSource.h"

namespace WinyunqCodeSytle
{
/// Preview deletion of one uniquely matched C++ source fragment.
SourceEdit DeleteCodeFragment(const NativeProject& project, const fs::path& path, std::string_view code);
}

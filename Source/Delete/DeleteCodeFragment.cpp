#include "DeleteCodeFragment.h"

namespace WinyunqCodeSytle
{
SourceEdit DeleteCodeFragment(const NativeProject& project, const fs::path& path, std::string_view code)
{
    return EditSource(project, path, code, {});
}
}

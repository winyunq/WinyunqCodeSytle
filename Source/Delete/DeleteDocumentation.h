#pragma once

#include "Write/EditDocumentation.h"

namespace WinyunqCodeSytle
{
/// Preview removal of the contiguous documentation attached to the selected declaration.
SourceEdit DeleteDocumentation(const NativeProject& project, const Symbol& symbol);
}

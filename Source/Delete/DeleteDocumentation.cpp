#include "DeleteDocumentation.h"

namespace WinyunqCodeSytle
{
SourceEdit DeleteDocumentation(const NativeProject& project, const Symbol& symbol)
{
    return EditDocumentation(project, symbol, {});
}
}

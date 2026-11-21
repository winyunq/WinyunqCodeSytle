#pragma once

#include "Read/ReadDeclaration.h"

namespace WinyunqCodeSytle
{
struct SourceDefinition
{
    SourceLocation Location;
    unsigned EndLine;
    std::string Code;
};

/// Read a symbol's definition from the indexed source file and line range.
SourceDefinition ReadDefinition(const NativeProject& project, const Symbol& symbol);
}

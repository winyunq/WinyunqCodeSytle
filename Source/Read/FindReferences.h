#pragma once

#include "Read/ReadDeclaration.h"

namespace WinyunqCodeSytle
{
struct Reference
{
    std::string Name;
    std::string Direction;
    std::string File;
    unsigned Line;
};

/// Return the incoming and outgoing references reported by Doxygen.
std::vector<Reference> FindReferences(const Symbol& symbol);
}

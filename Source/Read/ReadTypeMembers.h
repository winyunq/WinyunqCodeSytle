#pragma once

#include "Read/FindSymbols.h"

namespace WinyunqCodeSytle
{
struct TypeMember
{
    std::string Name;
    std::string Kind;
    std::string Access;
};

/// List direct bases and declared members with their indexed C++ access.
std::vector<TypeMember> ReadTypeMembers(const Symbol& symbol);
}

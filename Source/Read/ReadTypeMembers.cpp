#include "ReadTypeMembers.h"

#include <stdexcept>

namespace WinyunqCodeSytle
{
std::vector<TypeMember> ReadTypeMembers(const Symbol& symbol)
{
    if (symbol.Kind != "class" && symbol.Kind != "struct" && symbol.Kind != "union")
        throw std::runtime_error("Expected a C++ class, structure or union.");
    std::vector<TypeMember> result;
    for (auto base : symbol.Node.children("basecompoundref"))
        result.push_back({base.child_value(), "base", base.attribute("prot").value()});
    for (auto section : symbol.Node.children("sectiondef"))
        for (auto member : section.children("memberdef"))
            result.push_back({member.child_value("name"), member.attribute("kind").value(), member.attribute("prot").value()});
    return result;
}
}

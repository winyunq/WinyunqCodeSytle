#include "FindReferences.h"

namespace WinyunqCodeSytle
{
std::vector<Reference> FindReferences(const Symbol& symbol)
{
    std::vector<Reference> result;
    for (const auto direction : {"references", "referencedby"})
        for (const auto item : symbol.Node.children(direction))
            result.push_back({item.child_value(), direction, item.attribute("compoundref").value(),
                              item.attribute("startline").as_uint()});
    return result;
}
}

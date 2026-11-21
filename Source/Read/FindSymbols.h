#pragma once

#include "Configure/NativeProject.h"

#include <memory>
#include <string_view>
#include <vector>
#include <pugixml.hpp>

namespace WinyunqCodeSytle
{
/// One declaration or member selected from the Doxygen XML index.
struct Symbol
{
    std::string Id;
    std::string Name;
    std::string Kind;
    std::string Signature;
    std::shared_ptr<pugi::xml_document> Document;
    pugi::xml_node Node;
};

/// Find indexed C++ symbols by short name, qualified name or qualified signature.
/// @param index Directory containing the Doxygen index.xml and compound XML files.
/// @param name Short name, qualified name, qualified signature or Doxygen symbol ID.
/// @return Matching symbols with distinct Doxygen IDs, or an empty list if none match.
std::vector<Symbol> FindSymbols(const fs::path& index, std::string_view name);

/// Resolve a single symbol. Ambiguous overloads require a signature or exact index ID.
Symbol SelectSymbol(const fs::path& index, std::string_view name);
}

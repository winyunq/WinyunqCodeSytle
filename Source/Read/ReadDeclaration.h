#pragma once

#include "Read/FindSymbols.h"

#include <json.hpp>

namespace WinyunqCodeSytle
{
struct SourceLocation
{
    fs::path Path;
    unsigned Line;
};

/// Return the recorded declaration location, falling back to the indexed declaration or definition.
SourceLocation DeclarationLocation(const NativeProject& project, const Symbol& symbol);

std::vector<nlohmann::json> ReadCppDeclarations(const NativeProject& project, const fs::path& unit,
                                               const std::string& name, const std::string* replacement = nullptr);
nlohmann::json FindCppDeclaration(const std::vector<nlohmann::json>& ast, const Symbol& symbol,
                                 const SourceLocation& location, std::string_view source, bool definition = false);

/// Return the Doxygen-indexed C++ declaration text for the symbol.
std::string ReadDeclaration(const Symbol& symbol);
}

#pragma once

#include "Read/ReadDeclaration.h"
#include "Write/EditSource.h"

#include <json.hpp>
#include <utility>

namespace WinyunqCodeSytle
{
std::pair<std::size_t, std::size_t> DocumentationRange(const std::string& source, std::size_t declaration);

/// Insert or update the contiguous /// comment immediately above the indexed declaration.
/// Passing an empty comment removes the existing documentation at that location.
SourceEdit EditDocumentation(const NativeProject& project, const Symbol& symbol, std::string_view comment);

/// Preview a documentation edit at an already resolved declaration or definition location.
SourceEdit EditDocumentation(const SourceLocation& location, std::string_view comment);

/// Preview additions and updates to the supplied Doxygen fields.
SourceEdit EditDocumentation(const SourceLocation& location, const Symbol& symbol, const nlohmann::json& fields);

/// Remove the supplied parameter annotations from this documentation block.
SourceEdit RemoveParameterComments(const SourceLocation& location, const Symbol& symbol,
                                     const std::vector<std::string>& names);
}

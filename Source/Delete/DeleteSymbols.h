#pragma once

#include "Read/FindSymbols.h"
#include "Write/EditSource.h"

namespace WinyunqCodeSytle
{
struct DeleteReference
{
    fs::path File;
    unsigned Line;
    std::string Symbol;
    bool operator==(const DeleteReference& other) const
    {
        return File == other.File && Line == other.Line && Symbol == other.Symbol;
    }
};

struct SymbolDeletion
{
    std::vector<SourceEdit> Edits;
    std::vector<DeleteReference> References;
};

SymbolDeletion PreviewSymbolDeletion(const NativeProject& project, const fs::path& index,
                                     const std::vector<Symbol>& symbols);
}

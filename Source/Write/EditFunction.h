#pragma once

#include "Read/FindSymbols.h"
#include "Write/EditSource.h"

#include <json.hpp>

namespace WinyunqCodeSytle
{
struct FunctionEdit
{
    std::vector<SourceEdit> Edits;
    bool AddsParameters = false;
    std::vector<std::string> WithdrawParameters;
    nlohmann::json Review;
};

FunctionEdit EditFunctionSignature(const NativeProject& project, const Symbol& symbol, const nlohmann::json& signature);
SourceEdit EditFunctionBody(const NativeProject& project, const Symbol& symbol, const std::string& body);
SourceEdit AddMember(const NativeProject& project, const Symbol& symbol, const std::string& declaration);
}

#pragma once

#include <filesystem>
#include <string>

namespace WinyunqCodeSytle
{
bool ConfirmSignatureChange(const std::filesystem::path& scratch, const std::string& review);

class SourceWriteAuthorization
{
public:
    void Require(const std::filesystem::path& project);

private:
    bool Allowed = false;
};
}

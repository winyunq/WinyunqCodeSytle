#pragma once

#include <filesystem>
#include <string>
#include <vector>

namespace WinyunqCodeSytle
{
namespace fs = std::filesystem;

/// Holds the project root, Doxygen executable and private working directory for one MCP session.
class NativeProject
{
public:
    NativeProject(fs::path root, fs::path doxygen);
    ~NativeProject();
    NativeProject(const NativeProject&) = delete;
    NativeProject& operator=(const NativeProject&) = delete;

    /// Resolve a file path under the project root, including existing link targets.
    fs::path Resolve(const fs::path& path) const;

    /// Generate XML for the project's C++ source and return the XML directory.
    fs::path Index();
    fs::path IndexDeclaration(const std::string& declaration) const;
    std::string AnalyzeCpp(const fs::path& translationUnit, const std::string& name,
                           const std::string* replacement = nullptr) const;
    std::string QueryCppReferences(const std::vector<fs::path>& units, const std::vector<std::string>& names) const;
    const fs::path& Scratch() const { return WorkDirectory; }

    /// Run Doxygen on the project's Source directory and write output to the supplied directory.
    void RunDoxygen(const fs::path& output, bool html, bool publicHeadersOnly = false,
                    const fs::path& input = {}, const std::vector<fs::path>& files = {},
                    const std::vector<std::string>& defines = {}) const;

    const fs::path Root;

private:
    fs::path Doxygen;
    fs::path WorkDirectory;
};

/// Read an existing regular file as bytes, preserving line endings and encoding.
std::string ReadBytes(const fs::path& path);
}

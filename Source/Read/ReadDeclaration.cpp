#include "ReadDeclaration.h"

#include <algorithm>
#include <optional>
#include <sstream>

#include <stdexcept>

namespace WinyunqCodeSytle
{
namespace
{
std::string Text(pugi::xml_node node)
{
    std::string text;
    for (auto child : node.children())
        text += child.type() == pugi::node_pcdata ? child.value() : Text(child);
    return text;
}
}

SourceLocation DeclarationLocation(const NativeProject& project, const Symbol& symbol)
{
    const auto location = symbol.Node.child("location");
    const auto declared = location.attribute("declfile");
    const auto file = declared && *declared.value() ? declared : location.attribute("file");
    const auto line = (file == declared ? location.attribute("declline") : location.attribute("line")).as_uint();
    if (!file || line == 0)
        throw std::runtime_error("Doxygen has no source location for " + symbol.Name);
    return {project.Resolve(fs::u8path(file.value())), line};
}

std::string ReadDeclaration(const Symbol& symbol)
{
    const auto definition = Text(symbol.Node.child("definition"));
    return definition.empty() ? symbol.Kind + " " + symbol.Name : definition + Text(symbol.Node.child("argsstring"));
}

std::vector<nlohmann::json> ReadCppDeclarations(const NativeProject& project, const fs::path& unit,
                                               const std::string& name, const std::string* replacement)
{
    std::istringstream output(project.AnalyzeCpp(unit, name, replacement));
    std::vector<nlohmann::json> result;
    while (output >> std::ws && output.peek() != std::char_traits<char>::eof())
    {
        nlohmann::json node;
        output >> node;
        result.push_back(std::move(node));
    }
    return result;
}

nlohmann::json FindCppDeclaration(const std::vector<nlohmann::json>& ast, const Symbol& symbol,
                                 const SourceLocation& location, std::string_view source, bool definition)
{
    const auto indexed = symbol.Node.child("location");
    unsigned column = 0;
    for (const auto* prefix : {"decl", ""})
    {
        const auto file = indexed.attribute((std::string(prefix) + "file").c_str());
        const auto line = indexed.attribute((std::string(prefix) + "line").c_str());
        if (file && line.as_uint() == location.Line && fs::weakly_canonical(fs::u8path(file.value())) == location.Path)
            column = indexed.attribute((std::string(prefix) + "column").c_str()).as_uint();
    }
    const auto scope = symbol.Name.rfind("::");
    const auto name = scope == std::string::npos ? symbol.Name : symbol.Name.substr(scope + 2);
    auto lineAt = [&](const nlohmann::json& position) {
        const auto offset = position.at("offset").get<std::size_t>();
        if (offset > source.size())
            throw std::runtime_error("Clang reported a position outside the source file.");
        return 1 + static_cast<unsigned>(std::count(source.begin(), source.begin() + offset, '\n'));
    };
    std::optional<nlohmann::json> selected;
    for (const auto& root : ast)
    {
        const auto* node = &root;
        const auto rootKind = root.value("kind", "");
        if (rootKind == "FunctionTemplateDecl" || rootKind == "ClassTemplateDecl")
            for (const auto& child : root.at("inner"))
                if (child.value("name", "") == name)
                {
                    node = &child;
                    break;
                }
        if (node->value("isImplicit", false) || node->value("name", "") != name || !node->contains("loc"))
            continue;
        const auto kind = node->value("kind", "");
        const bool function = kind == "FunctionDecl" || kind == "CXXMethodDecl" || kind == "CXXConstructorDecl" ||
            kind == "CXXDestructorDecl" || kind == "CXXConversionDecl";
        const bool record = kind == "CXXRecordDecl";
        if ((symbol.Kind == "function" && !function) ||
            (symbol.Kind == "variable" && kind != "VarDecl" && kind != "FieldDecl") ||
            ((symbol.Kind == "class" || symbol.Kind == "struct" || symbol.Kind == "union") &&
                (!record || !node->value("completeDefinition", false))) ||
            (symbol.Kind == "enum" && kind != "EnumDecl") ||
            (symbol.Kind == "enumvalue" && kind != "EnumConstantDecl") ||
            (symbol.Kind == "typedef" && kind != "TypedefDecl" && kind != "TypeAliasDecl"))
            continue;
        const auto& position = node->at("loc");
        const auto file = position.value("file", root.at("loc").value("file", ""));
        if (file.empty() || !position.contains("offset") || fs::weakly_canonical(fs::u8path(file)) != location.Path)
            continue;
        // Doxygen places record compounds at column 1, even when the type name is indented.
        if (column && !(record && column == 1) &&
            lineAt(position) == location.Line && position.value("col", 0u) != column)
            continue;
        auto last = lineAt(position);
        if (definition)
        {
            const auto children = node->find("inner");
            if (children == node->end())
                continue;
            const auto body = std::find_if(children->begin(), children->end(), [](const auto& child) {
                return child.value("kind", "") == "CompoundStmt";
            });
            if (body == children->end())
                continue;
            last = lineAt(body->at("range").at("begin"));
        }
        if (location.Line < lineAt(node->at("range").at("begin")) || location.Line > last)
            continue;
        if (selected && selected->at("loc") != position)
            throw std::runtime_error("Multiple C++ declarations match the indexed location: " + symbol.Name);
        selected = *node;
    }
    if (!selected)
        throw std::runtime_error("Clang could not locate the indexed C++ declaration: " + symbol.Name);
    return std::move(*selected);
}
}

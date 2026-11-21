#include "EditFunction.h"

#include "Read/ReadDeclaration.h"
#include "Read/ReadDefinition.h"
#include "Read/ReadDocumentation.h"

#include <algorithm>
#include <cctype>
#include <map>
#include <optional>
#include <regex>
#include <set>
#include <stdexcept>

namespace WinyunqCodeSytle
{
namespace
{
using nlohmann::json;

std::size_t Offset(const json& position)
{
    return position.at("offset").get<std::size_t>();
}

std::size_t End(const json& range)
{
    const auto& position = range.at("end");
    return Offset(position) + position.at("tokLen").get<std::size_t>();
}

const json* Child(const json& node, const char* kind)
{
    if (const auto children = node.find("inner"); children != node.end())
        for (const auto& child : *children)
            if (child.value("kind", "") == kind)
                return &child;
    return nullptr;
}

std::vector<const json*> Parameters(const json& function)
{
    std::vector<const json*> result;
    if (const auto children = function.find("inner"); children != function.end())
        for (const auto& child : *children)
            if (child.value("kind", "") == "ParmVarDecl")
                result.push_back(&child);
    return result;
}

bool References(const json& node, const std::string& identity)
{
    if (const auto reference = node.find("referencedDecl"); reference != node.end() && reference->value("id", "") == identity)
        return true;
    if (const auto children = node.find("inner"); children != node.end())
        return std::any_of(children->begin(), children->end(), [&](const auto& child) { return References(child, identity); });
    return false;
}

std::string Join(const std::vector<std::string>& declarations)
{
    std::string result;
    for (const auto& declaration : declarations)
    {
        if (!result.empty())
            result += ", ";
        result += declaration;
    }
    return result;
}

std::pair<std::size_t, std::size_t> ParameterRange(const json& node, std::string_view source)
{
    const auto parameters = Parameters(node);
    if (!parameters.empty())
        return {Offset(parameters.front()->at("range").at("begin")), End(parameters.back()->at("range"))};
    const auto& name = node.at("loc");
    const auto open = source.find_first_not_of(" \t\r\n", Offset(name) + name.at("tokLen").get<std::size_t>());
    if (open == std::string_view::npos || source[open] != '(')
        throw std::runtime_error("Cannot locate the empty C++ parameter list.");
    const auto close = source.find(')', open + 1);
    if (close == std::string_view::npos || close >= End(node.at("range")))
        throw std::runtime_error("Cannot locate the end of the empty C++ parameter list.");
    return {open + 1, close};
}

std::string ParameterText(std::string_view source, const json& parameter)
{
    const auto& range = parameter.at("range");
    const auto start = Offset(range.at("begin"));
    return std::string(source.substr(start, End(range) - start));
}
}

FunctionEdit EditFunctionSignature(const NativeProject& project, const Symbol& symbol, const json& signature)
{
    if (symbol.Kind != "function" || !signature.is_object() || signature.empty())
        throw std::runtime_error("Provide a signature change for a C++ function.");
    for (const auto& [key, value] : signature.items())
        if (key != "name" && key != "parameters")
            throw std::runtime_error("Unsupported signature field: " + key);
    const auto newName = signature.value("name", "");
    static const std::regex identifier("[A-Za-z_][A-Za-z_0-9]*");
    if (signature.contains("name") && !std::regex_match(newName, identifier))
        throw std::runtime_error("Provide a valid C++ function name.");

    const auto declaration = DeclarationLocation(project, symbol);
    const auto indexed = symbol.Node.child("location");
    const auto definition = indexed.attribute("bodystart").as_uint()
        ? std::optional<SourceDefinition>(ReadDefinition(project, symbol)) : std::nullopt;
    const auto unit = definition ? definition->Location.Path : declaration.Path;
    const bool inlineDefinition = definition && unit == declaration.Path && declaration.Line >= definition->Location.Line &&
        declaration.Line <= definition->EndLine;
    auto header = ReadBytes(declaration.Path);
    const auto ast = ReadCppDeclarations(project, unit, symbol.Name);
    const auto declared = FindCppDeclaration(ast, symbol, declaration, header, inlineDefinition);
    const auto originalParameters = Parameters(declared);
    const auto doc = ReadDocumentation(symbol);
    std::map<std::string, std::string> notes;
    for (const auto& parameter : doc.value("parameters", json::array()))
        notes.emplace(parameter.value("name", ""), parameter.value("description", ""));

    FunctionEdit result;
    result.Review = {{"function", symbol.Name}, {"brief", doc.value("brief", "")},
                     {"details", doc.value("details", json::array())}, {"rows", json::array()}};
    std::vector<std::string> names;
    std::vector<std::string> proposed;
    std::vector<std::string> withoutDefaults;
    if (signature.contains("parameters"))
    {
        proposed = signature.at("parameters").get<std::vector<std::string>>();
        const auto probeIndex = project.IndexDeclaration("void CodeStyleProposedSignature(" + Join(proposed) + ");\n");
        const auto probe = FindSymbols(probeIndex, "CodeStyleProposedSignature");
        if (probe.size() != 1)
            throw std::runtime_error("Doxygen could not parse the new C++ parameter declarations.");
        const auto compact = [](std::string text) {
            text.erase(std::remove_if(text.begin(), text.end(), [](unsigned char character) {
                return std::isspace(character);
            }), text.end());
            return text;
        };
        if (compact(probe.front().Node.child_value("argsstring")) != compact('(' + Join(proposed) + ')'))
            throw std::runtime_error("Each signature entry must contain only a parameter declaration.");
        std::set<std::string> unique;
        for (const auto parameter : probe.front().Node.children("param"))
        {
            if (names.size() == proposed.size())
                throw std::runtime_error("Supply one C++ parameter declaration per list entry.");
            const std::string name = parameter.child_value("declname");
            if (name.empty() || !unique.insert(name).second)
                throw std::runtime_error("Each proposed parameter must have a distinct name.");
            auto definitionText = proposed[names.size()];
            const std::string defaultValue = parameter.child_value("defval");
            if (!defaultValue.empty())
            {
                const auto value = definitionText.rfind(defaultValue);
                const auto assignment = value == std::string::npos ? value : definitionText.rfind('=', value);
                if (assignment == std::string::npos)
                    throw std::runtime_error("Cannot map the default argument for " + name + " to its source.");
                definitionText.erase(assignment);
                definitionText.erase(definitionText.find_last_not_of(" \t\r\n") + 1);
            }
            names.push_back(name);
            withoutDefaults.push_back(std::move(definitionText));
        }
        if (names.size() != proposed.size())
            throw std::runtime_error("Supply one C++ parameter declaration per list entry.");
    }

    if (signature.contains("parameters"))
    {
        for (std::size_t i = 0; i < std::max(originalParameters.size(), names.size()); ++i)
        {
            const auto* previous = i < originalParameters.size() ? originalParameters[i] : nullptr;
            const auto name = i < names.size() ? names[i] : previous->value("name", "");
            result.Review["rows"].push_back({{"before", previous ? ParameterText(header, *previous) : ""},
                {"after", i < proposed.size() ? proposed[i] : ""},
                {"description", notes.count(name) ? notes.at(name) : ""}});
            if (i >= names.size())
                continue;
            if (std::any_of(originalParameters.begin(), originalParameters.end(), [&](const auto* parameter) {
                    return parameter->value("name", "") == name;
                }))
                continue;
            if (notes.find(name) == notes.end() || notes.at(name).empty())
                throw std::runtime_error("Document the added parameter before changing the API: " + name);
            result.AddsParameters = true;
            const auto equivalent = std::any_of(originalParameters.begin(), originalParameters.end(), [&](const auto* parameter) {
                const auto original = notes.find(parameter->value("name", ""));
                return original != notes.end() && original->second == notes.at(name);
            });
            if (!equivalent)
                result.WithdrawParameters.push_back(name);
        }
    }

    struct Replacement { std::size_t Start; std::size_t End; std::string Text; };
    std::map<fs::path, std::pair<std::string, std::vector<Replacement>>> drafts;
    const auto edit = [&](const SourceLocation& location, const json& node, const std::string& before, bool implementation) {
        auto& [original, changes] = drafts.try_emplace(location.Path, before, std::vector<Replacement>{}).first->second;
        if (signature.contains("parameters"))
        {
            auto replacement = implementation && !inlineDefinition ? withoutDefaults : proposed;
            const auto actual = Parameters(node);
            const auto* body = Child(node, "CompoundStmt");
            for (std::size_t i = 0; body && i < originalParameters.size() && i < actual.size(); ++i)
            {
                const auto oldName = originalParameters[i]->value("name", "");
                const auto match = std::find(names.begin(), names.end(), oldName);
                if (match == names.end() && References(*body, actual[i]->at("id").get<std::string>()))
                    throw std::runtime_error("The function body still uses parameter: " + oldName);
                const auto actualName = actual[i]->value("name", "");
                if (match != names.end() && actualName != oldName && !actualName.empty())
                {
                    auto& statement = replacement[match - names.begin()];
                    const auto at = statement.rfind(oldName);
                    if (at == std::string::npos)
                        throw std::runtime_error("Cannot retain the definition's parameter name: " + actualName);
                    statement.replace(at, oldName.size(), actualName);
                }
            }
            const auto [start, end] = ParameterRange(node, before);
            changes.push_back({start, end, Join(replacement)});
        }
        if (!newName.empty())
        {
            const auto& name = node.at("loc");
            const auto start = Offset(name);
            changes.push_back({start, start + name.at("tokLen").get<std::size_t>(), newName});
        }
    };
    edit(declaration, declared, header, inlineDefinition);
    if (definition && !inlineDefinition)
    {
        const auto before = ReadBytes(unit);
        const auto defined = FindCppDeclaration(ast, symbol, definition->Location, before, true);
        edit(definition->Location, defined, before, true);
    }
    for (auto& [path, draft] : drafts)
    {
        auto& [before, changes] = draft;
        std::sort(changes.begin(), changes.end(), [](const auto& left, const auto& right) { return left.Start > right.Start; });
        auto after = before;
        auto limit = before.size();
        for (const auto& change : changes)
        {
            if (change.End > limit)
                throw std::runtime_error("The C++ signature locations overlap.");
            after.replace(change.Start, change.End - change.Start, change.Text);
            limit = change.Start;
        }
        if (after != before)
            result.Edits.push_back({path, std::move(before), std::move(after)});
    }
    return result;
}

SourceEdit EditFunctionBody(const NativeProject& project, const Symbol& symbol, const std::string& body)
{
    if (symbol.Kind != "function" || body.size() < 2 || body.front() != '{' || body.back() != '}')
        throw std::runtime_error("Provide a function body enclosed in braces.");
    const auto location = ReadDefinition(project, symbol).Location;
    auto before = ReadBytes(location.Path);
    const auto declaration = FindCppDeclaration(ReadCppDeclarations(project, location.Path, symbol.Name),
                                                symbol, location, before, true);
    const auto& range = Child(declaration, "CompoundStmt")->at("range");
    const auto start = Offset(range.at("begin"));
    auto after = before;
    after.replace(start, End(range) - start, body);
    return {location.Path, std::move(before), std::move(after)};
}

SourceEdit AddMember(const NativeProject& project, const Symbol& symbol, const std::string& declaration)
{
    if ((symbol.Kind != "class" && symbol.Kind != "struct") || declaration.empty() || declaration.back() != ';')
        throw std::runtime_error("Provide a member declaration ending in a semicolon and a target class or struct.");
    const auto location = DeclarationLocation(project, symbol);
    auto before = ReadBytes(location.Path);
    const auto record = FindCppDeclaration(ReadCppDeclarations(project, location.Path, symbol.Name), symbol, location, before);
    const auto end = Offset(record.at("range").at("end"));
    const auto newline = before.find("\r\n") == std::string::npos ? "\n" : "\r\n";
    const auto addition = std::string(newline) + "    " + declaration + newline;
    auto after = before;
    after.insert(end, addition);
    const auto updated = FindCppDeclaration(ReadCppDeclarations(project, location.Path, symbol.Name, &after),
                                            symbol, location, after);
    if (Offset(updated.at("range").at("end")) != end + addition.size())
        throw std::runtime_error("The new declaration must remain inside the target class.");
    return {location.Path, std::move(before), std::move(after)};
}
}

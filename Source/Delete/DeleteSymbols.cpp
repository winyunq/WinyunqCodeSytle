#include "DeleteSymbols.h"

#include "Read/ReadDeclaration.h"
#include "Read/ReadDefinition.h"
#include "Write/EditDocumentation.h"

#include <algorithm>
#include <map>
#include <regex>
#include <sstream>
#include <stdexcept>
#include <tuple>

namespace WinyunqCodeSytle
{
namespace
{
using Range = std::pair<std::size_t, std::size_t>;

std::size_t LineStart(std::string_view source, unsigned line)
{
    std::size_t offset = 0;
    for (unsigned current = 1; current < line; ++current)
    {
        offset = source.find('\n', offset);
        if (offset == std::string_view::npos)
            throw std::runtime_error("Doxygen declaration is outside the source file.");
        ++offset;
    }
    return offset;
}

}

SymbolDeletion PreviewSymbolDeletion(const NativeProject& project, const fs::path& index,
                                     const std::vector<Symbol>& symbols)
{
    std::map<fs::path, std::vector<Range>> ranges;
    std::map<fs::path, std::string> originals;
    std::map<std::string, std::string> names;
    std::vector<std::tuple<fs::path, Range, std::string>> declarations;
    const auto record = [&](const fs::path& path, const Range span, const std::string& name) {
        ranges[path].push_back(span);
        declarations.emplace_back(path, span, name);
    };
    const auto sourceAt = [&](const fs::path& path) -> const std::string& {
        auto [entry, inserted] = originals.try_emplace(path);
        if (inserted)
            entry->second = ReadBytes(path);
        return entry->second;
    };
    for (const auto& symbol : symbols)
    {
        const auto declaration = DeclarationLocation(project, symbol);
        names.emplace(symbol.Id, symbol.Name);
        const auto location = symbol.Node.child("location");
        const auto body = location.attribute("bodyfile");
        const auto bodyStart = location.attribute("bodystart").as_uint();
        const auto bodyEnd = location.attribute("bodyend").as_uint();
        const auto unit = body && bodyStart ? project.Resolve(fs::u8path(body.value())) : declaration.Path;
        const auto ast = ReadCppDeclarations(project, unit, symbol.Name);
        const auto recordDeclaration = [&](const SourceLocation& position, bool implementation) {
            const auto& source = sourceAt(position.Path);
            const auto node = FindCppDeclaration(ast, symbol, position, source, implementation && symbol.Kind == "function");
            const auto& range = node.at("range");
            auto start = range.at("begin").at("offset").get<std::size_t>();
            const auto last = range.at("end");
            auto end = last.at("offset").get<std::size_t>() + last.at("tokLen").get<std::size_t>();
            const auto terminator = source.find_first_not_of(" \t\r\n", end);
            if (terminator != std::string::npos && source[terminator] == ';' && !(symbol.Kind == "function" && implementation))
                end = terminator + 1;
            if (symbol.Kind == "variable")
            {
                if (terminator == std::string::npos || source[terminator] != ';')
                    throw std::runtime_error("The selected variable shares a declaration with another object.");
                for (const auto sibling : symbol.Node.parent().children("memberdef"))
                {
                    const auto location = sibling.child("location");
                    if (sibling == symbol.Node || !location.attribute("column") || !location.attribute("line") ||
                        fs::weakly_canonical(fs::u8path(location.attribute("file").value())) != position.Path)
                        continue;
                    const auto offset = LineStart(source, location.attribute("line").as_uint()) +
                        location.attribute("column").as_uint() - 1;
                    if (offset >= start && offset < end)
                        throw std::runtime_error("The selected variable shares a declaration with another object.");
                }
            }
            const auto previous = start ? source.rfind('\n', start - 1) : std::string::npos;
            const auto line = previous == std::string::npos ? 0 : previous + 1;
            if (source.find_first_not_of(" \t", line) == start)
                start = DocumentationRange(source, line).first;
            record(position.Path, {start, end}, symbol.Name);
        };
        bool includesDeclaration = false;
        if (body && bodyStart)
        {
            const auto definition = bodyEnd >= bodyStart ? ReadDefinition(project, symbol).Location :
                SourceLocation{project.Resolve(fs::u8path(body.value())), bodyStart};
            recordDeclaration(definition, bodyEnd >= bodyStart);
            includesDeclaration = definition.Path == declaration.Path &&
                declaration.Line >= definition.Line && declaration.Line <= std::max(bodyStart, bodyEnd);
        }
        if (!includesDeclaration)
            recordDeclaration(declaration, false);
    }

    SymbolDeletion result;
    for (auto& [path, spans] : ranges)
    {
        std::sort(spans.begin(), spans.end());
        std::vector<Range> merged;
        for (const auto& span : spans)
        {
            if (!merged.empty() && span.first <= merged.back().second)
                merged.back().second = std::max(merged.back().second, span.second);
            else
                merged.push_back(span);
        }
        const auto& before = originals.at(path);
        auto after = before;
        for (auto span = merged.rbegin(); span != merged.rend(); ++span)
            after.erase(span->first, span->second - span->first);
        result.Edits.push_back({path, before, std::move(after)});
    }

    pugi::xml_document catalog;
    if (!catalog.load_file((index / "index.xml").c_str()))
        throw std::runtime_error("Cannot read Doxygen's symbol index.");
    std::vector<fs::path> units;
    for (const auto entry : catalog.child("doxygenindex").children("compound"))
    {
        if (std::string_view(entry.attribute("kind").value()) != "file")
            continue;
        pugi::xml_document file;
        if (!file.load_file((index / (std::string(entry.attribute("refid").value()) + ".xml")).c_str()))
            throw std::runtime_error("Cannot read the indexed C++ file.");
        const auto compound = file.child("doxygen").child("compounddef");
        const auto path = project.Resolve(fs::u8path(compound.child("location").attribute("file").value()));
        const auto extension = path.extension().string();
        if (!compound.child("includedby") || extension == ".cpp" || extension == ".cc" || extension == ".cxx")
            units.push_back(path);
    }
    if (units.empty())
        for (const auto& [path, spans] : ranges)
            units.push_back(path);
    std::vector<std::string> targets;
    for (const auto& [id, name] : names)
        if (std::find(targets.begin(), targets.end(), name) == targets.end())
            targets.push_back(name);
    std::istringstream uses(project.QueryCppReferences(units, targets));
    static const std::regex location(R"place(^(.+):([0-9]+):([0-9]+): note: "(decl|use)" binds here\s*$)place");
    std::string target;
    for (std::string line; std::getline(uses, line); )
    {
        if (line.rfind("Match #", 0) == 0)
            target.clear();
        std::smatch binding;
        if (!std::regex_match(line, binding, location))
            continue;
        const auto path = fs::weakly_canonical(fs::u8path(binding[1].str()));
        const auto row = static_cast<unsigned>(std::stoul(binding[2].str()));
        const auto column = std::stoul(binding[3].str());
        const auto found = ranges.find(path);
        const auto offset = found == ranges.end() ? 0 : LineStart(originals.at(path), row) + column - 1;
        const bool removed = found != ranges.end() && std::any_of(found->second.begin(), found->second.end(),
            [&](const auto& span) { return offset >= span.first && offset < span.second; });
        if (binding[4] == "decl")
        {
            if (removed)
                for (const auto& [file, span, symbol] : declarations)
                    if (file == path && offset >= span.first && offset < span.second)
                    {
                        target = symbol;
                        break;
                    }
        }
        else if (!target.empty() && !removed)
            result.References.push_back({path.lexically_relative(project.Root), row, target});
    }
    std::sort(result.References.begin(), result.References.end(), [](const auto& a, const auto& b) {
        return std::tie(a.File, a.Line, a.Symbol) < std::tie(b.File, b.Line, b.Symbol);
    });
    result.References.erase(std::unique(result.References.begin(), result.References.end()), result.References.end());
    return result;
}
}

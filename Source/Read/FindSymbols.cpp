#include "FindSymbols.h"

#include <stdexcept>
#include <unordered_set>

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

std::shared_ptr<pugi::xml_document> Load(const fs::path& path)
{
    auto document = std::make_shared<pugi::xml_document>();
    const auto bytes = ReadBytes(path);
    const auto parsed = document->load_buffer(bytes.data(), bytes.size(), pugi::parse_default | pugi::parse_ws_pcdata);
    if (!parsed)
        throw std::runtime_error("Cannot read Doxygen XML: " + std::string(parsed.description()));
    return document;
}

std::string ShortName(std::string_view name)
{
    const auto scope = name.rfind("::");
    return std::string(scope == std::string_view::npos ? name : name.substr(scope + 2));
}
}

std::vector<Symbol> FindSymbols(const fs::path& index, std::string_view name)
{
    const auto listing = Load(index / "index.xml");
    const auto shortName = ShortName(name.substr(0, name.find('(')));
    std::vector<Symbol> results;
    std::unordered_set<std::string> ids;
    for (auto compound : listing->child("doxygenindex").children("compound"))
    {
        const std::string ref = compound.attribute("refid").value();
        const std::string compoundName = compound.child_value("name");
        const auto kind = std::string_view(compound.attribute("kind").value());
        const bool matchCompound = kind != "file" && kind != "dir" && (name == ref || ShortName(compoundName) == shortName);
        bool matchMember = false;
        for (auto member : compound.children("member"))
            matchMember |= shortName == member.child_value("name") || name == member.attribute("refid").value();
        if (!matchCompound && !matchMember)
            continue;
        const auto document = Load(index / (ref + ".xml"));
        const auto definition = document->child("doxygen").child("compounddef");
        if (matchCompound && (name == ref || name == compoundName || name == shortName) && ids.insert(ref).second)
            results.push_back({ref, compoundName, std::string(kind), compoundName, document, definition});
        if (!matchMember)
            continue;
        for (auto section : definition.children("sectiondef"))
            for (auto node : section.children("memberdef"))
            {
                const std::string id = node.attribute("id").value();
                const std::string local = node.child_value("name");
                if (shortName != local && name != id)
                    continue;
                std::string qualified = node.child_value("qualifiedname");
                if (qualified.empty())
                    qualified = (kind == "file" ? "" : compoundName + "::") + local;
                const auto signature = qualified + Text(node.child("argsstring"));
                if ((name == id || name == local || name == qualified || name == signature) && ids.insert(id).second)
                    results.push_back({id, qualified, node.attribute("kind").value(), signature, document, node});
            }
    }
    return results;
}

Symbol SelectSymbol(const fs::path& index, std::string_view name)
{
    auto symbols = FindSymbols(index, name);
    if (symbols.empty())
        throw std::runtime_error("C++ symbol not found: " + std::string(name));
    if (symbols.size() != 1)
        throw std::runtime_error("Ambiguous C++ symbol. Select a qualified signature or index ID.");
    return std::move(symbols.front());
}
}

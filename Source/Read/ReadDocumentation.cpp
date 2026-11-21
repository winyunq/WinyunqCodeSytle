#include "ReadDocumentation.h"

#include <sstream>

namespace WinyunqCodeSytle
{
namespace
{
using nlohmann::json;

std::string Text(pugi::xml_node node, bool code = false)
{
    if (node.type() == pugi::node_pcdata || node.type() == pugi::node_cdata)
        return node.value();
    const std::string_view tag = node.name();
    if (tag == "sp")
        return " ";
    if (!code && (tag == "parameterlist" || tag == "simplesect" ||
                  tag == "programlisting" || tag == "internal"))
        return {};

    std::string result;
    for (const auto child : node.children())
        result += Text(child, code);
    return result;
}

std::string Prose(pugi::xml_node node)
{
    auto text = Text(node);
    constexpr std::string_view publication = "@ProductDocument";
    for (auto at = text.find(publication); at != std::string::npos; at = text.find(publication))
        text.erase(at, publication.size());
    std::istringstream words(text);
    std::string paragraph;
    for (std::string word; words >> word;)
    {
        if (!paragraph.empty())
            paragraph += ' ';
        paragraph += word;
    }
    return paragraph;
}

void Paragraphs(json& result, const char* field, pugi::xml_node node)
{
    for (const auto paragraph : node.children("para"))
        if (const auto text = Prose(paragraph); !text.empty())
            result[field].push_back(text);
}

std::string CompactCppExample(const std::string& code)
{
    std::istringstream lines(code);
    std::string result;
    std::string rawEnd;
    bool continuation = false;
    bool emitted = false;
    for (std::string line; std::getline(lines, line);)
    {
        const bool preserve = continuation || !rawEnd.empty();
        const auto last = line.find_last_not_of(" \t");
        continuation = last != std::string::npos && line[last] == '\\';
        for (std::size_t cursor = 0; cursor < line.size();)
        {
            if (!rawEnd.empty())
            {
                const auto close = line.find(rawEnd, cursor);
                if (close == std::string::npos)
                    break;
                cursor = close + rawEnd.size();
                rawEnd.clear();
            }
            const auto open = line.find("R\"", cursor);
            if (open == std::string::npos)
                break;
            const auto body = line.find('(', open + 2);
            if (body == std::string::npos || body - open - 2 > 16)
                break;
            rawEnd = ")" + line.substr(open + 2, body - open - 2) + "\"";
            cursor = body + 1;
        }
        if (!preserve)
        {
            const auto first = line.find_first_not_of(" \t");
            if (first == std::string::npos)
                continue;
            if (!continuation && rawEnd.empty())
                line.resize(last + 1);
            line.erase(0, first);
        }
        if (emitted)
            result += '\n';
        result += line;
        emitted = true;
    }
    return result;
}
}

nlohmann::json ReadDocumentation(const Symbol& symbol)
{
    auto result = json::object();
    const auto brief = Prose(symbol.Node.child("briefdescription"));
    if (!brief.empty())
        result["brief"] = brief;
    const auto detail = symbol.Node.child("detaileddescription");
    Paragraphs(result, "details", detail);
    Paragraphs(result, "implementation_notes", symbol.Node.child("inbodydescription"));
    for (const auto& selected : detail.select_nodes(".//parameterlist[not(ancestor::internal)]"))
    {
        const auto list = selected.node();
        const std::string_view kind = list.attribute("kind").value();
        const auto field = kind == "param" ? "parameters" : kind == "templateparam" ? "template_parameters" :
            kind == "retval" ? "return_values" : "exceptions";
        for (const auto item : list.children("parameteritem"))
        {
            const auto description = Prose(item.child("parameterdescription"));
            for (const auto name : item.child("parameternamelist").children("parametername"))
            {
                json parameter = {{"name", name.child_value()}};
                if (!description.empty())
                    parameter["description"] = description;
                if (const auto direction = name.attribute("direction"))
                    parameter["direction"] = direction.value();
                result[field].push_back(std::move(parameter));
            }
        }
    }
    for (const auto& selected : detail.select_nodes(".//simplesect[not(ancestor::internal)]"))
    {
        const auto section = selected.node();
        const std::string_view kind = section.attribute("kind").value();
        if (kind == "return") Paragraphs(result, "returns", section);
        else if (kind == "pre") Paragraphs(result, "preconditions", section);
        else if (kind == "post") Paragraphs(result, "postconditions", section);
        else if (kind == "note") Paragraphs(result, "notes", section);
        else if (kind == "warning") Paragraphs(result, "warnings", section);
        else if (kind == "see") Paragraphs(result, "see_also", section);
        else if (kind == "par")
        {
            auto block = json::object();
            const auto title = Prose(section.child("title"));
            if (!title.empty())
                block["title"] = title;
            Paragraphs(block, "paragraphs", section);
            if (!block.empty())
                result["sections"].push_back(std::move(block));
        }
    }
    for (const auto& selected : detail.select_nodes(".//programlisting[not(ancestor::internal)]"))
    {
        const auto listing = selected.node();
        std::string code;
        for (auto line = listing.child("codeline"); line; line = line.next_sibling("codeline"))
        {
            for (const auto highlight : line.children("highlight"))
                code += Text(highlight, true);
            if (line.next_sibling("codeline"))
                code += '\n';
        }
        const auto extension = fs::u8path(listing.attribute("filename").as_string()).extension().string();
        const auto language = std::string_view(listing.attribute("filename").as_string());
        if (language == ".cpp" || extension == ".cpp" || language == ".c" || extension == ".c")
            code = CompactCppExample(code);
        if (!code.empty())
            result["examples"].push_back(std::move(code));
    }
    return result;
}
}

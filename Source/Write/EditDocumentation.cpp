#include "EditDocumentation.h"
#include "Read/ReadDocumentation.h"

#include <optional>
#include <regex>
#include <stdexcept>

namespace WinyunqCodeSytle
{
std::pair<std::size_t, std::size_t> DocumentationRange(const std::string& before, std::size_t declaration)
{
    const auto firstToken = before.find_first_not_of(" \t", declaration);
    if (firstToken == std::string::npos)
        return {declaration, declaration};
    const auto indentation = before.substr(declaration, firstToken - declaration);
    auto documentationEnd = declaration;
    static const std::regex reflection(
        R"((?:^|\n)([ \t]*U(?:CLASS|STRUCT|ENUM|INTERFACE|FUNCTION|PROPERTY|DELEGATE)\([^;{}]*\)[ \t\r]*\n)$)");
    std::match_results<std::string::const_iterator> macro;
    if (std::regex_search(before.cbegin(), before.cbegin() + declaration, macro, reflection))
        documentationEnd = static_cast<std::size_t>(macro.position(1));

    auto start = documentationEnd;
    while (start)
    {
        auto previous = start > 1 ? before.rfind('\n', start - 2) : std::string::npos;
        previous = previous == std::string::npos ? 0 : previous + 1;
        if (before.compare(previous, indentation.size() + 3, indentation + "///") != 0)
            break;
        start = previous;
    }
    if (start == documentationEnd && start != 0)
    {
        const auto last = before.find_last_not_of(" \t\r\n", start - 1);
        if (last != std::string::npos && last != 0 && before.compare(last - 1, 2, "*/") == 0)
        {
            const auto opening = before.rfind("/*", last - 1);
            if (opening != std::string::npos &&
                (before.compare(opening, 3, "/**") == 0 || before.compare(opening, 3, "/*!") == 0) &&
                before.find("*/", opening + 2) == last - 1)
            {
                const auto line = opening ? before.rfind('\n', opening - 1) : std::string::npos;
                const auto beginning = line == std::string::npos ? 0 : line + 1;
                auto first = before.find_first_not_of(" \t", beginning);
                if (beginning == 0 && before.compare(0, 3, "\xEF\xBB\xBF") == 0)
                    first = before.find_first_not_of(" \t", 3);
                if (first == opening)
                    start = opening > 0 && beginning == 0 && first >= 3 &&
                            before.compare(0, 3, "\xEF\xBB\xBF") == 0 ? 3 : beginning;
            }
        }
    }
    return {start, documentationEnd};
}

namespace
{
std::size_t DeclarationOffset(const std::string& source, const SourceLocation& location)
{
    std::size_t declaration = 0;
    for (unsigned line = 1; line < location.Line; ++line)
    {
        declaration = source.find('\n', declaration);
        if (declaration == std::string::npos)
            throw std::runtime_error("Declaration line is outside the source file.");
        ++declaration;
    }
    const auto firstToken = source.find_first_not_of(" \t", declaration);
    if (firstToken == std::string::npos || source[firstToken] == '\n' ||
        source[firstToken] == '\r' || source[firstToken] == '{')
        throw std::runtime_error("Expected a declaration or definition signature at the indexed line.");
    return declaration;
}

std::string FormatDocumentation(std::string_view comment, const std::string& prefix, const char* newline)
{
    std::string formatted;
    while (!comment.empty())
    {
        const auto end = comment.find('\n');
        auto line = comment.substr(0, end);
        if (!line.empty() && line.back() == '\r')
            line.remove_suffix(1);
        if (line.find('\r') != std::string_view::npos || (!line.empty() && line.back() == '\\'))
            throw std::runtime_error("Documentation cannot contain a line continuation.");
        formatted += prefix;
        if (!line.empty())
        {
            formatted += ' ';
            formatted += line;
        }
        formatted += newline;
        if (end == std::string_view::npos)
            break;
        comment.remove_prefix(end + 1);
    }
    return formatted;
}

}

SourceEdit EditDocumentation(const NativeProject& project, const Symbol& symbol, std::string_view comment)
{
    return EditDocumentation(DeclarationLocation(project, symbol), comment);
}

/// @brief 在指定的声明或定义上预览 Doxygen 注释的新增或更新。
/// @details 输入是注释正文。函数在源码中生成行注释前缀并保留缩进和换行，将已有的连续文档行作为一个整体更新。Doxygen 在索引或导出时解析正文中的命令。
/// @param[in] location 由源码索引确定的目标文件和签名起始行。
/// @param[in] comment 注释正文。空正文用于删除现有的连续文档行。
/// @return 包含目标文件、修改前内容和修改后内容的预览。
///
/// @par 常用 Doxygen 命令
/// 命令可用 `@` 或反斜杠引入。本项目使用 `@`。用 `@brief` 写用途，`@details` 写处理方式，`@param[in]`、`@param[out]` 或 `@param[in,out]` 写参数方向与含义，`@tparam` 写模板参数，`@return` 写结果，`@retval` 分别说明具体返回值。
/// 有实际调用约定时用 `@pre` 和 `@post`，相关接口用 `@ref` 或 `@see`，补充说明用 `@note`，误用及后果用 `@warning`，代码示例由 `@code{.cpp}` 和 `@endcode` 包围。
///
/// @par 函数正文模板
/// @verbatim
/// @brief 一句话说明用途。
/// @details 简述输入如何处理、结果如何产生。
/// @param[in] input 参数含义及实际约束。
/// @return 返回值的含义。
/// @endverbatim
SourceEdit EditDocumentation(const SourceLocation& location, std::string_view comment)
{
    auto before = ReadBytes(location.Path);
    const auto declaration = DeclarationOffset(before, location);
    const auto indentation = before.substr(declaration, before.find_first_not_of(" \t", declaration) - declaration);
    const auto [start, documentationEnd] = DocumentationRange(before, declaration);
    const char* newline = before.find("\r\n") != std::string::npos ? "\r\n" : "\n";
    auto after = before;
    after.replace(start, documentationEnd - start, FormatDocumentation(comment, indentation + "///", newline));
    return {location.Path, std::move(before), std::move(after)};
}

namespace
{
struct FieldChange
{
    std::string Command;
    std::string Name;
    std::string Direction;
    std::string Before;
    std::optional<std::string> After;
};

SourceEdit PatchDocumentation(const SourceLocation& location, const std::vector<FieldChange>& changes)
{
    auto before = ReadBytes(location.Path);
    const auto declaration = DeclarationOffset(before, location);
    const auto indentation = before.substr(declaration, before.find_first_not_of(" \t", declaration) - declaration);
    const auto [start, end] = DocumentationRange(before, declaration);
    auto comment = before.substr(start, end - start);
    const auto opening = comment.find_first_not_of(" \t");
    const bool block = opening != std::string_view::npos && comment.substr(opening, 2) == "/*";
    const auto newline = before.find("\r\n") == std::string::npos ? "\n" : "\r\n";
    const auto prefix = indentation + (block ? " *" : "///");
    std::string additions;
    for (const auto& change : changes)
    {
        std::string value;
        if (change.After)
        {
            const auto& input = *change.After;
            const auto first = input.find_first_not_of(" \t\r\n");
            if (first == std::string::npos || input.find('\0') != std::string::npos)
                throw std::runtime_error("Provide a non-empty documentation field.");
            if (block && input.find("*/") != std::string::npos)
                throw std::runtime_error("Documentation cannot contain a comment terminator.");
            value = input.substr(first, input.find_last_not_of(" \t\r\n") - first + 1);
        }
        auto tag = change.Command;
        if (!change.Direction.empty())
            tag += '[' + change.Direction + ']';
        if (!change.Name.empty())
            tag += ' ' + change.Name;
        if (change.Before.empty())
        {
            if (change.After)
                additions += FormatDocumentation('@' + tag + ' ' + value, prefix, newline);
            continue;
        }
        // shortcut: match the indexed field's literal source text until the index includes field offsets.
        const auto find = [&](const std::string& parsed) {
            auto offset = std::string::npos;
            for (const char marker : {'@', '\\'})
            {
                const auto literal = marker + tag + ' ' + parsed;
                const auto at = comment.find(literal);
                if (at == std::string::npos)
                    continue;
                if (offset != std::string::npos || comment.find(literal, at + 1) != std::string::npos)
                    throw std::runtime_error("The Doxygen field matches multiple source fragments.");
                offset = at;
            }
            return offset;
        };
        auto old = change.Before;
        auto offset = find(old);
        if (change.Command == "brief" && offset == std::string::npos && old.back() == '.')
        {
            old.pop_back();
            offset = find(old);
        }
        if (old.empty() || offset == std::string::npos)
            throw std::runtime_error("The indexed Doxygen field does not match a source fragment: " + tag);
        const auto body = offset + tag.size() + 2;
        if (change.After)
        {
            auto replacement = FormatDocumentation(value, prefix, newline);
            replacement.erase(0, prefix.size() + 1);
            replacement.resize(replacement.size() - std::char_traits<char>::length(newline));
            comment.replace(body, old.size(), replacement);
        }
        else
        {
            const auto previous = offset ? comment.rfind('\n', offset - 1) : std::string::npos;
            const auto line = previous == std::string::npos ? 0 : previous + 1;
            const auto next = comment.find('\n', body + old.size());
            if (next != std::string::npos && comment.substr(line, offset - line) == prefix + ' ' &&
                comment.find_first_not_of(" \t\r", body + old.size()) == next)
                comment.erase(line, next + 1 - line);
            else
                comment.erase(offset, body + old.size() - offset);
        }
    }
    if (!additions.empty())
    {
        if (block)
        {
            const auto close = comment.rfind("*/");
            const auto separator = comment.rfind('\n', close);
            const auto line = separator == std::string::npos ? 0 : separator + 1;
            if (comment.substr(line, close - line).find_first_not_of(" \t") == std::string::npos)
                comment.insert(line, additions);
            else
                comment.insert(close, (close == opening + 2 ? "*" : "") + std::string(newline) +
                    additions + indentation + ' ');
        }
        else
            comment += additions;
    }
    auto after = before;
    after.replace(start, end - start, comment);
    return {location.Path, std::move(before), std::move(after)};
}

FieldChange ParameterChange(const nlohmann::json& parameters, const std::string& name,
                            std::optional<std::string> text)
{
    for (const auto& parameter : parameters)
        if (parameter.value("name", "") == name)
        {
            auto direction = parameter.value("direction", "");
            if (direction == "inout")
                direction = "in,out";
            return {"param", name, std::move(direction), parameter.value("description", ""), std::move(text)};
        }
    return {"param", name, "", "", std::move(text)};
}
}

SourceEdit EditDocumentation(const SourceLocation& location, const Symbol& symbol, const nlohmann::json& fields)
{
    if (!fields.is_object() || fields.empty())
        throw std::runtime_error("Provide a non-empty object of documentation fields.");
    const auto indexed = ReadDocumentation(symbol);
    std::vector<FieldChange> changes;
    for (const auto& [field, value] : fields.items())
    {
        if (field == "brief")
            changes.push_back({"brief", "", "", indexed.value("brief", ""), value.get<std::string>()});
        else if (field == "params" && value.is_object() && !value.empty())
        {
            static const std::regex identifier("[A-Za-z_][A-Za-z_0-9]*");
            const auto parameters = indexed.value("parameters", nlohmann::json::array());
            for (const auto& [name, description] : value.items())
            {
                if (!std::regex_match(name, identifier))
                    throw std::runtime_error("Provide a C++ parameter name.");
                changes.push_back(ParameterChange(parameters, name, description.get<std::string>()));
            }
        }
        else
            throw std::runtime_error("Unsupported documentation field: " + field);
    }
    return PatchDocumentation(location, changes);
}

SourceEdit RemoveParameterComments(const SourceLocation& location, const Symbol& symbol,
                                     const std::vector<std::string>& names)
{
    const auto parameters = ReadDocumentation(symbol).value("parameters", nlohmann::json::array());
    std::vector<FieldChange> changes;
    for (const auto& name : names)
        changes.push_back(ParameterChange(parameters, name, std::nullopt));
    return PatchDocumentation(location, changes);
}
}

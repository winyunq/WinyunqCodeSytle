#include "GenerateWebsite.h"
#include "WebsiteStyle.h"

#include <algorithm>
#include <cctype>
#include <fstream>
#include <map>
#include <memory>
#include <regex>
#include <set>
#include <sstream>
#include <stdexcept>
#include <tuple>

#include <pugixml.hpp>

#ifdef _WIN32
#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#include <bcrypt.h>
#else
#include <openssl/sha.h>
#endif

namespace WinyunqCodeSytle
{
namespace
{
using nlohmann::json;

void Write(const fs::path& path, std::string_view text)
{
    fs::create_directories(path.parent_path());
    std::ofstream output(path, std::ios::binary | std::ios::trunc);
    output.exceptions(std::ios::badbit | std::ios::failbit);
    output << text;
    output.close();
}

std::string Escape(std::string_view text)
{
    std::string result;
    for (const auto character : text)
    {
        switch (character)
        {
        case '&': result += "&amp;"; break;
        case '<': result += "&lt;"; break;
        case '>': result += "&gt;"; break;
        case '"': result += "&quot;"; break;
        case '\'': result += "&#39;"; break;
        default: result += character; break;
        }
    }
    return result;
}

std::string Url(std::string_view text)
{
    constexpr char hex[] = "0123456789ABCDEF";
    std::string result;
    for (const unsigned char character : text)
    {
        if (character <= ' ' || character == 0x7f || std::string_view("#?%\\").find(character) != std::string_view::npos)
        {
            result += '%';
            result += hex[character >> 4];
            result += hex[character & 15];
        }
        else
            result += static_cast<char>(character);
    }
    return result;
}

std::string SiteRoot(std::string_view page)
{
    std::string root;
    for (const auto character : page)
        if (character == '/')
            root += "../";
    return root;
}

std::string Text(pugi::xml_node node)
{
    if (node.type() == pugi::node_pcdata || node.type() == pugi::node_cdata)
        return node.value();
    if (std::string_view(node.name()) == "sp")
        return " ";
    std::string text;
    for (const auto child : node.children())
        text += Text(child);
    return text;
}

std::string Normalize(std::string_view text)
{
    std::istringstream words{std::string(text)};
    std::string result;
    for (std::string word; words >> word; )
    {
        if (!result.empty())
            result += ' ';
        result += word;
    }
    return result;
}

std::string Hash(std::string_view text)
{
    unsigned char digest[32]{};
#ifdef _WIN32
    static const struct Provider
    {
        BCRYPT_ALG_HANDLE Handle{};
        Provider()
        {
            if (BCryptOpenAlgorithmProvider(&Handle, BCRYPT_SHA256_ALGORITHM, nullptr, 0) < 0)
                throw std::runtime_error("Cannot open the SHA-256 provider.");
        }
        ~Provider() { BCryptCloseAlgorithmProvider(Handle, 0); }
    } provider;
    if (BCryptHash(provider.Handle, nullptr, 0, reinterpret_cast<PUCHAR>(const_cast<char*>(text.data())),
                   static_cast<ULONG>(text.size()), digest, sizeof(digest)) < 0)
        throw std::runtime_error("Cannot compute the website identifier.");
#else
    if (!SHA256(reinterpret_cast<const unsigned char*>(text.data()), text.size(), digest))
        throw std::runtime_error("Cannot compute the website identifier.");
#endif
    constexpr char hex[] = "0123456789abcdef";
    std::string result;
    for (const auto byte : digest)
    {
        result += hex[byte >> 4];
        result += hex[byte & 15];
    }
    return result;
}

std::string SourceHash(std::string_view text)
{
    return Hash(Normalize(text));
}

std::regex Glob(std::string pattern)
{
    std::replace(pattern.begin(), pattern.end(), '\\', '/');
    const auto path = fs::u8path(pattern);
    if (path.has_root_path() || std::find(path.begin(), path.end(), fs::path("..")) != path.end())
        throw std::runtime_error("Documentation globs must be relative to the project.");
    std::string expression;
    for (std::size_t i = 0; i < pattern.size(); ++i)
    {
        const auto character = pattern[i];
        if (pattern.compare(i, 3, "**/") == 0)
        {
            expression += "(?:.*/)?";
            i += 2;
        }
        else if (pattern.compare(i, 2, "**") == 0)
        {
            expression += ".*";
            ++i;
        }
        else if (character == '*')
            expression += "[^/]*";
        else if (character == '?')
            expression += "[^/]";
        else
        {
            if (std::string_view(R"(\.^$|()[]{}+)").find(character) != std::string_view::npos)
                expression += '\\';
            expression += character;
        }
    }
    return std::regex(expression);
}

bool Header(const fs::path& path)
{
    const auto extension = path.extension().string();
    return extension == ".h" || extension == ".hh" || extension == ".hpp" || extension == ".hxx";
}

bool DocumentationSource(const fs::path& path)
{
    return Header(path) || path.extension() == ".py" || path.extension() == ".dox";
}

void AppendProjectMcpInputs(const NativeProject& project, json& inputs, std::vector<fs::path>& files)
{
    const auto plugins = project.Root / "Plugins";
    if (!fs::is_directory(plugins))
        return;

    std::set<std::string> enabled;
    for (const auto& entry : fs::directory_iterator(project.Root))
    {
        if (!entry.is_regular_file() || entry.path().extension() != ".uproject")
            continue;
        const auto descriptor = json::parse(ReadBytes(entry.path()));
        for (const auto& plugin : descriptor.value("Plugins", json::array()))
            if (plugin.value("Enabled", false))
                enabled.insert(plugin.at("Name").get<std::string>());
    }
    for (const auto& entry : fs::directory_iterator(plugins))
    {
        const auto scripts = entry.path() / "Resources/Python";
        if (!fs::is_directory(scripts))
            continue;
        for (const auto& descriptor : fs::directory_iterator(entry.path()))
        {
            if (descriptor.path().extension() != ".uplugin" ||
                !enabled.count(descriptor.path().stem().u8string()))
                continue;
            const auto relative = entry.path().lexically_relative(project.Root).generic_u8string();
            inputs.push_back(relative + "/Resources/Python/*McpServer.py");
            inputs.push_back(relative + "/Source/*/Public/**/*.h");
            for (const auto& script : fs::directory_iterator(scripts))
                if (!script.is_symlink() && script.is_regular_file() && script.path().extension() == ".py")
                    files.push_back(script.path());
            const auto source = entry.path() / "Source";
            if (fs::is_directory(source))
                for (const auto& module : fs::directory_iterator(source))
                {
                    const auto headers = module.path() / "Public";
                    if (fs::is_directory(headers))
                        for (const auto& header : fs::recursive_directory_iterator(headers))
                            if (!header.is_symlink() && header.is_regular_file() && Header(header.path()))
                                files.push_back(header.path());
                }
            break;
        }
    }
}

bool FileNameLess(const fs::path& left, const fs::path& right)
{
#ifdef _WIN32
    return CompareStringOrdinal(left.c_str(), -1, right.c_str(), -1, TRUE) == CSTR_LESS_THAN;
#else
    return left < right;
#endif
}

struct Group
{
    std::string Id;
    json Title;
    std::vector<std::pair<std::regex, std::regex>> Selectors;
    std::set<fs::path> Files;
};

std::vector<Group> Groups(const NativeProject& project, const json& config, bool publicView)
{
    auto groups = config.value(publicView ? "groups" : "developer_groups", json::array());
    const bool implicitGroup = groups.empty();
    std::vector<fs::path> files;
    if (implicitGroup)
    {
        auto fallback = publicView ? json::array({"Source/**/*.h", "Source/**/*.hpp", "Docs/**/*.dox"}) :
            json::array({"Source/**/*.cpp", "Source/**/*.h", "Source/**/*.hpp"});
        if (publicView && !config.contains("user_inputs"))
        {
            AppendProjectMcpInputs(project, fallback, files);
            const auto docs = project.Root / "Docs";
            if (fs::is_directory(docs))
                for (const auto& note : fs::recursive_directory_iterator(docs))
                    if (!note.is_symlink() && note.is_regular_file() && note.path().extension() == ".dox")
                        files.push_back(note.path());
        }
        groups.push_back({{"id", ""},
                          {"headers", config.value(publicView ? "user_inputs" : "developer_inputs", fallback)}});
    }
    std::set<fs::path, decltype(&FileNameLess)> ids(&FileNameLess);
    ids.emplace("index");
    static const std::regex identifier("[A-Za-z][A-Za-z0-9_-]*");
    std::vector<Group> result;
    for (const auto& group : groups)
    {
        const auto id = group.at("id").get<std::string>();
        if (!implicitGroup && (!std::regex_match(id, identifier) || !ids.emplace(id).second))
            throw std::runtime_error("Invalid or duplicate documentation group: " + id);
        Group selected{id, group.value("title", json(id)), {}, {}};
        const auto symbols = group.value("symbols_regex", ".*");
        for (const auto& entry : group.value("headers", json::array()))
            selected.Selectors.emplace_back(Glob(entry.is_string() ? entry.get<std::string>() : entry.at("glob").get<std::string>()),
                entry.is_string() ? symbols : entry.value("symbols_regex", symbols));
        result.push_back(std::move(selected));
    }
    const auto source = project.Root / "Source";
    if (fs::is_directory(source))
        for (const auto& entry : fs::recursive_directory_iterator(source))
            if (!entry.is_symlink() && entry.is_regular_file())
                files.push_back(entry.path());
    for (const auto& file : files)
    {
        const auto relative = file.lexically_relative(project.Root).generic_u8string();
        for (auto& group : result)
        {
            const auto matched = std::any_of(group.Selectors.begin(), group.Selectors.end(), [&](const auto& selector) {
                return std::regex_match(relative, selector.first);
            });
            if (!matched)
                continue;
            if (publicView && !DocumentationSource(file))
                throw std::runtime_error("Unsupported public documentation source: " + relative);
            if (publicView && implicitGroup && !config.contains("user_inputs") &&
                ReadBytes(file).find("@ProductDocument") == std::string::npos)
                continue;
            group.Files.insert(project.Resolve(file));
        }
    }
    return result;
}

struct Labels
{
    const char *Start, *Overview, *Contents, *Version, *Search, *Skip, *Open, *Empty,
        *Members, *Name, *Type, *Description, *Inputs, *Returns, *Function, *Calling,
        *Current, *Header, *Implementation, *Notice, *Warning, *File, *Class;
};
const Labels English{"Documentation", "Overview", "On this page", "Version",
    "Search this documentation", "Skip to content", "Open files", "No files in this folder.", "Members",
    "Name", "Type", "Description", "Inputs", "Return value", "Function", "Invocation", "Current function",
    "Header", "Implementation", "Note", "Warning", "File", "Class"};
const Labels Chinese{"文档目录", "概述", "本页内容", "版本", "搜索文档", "跳至正文",
    "查看文件", "此文件夹暂无文件。", "成员", "名称", "类型", "说明", "输入", "返回值", "函数",
    "调用方式", "当前函数", "头文件", "实现文件", "说明", "警告", "文件", "类"};

struct Language
{
    std::string Code, Source;
    std::map<std::string, json> Memory;
    std::map<std::string, std::string> Reusable;
    json Localizations = json::object();

    const Labels& Words() const { return Code == "zh-CN" ? Chinese : English; }

    std::string Translate(const std::string& id, const std::string& input, std::string seed = {}) const
    {
        auto text = Normalize(input);
        for (auto marker = text.find("@ProductDocument"); marker != std::string::npos; marker = text.find("@ProductDocument"))
            text.erase(marker, std::string_view("@ProductDocument").size());
        text = Normalize(text);
        const auto bilingual = text.find(" / ");
        if (bilingual != std::string::npos &&
            std::any_of(text.begin() + bilingual + 3, text.end(), [](unsigned char c) { return c >= 0xe3 && c <= 0xe9; }))
        {
            if (Code == "zh-CN")
                seed = text.substr(bilingual + 3);
            text.erase(bilingual);
        }
        if (Code == Source || text.empty())
            return seed.empty() || Code == Source ? text : seed;
        const auto hash = SourceHash(text);
        if (const auto row = Memory.find(id); row != Memory.end() &&
            row->second.value("translated_source_hash", "") == hash && !row->second.value("translation", "").empty())
            return row->second.at("translation").get<std::string>();
        if (!seed.empty())
            return seed;
        if (const auto translated = Reusable.find(hash); translated != Reusable.end())
            return translated->second;
        return text;
    }

    std::string LocalName(const char* category, const std::string& key, const std::string& fallback) const
    {
        if (const auto list = Localizations.find(category); list != Localizations.end() && list->contains(key))
        {
            const auto& value = list->at(key);
            if (value.is_string())
                return value.get<std::string>();
            return value.value("name", fallback);
        }
        return fallback;
    }
};

Language ReadLanguage(const NativeProject& project, const json& config, const std::string& code)
{
    Language result{code, config.value("source_language", "en"), {}, {}};
    const auto localizations = config.value("blueprint_localizations", json::object());
    if (localizations.contains(code))
        result.Localizations = json::parse(ReadBytes(project.Resolve(fs::u8path(localizations.at(code).get<std::string>()))));
    if (code == result.Source)
        return result;
    const auto memory = project.Resolve(fs::u8path(config.value("translation_directory", "Documentation/Translations")) /
                                        (code + ".json"));
    if (fs::is_regular_file(memory))
        for (const auto& row : json::parse(ReadBytes(memory)))
        {
            result.Memory.emplace(row.at("id").get<std::string>(), row);
            const auto text = row.value("translation", "");
            const auto hash = row.value("translated_source_hash", "");
            if (!text.empty() && !hash.empty() && hash == row.value("source_hash", ""))
                result.Reusable.emplace(hash, text);
        }
    return result;
}

std::string GroupTitle(const Group& group, const Language& language)
{
    return group.Title.is_string() ? group.Title.get<std::string>() :
        group.Title.value(language.Code, group.Title.value(language.Source, group.Id));
}

struct Record
{
    std::string Id, Name, Leaf, Scope, Signature, Page, GroupId, Anchor;
    pugi::xml_node Node;
    std::string ToolName;
};

struct Page
{
    std::string Path, Title, DoxygenId;
    fs::path File;
    std::map<std::string, std::vector<Record*>> Sections;
    pugi::xml_node Overview;
};

std::string AnchorName(std::string_view name)
{
    auto anchor = Normalize(name);
    std::replace(anchor.begin(), anchor.end(), ' ', '-');
    return anchor;
}

std::string SectionAnchor(const std::string& scope)
{
    return scope.empty() ? "members" : "class-" + AnchorName(scope);
}

std::string RecordUrl(const std::string& current, const Record& target)
{
    const auto page = current == target.Page ? "" : SiteRoot(current) + Url(target.Page);
    return page + '#' + Url(target.Anchor);
}

std::string RecordLink(const std::string& current, const Record& target)
{
    return Escape(RecordUrl(current, target));
}

std::string Html(pugi::xml_node node)
{
    std::ostringstream html;
    node.print(html, "", pugi::format_raw | pugi::format_no_empty_element_tags);
    return html.str();
}

struct Website
{
    std::vector<Group> Groups;
    std::vector<std::unique_ptr<pugi::xml_document>> Compounds;
    std::map<std::string, Record> Records;
    std::map<std::string, const Record*> References;
    std::map<std::string, pugi::xml_node> Classes;
    std::vector<Page> Pages;
    pugi::xml_node Overview;
    std::vector<pugi::xml_node> AnnotatedPages;
    fs::path HtmlDirectory;
    std::map<std::string, std::unique_ptr<pugi::xml_document>> HtmlDocuments;
    std::map<std::string, std::string> FilePages;
    std::string MathScripts, MermaidScript;
};

Website ReadIndex(const NativeProject& project, const fs::path& index, std::vector<Group> groups,
                  bool publicView, bool explicitPublicScope)
{
    Website website;
    website.Groups = std::move(groups);
    std::map<fs::path, Page> pages;
    for (const auto& group : website.Groups)
        for (const auto& file : group.Files)
            pages.try_emplace(file, Page{{}, file.stem().u8string(), {}, file, {}, {}});
    bool markedPublic = false;
    if (!index.empty())
    {
        website.HtmlDirectory = index.parent_path() / "html";
        pugi::xml_document list;
        if (!list.load_file((index / "index.xml").c_str()))
            throw std::runtime_error("Cannot read Doxygen's website index.");
        for (const auto entry : list.child("doxygenindex").children("compound"))
        {
            auto document = std::make_unique<pugi::xml_document>();
            const std::string refid = entry.attribute("refid").value();
            const auto file = index / (refid + ".xml");
            if (!document->load_file(file.c_str()))
                throw std::runtime_error("Cannot read Doxygen documentation: " + file.generic_u8string());
            const auto compound = document->child("doxygen").child("compounddef");
            const std::string_view kind = compound.attribute("kind").value();
            if (kind == "page" && Published(compound))
            {
                if (std::string_view(compound.attribute("id").value()) == "indexpage")
                    website.Overview = compound;
                else
                    website.AnnotatedPages.push_back(compound);
            }
            if (kind == "class" || kind == "struct")
                website.Classes.emplace(compound.child_value("compoundname"), compound);
            if (kind == "file" && compound.child("location").attribute("file"))
            {
                const auto source = fs::weakly_canonical(project.Root /
                    fs::u8path(compound.child("location").attribute("file").value()));
                if (auto target = pages.find(source); target != pages.end())
                {
                    target->second.Overview = compound;
                    target->second.DoxygenId = refid;
                }
            }
            website.Compounds.push_back(std::move(document));
            const auto htmlFile = website.HtmlDirectory / (refid == "indexpage" ? "index.html" : refid + ".html");
            if (!fs::is_regular_file(htmlFile))
                continue;
            auto html = std::make_unique<pugi::xml_document>();
            const auto parsed = html->load_file(htmlFile.c_str(), pugi::parse_default | pugi::parse_ws_pcdata);
            if (!parsed)
                throw std::runtime_error("Cannot read Doxygen HTML: " + htmlFile.generic_u8string() + " (" + parsed.description() + ')');
            if (website.MathScripts.empty() || website.MermaidScript.empty())
            {
                const auto head = html->child("html").child("head");
                for (const auto script : head.children("script"))
                {
                    if (script.attribute("id").as_string() == std::string_view("MathJax-script"))
                        website.MathScripts = Html(script.previous_sibling("script")) + Html(script);
                    if (std::string_view(script.child_value()).find("mermaid.initialize") != std::string_view::npos)
                        website.MermaidScript = Html(script);
                }
            }
            website.HtmlDocuments.emplace(refid, std::move(html));
        }

        markedPublic = publicView && website.Overview;
        for (const auto& document : website.Compounds)
        {
            const auto compound = document->child("doxygen").child("compounddef");
            const std::string owner = compound.child_value("compoundname");
            const std::string_view ownerKind = compound.attribute("kind").value();
            const auto add = [&](pugi::xml_node node) {
                const std::string_view kind = node.attribute("kind").value();
                if (kind != "function" && kind != "variable" && kind != "enum" && kind != "typedef" &&
                    kind != "class" && kind != "struct" && kind != "namespace")
                    return;
                if (publicView && (std::string_view(node.attribute("prot").as_string("public")) != "public" ||
                    ((markedPublic || !explicitPublicScope) && !Published(node))))
                    return;
                const auto location = node.child("location");
                if (!location.attribute("file") || !*location.attribute("file").value())
                    return;
                const auto file = fs::weakly_canonical(project.Root / fs::u8path(location.attribute("file").value()));
                auto name = node == compound ? owner : std::string(node.child_value("qualifiedname"));
                if (name.empty())
                    name = (ownerKind == "class" || ownerKind == "struct" || ownerKind == "namespace" ? owner + "::" : "") +
                        node.child_value("name");
                const auto scopeAt = name.rfind("::");
                const auto leaf = node == compound ? (scopeAt == std::string::npos ? name : name.substr(scopeAt + 2)) :
                    std::string(node.child_value("name"));
                const auto relative = file.lexically_relative(project.Root).generic_u8string();
                for (const auto& group : website.Groups)
                {
                    if (!group.Files.count(file) || std::none_of(group.Selectors.begin(), group.Selectors.end(), [&](const auto& selector) {
                            return std::regex_match(relative, selector.first) && std::regex_search(name, selector.second);
                        }))
                        continue;
                    const auto signature = std::string(node.child("definition").text().as_string(name.c_str())) +
                        node.child_value("argsstring");
                    const auto id = SourceHash(name + '\n' + signature).substr(0, 24);
                    auto scope = website.Classes.count(name) ? name : scopeAt != std::string::npos ? name.substr(0, scopeAt) : "";
                    if (!website.Classes.count(scope))
                        scope.clear();
                    auto page = pages.find(file);
                    if (!publicView && location.attribute("bodyfile"))
                    {
                        const auto body = fs::weakly_canonical(project.Root / fs::u8path(location.attribute("bodyfile").value()));
                        if (group.Files.count(body))
                            page = pages.find(body);
                    }
                    std::string toolName;
                    if (markedPublic && kind == "function" && leaf.rfind("MCP_", 0) == 0)
                    {
                        static const std::regex toolBrief(R"(([a-z][a-z0-9]*(?:_[a-z0-9]+)+) .+)");
                        const auto brief = Normalize(Text(node.child("briefdescription")));
                        std::smatch match;
                        if (std::regex_match(brief, match, toolBrief))
                            toolName = match[1].str();
                    }
                    const auto [record, inserted] = website.Records.try_emplace(id,
                        Record{id, name, leaf, scope, signature, {}, group.Id, {}, node, std::move(toolName)});
                    website.References[node.attribute("id").value()] = &record->second;
                    if (inserted)
                        page->second.Sections[scope].push_back(&record->second);
                    break;
                }
            };
            if (ownerKind == "class" || ownerKind == "struct" || ownerKind == "namespace")
                add(compound);
            for (const auto section : compound.children("sectiondef"))
                for (const auto member : section.children("memberdef"))
                    add(member);
        }
    }
    const auto sourceRoot = project.Resolve("Source");
    std::map<fs::path, std::set<fs::path>> children;
    std::map<fs::path, fs::path> routes;
    for (auto& [file, page] : pages)
    {
        if (publicView && (markedPublic || !explicitPublicScope) && !Published(page.Overview))
            page.Overview = {};
        if (page.Sections.empty() && !page.Overview.child("briefdescription").first_child() &&
            !page.Overview.child("detaileddescription").first_child())
            continue;
        fs::path parent;
        for (const auto& part : file.lexically_relative(sourceRoot))
        {
            children[parent].insert(part);
            parent /= part;
        }
        routes.emplace(file, fs::path{});
    }
    std::map<fs::path, std::size_t, decltype(&FileNameLess)> stems(&FileNameLess), names(&FileNameLess);
    ++stems["index"];
    for (const auto& group : website.Groups)
        if (!group.Id.empty())
            ++stems[group.Id];
    for (auto& [file, route] : routes)
    {
        const auto relative = file.lexically_relative(sourceRoot);
        fs::path parent;
        for (const auto& directory : relative.parent_path())
        {
            parent /= directory;
            if (children.at(parent).size() > 1)
                route /= directory;
        }
        route /= relative.filename();
        ++stems[fs::path(route).replace_extension()];
        ++names[route];
    }
    for (auto& [file, route] : routes)
    {
        const auto stem = fs::path(route).replace_extension();
        if (stems.at(stem) == 1)
            route = stem;
        else if (names.at(route) > 1)
            route = file.lexically_relative(sourceRoot);
        auto& page = pages.at(file);
        page.Path = route.generic_u8string() + ".html";
        if (!page.DoxygenId.empty())
            website.FilePages.emplace(page.DoxygenId, page.Path);
    }
    for (auto& entry : pages)
    {
        auto& page = entry.second;
        if (page.Path.empty())
            continue;
        std::set<std::string> anchors{"overview", "main-content", "project-navigation", "search", "search-index", "search-results"};
        for (const auto& section : page.Sections)
            anchors.insert(SectionAnchor(section.first));
        for (auto& [scope, records] : page.Sections)
        {
            std::sort(records.begin(), records.end(), [](const auto* left, const auto* right) {
                return std::tie(left->Name, left->Signature) < std::tie(right->Name, right->Signature);
            });
            for (auto* record : records)
            {
                record->Page = page.Path;
                if (record->Name == scope)
                {
                    record->Anchor = SectionAnchor(scope);
                    continue;
                }
                const auto name = AnchorName(record->ToolName.empty() ? record->Leaf : record->ToolName);
                record->Anchor = name;
                for (std::size_t number = 2; !anchors.insert(record->Anchor).second; ++number)
                    record->Anchor = name + '-' + std::to_string(number);
            }
        }
        website.Pages.push_back(std::move(page));
    }
    std::sort(website.Pages.begin(), website.Pages.end(), [](const auto& a, const auto& b) {
        return std::tie(a.Title, a.File) < std::tie(b.Title, b.File);
    });
    if (!website.Pages.empty())
    {
        const auto root = std::find_if(website.Groups.begin(), website.Groups.end(), [&](const auto& group) {
            return std::all_of(website.Pages.begin(), website.Pages.end(), [&](const auto& page) {
                return group.Files.count(page.File) != 0;
            });
        });
        if (root != website.Groups.end())
            root->Id.clear();
    }
    return website;
}

std::string FunctionKey(const Record& entry)
{
    const auto separator = entry.Name.rfind("::");
    if (separator == std::string::npos)
        return entry.Name;
    auto scope = entry.Name.substr(0, separator);
    if (scope.size() > 1 && std::string_view("UAFI").find(scope[0]) != std::string_view::npos &&
        std::isupper(static_cast<unsigned char>(scope[1])))
        scope.erase(0, 1);
    return scope + '.' + entry.Leaf;
}

std::string Title(const Record& entry, const Language& language, const std::string& audience)
{
    if (!entry.ToolName.empty())
        return entry.ToolName;
    return language.LocalName("functions", FunctionKey(entry), language.Translate(entry.Id + ":title/" + audience, entry.Leaf));
}

std::string Brief(const Record& entry, const Language& language)
{
    auto brief = Normalize(Text(entry.Node.child("briefdescription")));
    if (!entry.ToolName.empty())
        brief.erase(0, entry.ToolName.size() + 1);
    return language.Translate(entry.Id + ":brief", brief);
}

constexpr std::string_view McpInputPrefix = "MCP input ";

bool IsMcpToolName(const std::string& name)
{
    static const std::regex pattern("[a-z][a-z0-9]*(?:_[a-z0-9]+)+");
    return std::regex_match(name, pattern);
}

std::string DoxygenBody(const Record& entry, const Website& website, const Language& language, const json& config,
                        const NativeProject& project, const fs::path& output, const std::string& audience, bool hasParameters)
{
    const std::string refid = entry.Node.attribute("id").value();
    const auto split = std::string_view(entry.Node.name()) == "memberdef" ? refid.rfind("_1") : std::string::npos;
    const auto page = refid.substr(0, split);
    const auto document = website.HtmlDocuments.find(page);
    if (document == website.HtmlDocuments.end())
        return {};
    const auto kind = std::string_view(entry.Node.attribute("kind").value());
    const auto query = split != std::string::npos ?
        "//a[@id='" + refid.substr(split + 2) + "']/following-sibling::div[@class='memitem'][1]/div[@class='memdoc']" :
        kind == "page" ? "//div[@class='contents']/div[@class='textblock']" :
        "//a[@id='details']/following-sibling::div[@class='textblock'][1]";
    const auto native = document->second->select_node(query.c_str()).node();
    if (!native)
        return {};

    pugi::xml_document fragment;
    auto body = fragment.append_copy(native);
    const auto root = SiteRoot(entry.Page);
    for (const auto match : body.select_nodes(".//*[@href or @src or @data]"))
    {
        auto element = match.node();
        for (const auto* name : {"href", "src", "data"})
        {
            auto attribute = element.attribute(name);
            if (!attribute)
                continue;
            const std::string value = attribute.value();
            const auto fragmentAt = value.find('#');
            const auto file = value.substr(0, fragmentAt);
            const auto path = fs::u8path(file);
            if (!file.empty() && (path != path.filename() || file.find(':') != std::string::npos))
                continue;
            const bool link = std::string_view(name) == "href";
            if (link && (file.empty() || path.extension() == ".html"))
            {
                const auto target = file.empty() ? page : path.stem().u8string();
                const auto anchor = fragmentAt == std::string::npos ? std::string{} : value.substr(fragmentAt + 1);
                const auto reference = website.References.find(anchor.empty() ? target : target + "_1" + anchor);
                if (reference != website.References.end())
                {
                    attribute.set_value(RecordUrl(entry.Page, *reference->second).c_str());
                    element.append_attribute("data-api-reference") = "yes";
                }
                else if (const auto targetPage = website.FilePages.find(target); anchor.empty() && targetPage != website.FilePages.end())
                    attribute.set_value((root + Url(targetPage->second)).c_str());
                else if (!file.empty() && fs::is_regular_file(website.HtmlDirectory / path))
                    element.remove_attribute(attribute);
            }
            else if (!file.empty() && fs::is_regular_file(website.HtmlDirectory / path))
            {
                const auto relative = fs::path("assets") / audience / path;
                const auto saved = project.Resolve(output / relative);
                fs::create_directories(saved.parent_path());
                fs::copy_file(website.HtmlDirectory / path, saved, fs::copy_options::overwrite_existing);
                attribute.set_value((root + "../../" + Url(relative.generic_u8string()) + value.substr(file.size())).c_str());
            }
        }
    }
    for (const auto section : body.select_nodes(".//dl[@class='params' or @class='section pre' or @class='section post']"))
    {
        const auto node = section.node();
        const auto kind = std::string_view(node.attribute("class").value());
        if ((kind == "params" && hasParameters) ||
            (kind != "params" && node.select_node(".//*[@data-api-reference]")))
            node.parent().remove_child(node);
    }
    const auto sections = config.value("language_sections", json{{"zh-CN", "中文|Chinese|zh-CN"}});
    for (const auto section : body.select_nodes(".//dl[@class='section user']"))
    {
        auto node = section.node();
        auto title = node.child("dt");
        const auto text = Normalize(Text(title));
        if (std::string_view(entry.Node.attribute("kind").value()) == "page" && IsMcpToolName(text))
            node.append_attribute("id") = text.c_str();
        if (!entry.ToolName.empty() && text.rfind(McpInputPrefix, 0) == 0)
        {
            node.parent().remove_child(node);
            continue;
        }
        bool localized = false;
        for (const auto& [locale, pattern] : sections.items())
            if (std::regex_match(text, std::regex(pattern.get<std::string>())))
            {
                if (locale == language.Code)
                    node.remove_child(title);
                else
                    node.parent().remove_child(node);
                localized = true;
                break;
            }
        if (!localized)
            for (const auto child : node.children())
                if (child.first_child().type() == pugi::node_pcdata && !child.first_child().next_sibling())
                    child.text().set(language.Translate({}, child.child_value()).c_str());
    }
    unsigned paragraph = 0;
    for (const auto child : body.children("p"))
    {
        const auto id = entry.Id + ":details/" + std::to_string(paragraph++);
        if (!child.attribute("class") && child.first_child().type() == pugi::node_pcdata && !child.first_child().next_sibling() &&
            std::string_view(child.child_value()).find("\\(") == std::string_view::npos)
            child.text().set(language.Translate(id, child.child_value()).c_str());
    }
    return Html(body);
}

struct Parameter
{
    std::string Name, Label, Type, Default, Description;
};


std::vector<Parameter> Parameters(const Record& entry, const Language& language, const json& config, bool publicView)
{
    std::map<std::string, std::string> descriptions;
    for (const auto match : entry.Node.select_nodes("detaileddescription//parameterlist[@kind='param']/parameteritem"))
    {
        const auto item = match.node();
        const auto description = Text(item.child("parameterdescription"));
        for (const auto name : item.child("parameternamelist").children("parametername"))
            descriptions.emplace(name.child_value(), description);
    }
    const auto hidden = config.value("hidden_parameters", std::vector<std::string>{});
    std::vector<Parameter> result;
    for (const auto parameter : entry.Node.children("param"))
    {
        const std::string name = parameter.child("declname").text().as_string(parameter.child_value("defname"));
        if (name.empty() || (publicView && std::find(hidden.begin(), hidden.end(), name) != hidden.end()))
            continue;
        if (!entry.ToolName.empty())
        {
            static const std::regex argument(R"(MCP ([a-z][a-z0-9_]*)[.] (.+))");
            const auto description = Normalize(descriptions[name]);
            std::smatch match;
            if (std::regex_match(description, match, argument))
            {
                const auto alias = match[1].str();
                result.push_back({alias, alias, {}, {}, language.Translate(entry.Id + ":param/" + name, match[2].str())});
                continue;
            }
        }
        result.push_back({name, language.LocalName("parameters", FunctionKey(entry) + '.' + name,
            language.Translate(entry.Id + ":term/" + name, name)), Text(parameter.child("type")),
            Text(parameter.child("defval")), language.Translate(entry.Id + ":param/" + name, descriptions[name])});
    }
    if (!entry.ToolName.empty())
        for (const auto match : entry.Node.select_nodes("detaileddescription//simplesect[@kind='par']"))
        {
            const auto section = match.node();
            const auto title = Normalize(Text(section.child("title")));
            if (title.rfind(McpInputPrefix, 0) != 0)
                continue;
            const auto alias = title.substr(McpInputPrefix.size());
            result.push_back({alias, alias, {}, {}, language.Translate(entry.Id + ":param/" + alias, Text(section.child("para")))});
        }
    return result;
}

std::string FunctionSignature(const std::string& title, const std::vector<Parameter>& parameters)
{
    std::string text = title + '(';
    for (const auto& parameter : parameters)
    {
        if (text.back() != '(')
            text += ", ";
        text += parameter.Label;
    }
    return text + ')';
}

std::string Article(const Record& entry, const Website& website, const Language& language,
                    const json& config, const NativeProject& project, const fs::path& output, const std::string& audience)
{
    const bool publicView = audience == "user";
    const bool chinese = language.Code == "zh-CN";
    const auto& words = language.Words();
    const std::string_view kind = entry.Node.attribute("kind").value();
    const bool type = kind == "class" || kind == "struct" || kind == "file" || kind == "page";
    const bool tool = !entry.ToolName.empty();
    const auto params = Parameters(entry, language, config, publicView);
    std::string article = "<article class=\"api-card" + std::string(type ? " type-summary" : "") + '"';
    if (!entry.Anchor.empty())
        article += " id=\"" + Escape(entry.Anchor) + '"';
    article += '>';
    if (!type)
    {
        const auto title = Title(entry, language, audience);
        const auto heading = entry.Scope.empty() ? "h2" : "h3";
        article += "<div class=\"api-heading\">";
        if (kind == "function")
            article += "<span class=\"entity-label\">" + std::string(words.Function) + "</span><" + heading +
                "><code class=\"function-signature\">" + Escape(FunctionSignature(title, params)) + "</code></" + heading + '>';
        else
            article += '<' + std::string(heading) + '>' + Escape(title) + "</" + heading + '>';
        article += "</div>";
        if (!tool)
            article += "<code class=\"api-name\">" + Escape(entry.Name) + "</code>";
    }
    if (const auto brief = Brief(entry, language); !brief.empty())
        article += "<p class=\"brief\">" + Escape(brief) + "</p>";
    if (!publicView && kind == "function")
        article += "<pre><code>" + Escape(entry.Signature) + "</code></pre>";

    const auto detail = entry.Node.child("detaileddescription");
    const auto details = DoxygenBody(entry, website, language, config, project, output, audience, !params.empty());

    std::string before, after;
    for (const auto match : detail.select_nodes(".//simplesect[@kind='pre' or @kind='post']"))
    {
        const auto section = match.node();
        const auto reference = section.select_node(".//ref");
        const auto target = website.References.find(reference.node().attribute("refid").value());
        if (target == website.References.end())
            continue;
        const auto& other = *target->second;
        const auto text = Normalize(Text(section));
        std::string mode = text;
        if (text.find("自动") != std::string::npos || text.find("automatic") != std::string::npos)
            mode = chinese ? "自动完成" : "Automatic";
        else if (text.find("可选") != std::string::npos || text.find("optional") != std::string::npos)
            mode = chinese ? "可选调用" : "Optional";
        else if (text.find("必须") != std::string::npos || text.find("required") != std::string::npos)
            mode = chinese ? "必须调用" : "Required";
        auto& rows = std::string_view(section.attribute("kind").value()) == "pre" ? before : after;
        rows += "<tr><th scope=\"row\"><a href=\"" + RecordLink(entry.Page, other) + "\"><code class=\"function-signature\">" +
            Escape(FunctionSignature(Title(other, language, audience), Parameters(other, language, config, publicView))) +
            "</code></a></th><td>" + Escape(Brief(other, language)) + "</td><td class=\"call-execution\">" + Escape(mode) + "</td></tr>";
    }
    if (!details.empty())
        article += "<section class=\"api-details\">" + (type ? "" : "<h3>" + std::string(words.Description) + "</h3>") + details + "</section>";
    if (!before.empty() || !after.empty())
        article += "<table class=\"call-table\"><thead><tr><th scope=\"col\">" + std::string(words.Function) +
            "</th><th scope=\"col\">" + words.Description + "</th><th scope=\"col\">" + words.Calling +
            "</th></tr></thead><tbody>" + before + "<tr class=\"call-current\"><th scope=\"row\"><code class=\"function-signature\">" +
            Escape(FunctionSignature(Title(entry, language, audience), params)) + "</code></th><td>" + Escape(Brief(entry, language)) +
            "</td><td class=\"call-execution\">" + words.Current + "</td></tr>" + after + "</tbody></table>";

    if (!params.empty())
    {
        article += "<h3>" + std::string(words.Inputs) + "</h3><table class=\"parameters\"><thead><tr><th scope=\"col\">" +
            words.Name + "</th>";
        if (!tool)
            article += "<th scope=\"col\">" + std::string(words.Type) + "</th>";
        article += "<th scope=\"col\">" + std::string(words.Description) + "</th></tr></thead><tbody>";
        for (const auto& parameter : params)
        {
            article += "<tr><th scope=\"row\"><code class=\"parameter-name\">" + Escape(parameter.Label) + "</code>";
            if (parameter.Label != parameter.Name)
                article += "<code class=\"parameter-native\">" + Escape(parameter.Name) + "</code>";
            article += "</th>";
            if (!tool)
            {
                article += "<td><code class=\"type\">" + Escape(parameter.Type) + "</code>";
                if (!parameter.Default.empty())
                    article += "<code class=\"default\">= " + Escape(parameter.Default) + "</code>";
                article += "</td>";
            }
            article += "<td>" + Escape(parameter.Description) + "</td></tr>";
        }
        article += "</tbody></table>";
    }
    return article + "</article>";
}

std::string FileLinks(const Website& website, const Group& group, const std::string& current, const Labels& words)
{
    const auto root = SiteRoot(current);
    struct Folder
    {
        std::map<std::string, Folder> Subfolders;
        std::vector<const Page*> Files;
    };
    Folder tree;
    for (const auto& page : website.Pages)
    {
        if (!group.Files.count(page.File))
            continue;
        auto* folder = &tree;
        const auto directory = fs::u8path(page.Path).parent_path();
        for (const auto& component : directory)
            if (component != ".")
                folder = &folder->Subfolders[component.u8string()];
        folder->Files.push_back(&page);
    }
    const auto render = [&](const auto& render, const Folder& folder) -> std::string {
        if (folder.Subfolders.empty() && folder.Files.empty())
            return {};
        std::string links = "<ul class=\"document-items\">";
        for (const auto& [name, child] : folder.Subfolders)
            links += "<li><span>" + Escape(name) + "</span>" + render(render, child) + "</li>";
        for (const auto* page : folder.Files)
        {
            links += "<li><a href=\"" + Escape(root + Url(page->Path)) + '"' + (page->Path == current ? " aria-current=\"page\"" : "") +
                '>' + Escape(page->Title);
            if (std::count_if(folder.Files.begin(), folder.Files.end(), [&](const auto* other) { return other->Title == page->Title; }) > 1)
                links += " <small>" + std::string(Header(page->File) ? words.Header : words.Implementation) + "</small>";
            links += "</a></li>";
        }
        return links + "</ul>";
    };
    return render(render, tree);
}

std::string PageHtml(const Website& website, const Language& language, const std::vector<Language>& languages,
                     const std::string& title, const std::string& version, const std::string& current,
                     const std::string& pageTitle, const Group* group,
                     const std::string& content, const std::string& toc, const std::string& search,
                     const std::string& styleVersion)
{
    const auto& words = language.Words();
    const auto root = SiteRoot(current);
    const auto home = root + "index.html";
    std::string navigation;
    for (const auto& item : website.Groups)
    {
        if (item.Id.empty())
        {
            navigation += FileLinks(website, item, current, words);
            continue;
        }
        const bool selected = &item == group;
        const auto link = "<a class=\"nav-item" + std::string(selected ? " active" : "") + "\" href=\"" + root + item.Id +
            ".html\"><span>" + Escape(GroupTitle(item, language)) + "</span></a>";
        const auto children = selected && std::count_if(website.Pages.begin(), website.Pages.end(), [&](const auto& file) {
            return item.Files.count(file.File) != 0;
        }) > 1 ? FileLinks(website, item, current, words) : "";
        navigation += children.empty() ? link : "<details class=\"nav-group\" open><summary>" + link +
            "</summary>" + children + "</details>";
    }
    std::string locales;
    for (const auto& locale : languages)
        locales += "<a" + std::string(locale.Code == language.Code ? " aria-current=\"page\"" : "") + " href=\"" + root + "../" +
            locale.Code + '/' + Escape(Url(current)) + "\">" + Escape(locale.Code == "en" ? "English" :
            locale.Code == "zh-CN" ? "简体中文" : locale.Code) + "</a>";
    std::string breadcrumbs = "<a href=\"" + home + "\">" + Escape(title) + "</a>";
    breadcrumbs += "<span>/</span><span>" + Escape(pageTitle) + "</span>";
    std::string renderers;
    if (content.find("class=\"mermaidgraph\"") != std::string::npos)
        renderers += website.MermaidScript;
    if (content.find("class=\"formulaDsp\"") != std::string::npos || content.find("\\(") != std::string::npos)
        renderers += website.MathScripts;

    return "<!doctype html><html lang=\"" + language.Code + "\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" "
        "content=\"width=device-width,initial-scale=1\"><title>" + Escape(title + " · " + pageTitle) +
        "</title><link rel=\"stylesheet\" href=\"" + root + "../../assets/site.css?v=" + styleVersion +
        "\"><script defer src=\"" + root + "../../assets/site.js?v=" + styleVersion + "\"></script>" + renderers + "</head><body>\n"
        "<a class=\"skip-link\" href=\"#main-content\">" + words.Skip +
        "</a>\n<header><button class=\"menu-toggle\" aria-controls=\"project-navigation\" aria-expanded=\"false\">☰ " +
        words.Start + "</button><a class=\"brand\" href=\"" + home + "\">" + Escape(title) +
        "</a><div class=\"header-search\"><label class=\"search\"><span aria-hidden=\"true\">⌕</span><input id=\"search\" "
        "type=\"search\" placeholder=\"" + words.Search + "\" aria-label=\"" + words.Search +
        "\"></label><div id=\"search-results\" hidden></div></div><nav class=\"languages\">" + locales + "</nav></header>\n"
        "<aside class=\"sidebar\" id=\"project-navigation\"><div class=\"sidebar-title\">" + Escape(title) +
        "</div><div class=\"version\"><span>" + words.Version + "</span><strong>" + Escape(version) +
        "</strong></div><nav aria-labelledby=\"document-directory\"><h2 class=\"nav-caption\" id=\"document-directory\">" +
        words.Start + "</h2>" + navigation + "</nav></aside>\n"
        "<main id=\"main-content\" tabindex=\"-1\"><nav class=\"breadcrumbs\" aria-label=\"" +
        (language.Code == "zh-CN" ? "项目文档" : "Project documentation") + "\">" + breadcrumbs + "</nav>" + content +
        "</main>\n<aside class=\"page-toc\"><nav aria-label=\"" + words.Contents + "\"><h2>" + words.Contents +
        "</h2><a href=\"#overview\">" + words.Overview + "</a>" + toc +
        "</nav></aside><script type=\"application/json\" id=\"search-index\" data-root=\"" + root + "\">" +
        search + "</script></body></html>";
}

std::string ToolUsage(pugi::xml_node detail, const std::string& heading)
{
    for (const auto match : detail.select_nodes(".//simplesect[@kind='par']"))
        if (Normalize(Text(match.node().child("title"))) == heading)
            return Text(match.node().child("para"));
    return {};
}

std::string ToolIndex(const Website& website, const Language& language, bool overviewVisible, std::string& toc)
{
    struct Tool
    {
        std::string Link, Motivation, Usage;
    };
    struct Owner
    {
        std::string Title, Purpose, Boundary;
        std::map<std::string, Tool> Tools;
    };
    std::map<std::string, Owner> owners;
    for (const auto& [id, record] : website.Records)
    {
        if (record.ToolName.empty())
            continue;
        const auto detail = record.Node.child("detaileddescription");
        const auto& scope = record.Scope.empty() ? record.GroupId : record.Scope;
        auto& owner = owners[scope];
        owner.Title = scope;
        if (const auto type = website.Classes.find(scope); type != website.Classes.end())
            owner.Purpose = Text(type->second.child("briefdescription"));
        owner.Tools.emplace(record.ToolName, Tool{RecordLink("index.html", record), Text(detail.child("para")),
            ToolUsage(detail, "Usage / 用法")});
    }

    const auto addPage = [&](pugi::xml_node page, const std::string& key, const std::string& title, bool link) {
        const auto detail = page.child("detaileddescription");
        for (const auto match : detail.select_nodes(".//simplesect[@kind='par']"))
        {
            const auto section = match.node();
            const auto name = Normalize(Text(section.child("title")));
            if (!IsMcpToolName(name))
                continue;
            const auto usage = ToolUsage(detail, name + " usage / " + name + " 用法");
            if (usage.empty())
                continue;
            auto& owner = owners[key];
            owner.Title = title;
            if (page != website.Overview)
            {
                owner.Purpose = Text(page.child("briefdescription"));
                owner.Boundary = Text(detail.child("para"));
            }
            owner.Tools.emplace(name, Tool{link ? "#" + name : "", Text(section.child("para")), usage});
        }
    };
    addPage(website.Overview, "MassBattleEditorMCP", "MassBattleEditorMCP · Server workflows / MassBattleEditorMCP · 连接与批处理",
        overviewVisible);
    for (const auto page : website.AnnotatedPages)
        addPage(page, page.attribute("id").value(), Text(page.child("title")), false);
    if (owners.empty())
        return {};

    const bool chinese = language.Code == "zh-CN";
    const auto heading = chinese ? "MCP 工具清单" : "MCP tools";
    std::string catalogue = "<section id=\"tools\"><h2 class=\"section-heading\">" + std::string(heading) + "</h2>";
    std::string links = "<a href=\"#tools\">" + std::string(heading) + "</a>";
    for (const auto& [key, owner] : owners)
    {
        const auto id = Escape("tools-" + key);
        const auto title = Escape(language.Translate(key + ":title", owner.Title));
        catalogue += "<section id=\"" + id + "\"><h3>" + title + "</h3>";
        links += "<a class=\"toc-member\" href=\"#" + id + "\">" + title + "</a>";
        for (const auto* text : {&owner.Purpose, &owner.Boundary})
            if (!text->empty())
                catalogue += "<p>" + Escape(language.Translate({}, *text)) + "</p>";
        catalogue += "<table class=\"member-index tool-index\"><thead><tr><th scope=\"col\">" +
            std::string(chinese ? "工具" : "Tool") + "</th><th scope=\"col\">" +
            (chinese ? "设计动机" : "Design rationale") + "</th><th scope=\"col\">" +
            (chinese ? "用法" : "Usage") + "</th></tr></thead><tbody>";
        for (const auto& [name, tool] : owner.Tools)
        {
            auto label = "<code>" + Escape(name) + "</code>";
            if (!tool.Link.empty())
                label = "<a href=\"" + tool.Link + "\">" + label + "</a>";
            catalogue += "<tr><th scope=\"row\" id=\"tool-" + Escape(name) + "\">" + label +
                "</th><td>" + Escape(language.Translate(name + ":motivation", tool.Motivation)) +
                "</td><td>" + Escape(language.Translate(name + ":usage", tool.Usage)) + "</td></tr>";
        }
        catalogue += "</tbody></table></section>";
    }
    toc = links + toc;
    return catalogue + "</section>";
}

void Render(const NativeProject& project, const Website& website, const json& config, const fs::path& output,
            const std::vector<Language>& languages, const std::string& title, const std::string& version,
            const std::string& audience, const std::string& styleVersion)
{
    for (const auto& language : languages)
    {
        const auto& words = language.Words();
        const auto directory = project.Resolve(output / audience / language.Code);
        auto searchIndex = json::array();
        std::map<std::string, std::string> articles;
        for (const auto& [id, record] : website.Records)
        {
            const auto& name = record.ToolName.empty() ? record.Name : record.ToolName;
            searchIndex.push_back({{"id", Url(record.Anchor)}, {"title", Title(record, language, audience)}, {"name", name},
                                   {"group", record.GroupId}, {"brief", Brief(record, language)}, {"page", Url(record.Page)}});
            articles.emplace(id, Article(record, website, language, config, project, output, audience));
        }
        std::string search;
        for (const auto character : searchIndex.dump())
        {
            if (character == '<') search += "\\u003c";
            else if (character == '>') search += "\\u003e";
            else if (character == '&') search += "\\u0026";
            else search += character;
        }

        const bool namedGroups = std::any_of(website.Groups.begin(), website.Groups.end(), [](const auto& group) { return !group.Id.empty(); });
        std::string listings;
        std::string homeToc;
        if (namedGroups)
        {
            listings = "<h2 class=\"section-heading\" id=\"folders\">" + std::string(words.Start) + "</h2><div class=\"family-grid\">";
            for (const auto& group : website.Groups)
                if (!group.Id.empty())
                    listings += "<a class=\"family-card\" href=\"" + group.Id + ".html\"><h2>" + Escape(GroupTitle(group, language)) +
                        "</h2><span class=\"card-link\">" + words.Open + " →</span></a>";
            listings += "</div>";
            homeToc = "<a href=\"#folders\">" + std::string(words.Start) + "</a>";
        }
        for (const auto& group : website.Groups)
            if (group.Id.empty())
                listings += FileLinks(website, group, "index.html", words);
        std::string overview;
        for (const auto node : website.AnnotatedPages)
        {
            const auto path = fs::u8path(node.child("location").attribute("file").value());
            if (path.extension() != ".dox")
                continue;
            const Record record{node.attribute("id").value(), title, title, "", "", "index.html", "", "", node, {}};
            overview += Article(record, website, language, config, project, output, audience);
        }
        const bool showPluginOverview = overview.empty() && website.Overview;
        if (showPluginOverview)
        {
            const Record record{"overview", title, title, "", "", "index.html", "", "", website.Overview, {}};
            overview = Article(record, website, language, config, project, output, audience);
        }
        listings = ToolIndex(website, language, showPluginOverview, homeToc) + listings;
        Write(project.Resolve(directory / "index.html"), PageHtml(website, language, languages, title, version, "index.html",
            namedGroups ? words.Start : words.Overview, nullptr, "<section class=\"hero\" id=\"overview\"><h1>" + Escape(title) +
            "</h1>" + overview + "</section>" + listings, homeToc, search, styleVersion));

        std::set<fs::path> expected{directory / "index.html"};
        for (const auto& group : website.Groups)
        {
            if (!group.Id.empty())
            {
                const auto label = GroupTitle(group, language);
                const auto heading = "<section class=\"page-heading\" id=\"overview\"><h1>" + Escape(label) + "</h1></section>";
                const auto route = group.Id + ".html";
                const auto links = FileLinks(website, group, route, words);
                const auto groupFile = directory / route;
                Write(project.Resolve(groupFile), PageHtml(website, language, languages, title, version, route, label, &group,
                    heading + (links.empty() ? "<p>" + std::string(words.Empty) + "</p>" : links), "", search, styleVersion));
                expected.insert(groupFile);
            }
            for (const auto& page : website.Pages)
            {
                if (!group.Files.count(page.File))
                    continue;
                const auto item = directory / fs::u8path(page.Path);
                if (!expected.insert(item).second)
                    continue;
                const auto summary = [&](pugi::xml_node node, const std::string& name) {
                    const Record record{SourceHash(name + '\n' + name).substr(0, 24), name, name, "", name,
                                        page.Path, group.Id, {}, node};
                    return Article(record, website, language, config, project, output, audience);
                };
                const auto fileName = page.File.filename().u8string();
                std::string content = "<section class=\"file-overview\" id=\"overview\"><div class=\"page-heading\">"
                    "<span class=\"entity-label\">" + std::string(words.File) + "</span><h1>" + Escape(fileName) + "</h1></div>";
                if (page.Overview.child("briefdescription").first_child() || page.Overview.child("detaileddescription").first_child())
                    content += summary(page.Overview, fileName);
                content += "</section>";
                std::string toc;
                for (const auto& [scope, records] : page.Sections)
                {
                    const auto id = SectionAnchor(scope);
                    const auto label = scope.empty() ? words.Members : scope;
                    const auto type = website.Classes.find(scope);
                    const auto kind = type == website.Classes.end() ? "members" : type->second.attribute("kind").value();
                    content += "<section class=\"class-section\" data-kind=\"" + std::string(kind) + "\" id=\"" + Escape(id) +
                        "\"><div class=\"class-heading\">";
                    if (!scope.empty())
                        content += "<span class=\"entity-label\">" + std::string(words.Class) + "</span>";
                    content += "<h2>" + Escape(label) + "</h2></div><div class=\"class-members\">";
                    if (type != website.Classes.end())
                        content += summary(type->second, scope);
                    toc += "<a href=\"#" + Escape(Url(id)) + "\">" + Escape(label) + "</a>";
                    std::string rows, members;
                    for (const auto* entry : records)
                    {
                        if (entry->Name == scope)
                            continue;
                        const auto name = Title(*entry, language, audience);
                        const auto link = RecordLink(page.Path, *entry);
                        rows += "<tr><td><a href=\"" + link + "\">";
                        if (std::string_view(entry->Node.attribute("kind").value()) == "function")
                            rows += "<span class=\"entity-label\">" + std::string(words.Function) +
                                "</span><code class=\"function-signature\">" +
                                Escape(FunctionSignature(name, Parameters(*entry, language, config, audience == "user"))) + "</code>";
                        else
                            rows += "<code>" + Escape(name) + "</code>";
                        rows += "</a></td><td>" + Escape(Brief(*entry, language)) + "</td></tr>";
                        toc += "<a class=\"toc-member\" href=\"" + link + "\">" + Escape(name) + "</a>";
                        members += articles.at(entry->Id);
                    }
                    if (!rows.empty())
                        content += "<table class=\"member-index\"><caption>" + std::string(words.Members) +
                            "</caption><thead><tr><th scope=\"col\">" + words.Name + "</th><th scope=\"col\">" +
                            words.Description + "</th></tr></thead><tbody>" + rows + "</tbody></table>" + members;
                    content += "</div></section>";
                }
                Write(project.Resolve(item), PageHtml(website, language, languages, title, version, page.Path, page.Title,
                    &group, content, toc, search, styleVersion));
            }
        }
        std::set<fs::path> staleParents;
        for (const auto& entry : fs::recursive_directory_iterator(directory))
        {
            if (entry.is_regular_file() && entry.path().extension() == ".html" && !expected.count(entry.path()))
            {
                fs::remove(entry.path());
                for (auto parent = entry.path().parent_path(); parent != directory; parent = parent.parent_path())
                    staleParents.insert(parent);
            }
        }
        for (auto parent = staleParents.rbegin(); parent != staleParents.rend(); ++parent)
            if (fs::is_empty(*parent))
                fs::remove(*parent);
    }
}
}

bool Published(pugi::xml_node node)
{
    const auto location = node.child("location");
    return DocumentationSource(fs::u8path(location.attribute("file").value())) &&
           node.attribute("prot").as_string() != std::string_view("private") &&
           (Text(node.child("briefdescription")) + Text(node.child("detaileddescription"))).find("@ProductDocument")
               != std::string::npos;
}

nlohmann::json GenerateWebsite(NativeProject& project, const nlohmann::json& profile, const std::string& audience)
{
    if (audience != "both" && audience != "user" && audience != "developer")
        throw std::runtime_error("Choose the user, developer, or both website audiences.");
    auto config = profile.value("documentation", json::object());
    if (!profile.contains("documentation"))
    {
        const auto settings = project.Resolve("Docs/McpDocumentation.json");
        if (fs::is_regular_file(settings))
            config = json::parse(ReadBytes(settings)).value("documentation", json::object());
    }
    const auto output = project.Resolve(fs::u8path(config.value("output", "Saved/Documentation/Website")));
    const auto title = config.value("title", project.Root.filename().u8string());
    auto version = config.value("version", "");
    if (config.contains("version_file"))
        version = json::parse(ReadBytes(project.Resolve(fs::u8path(config.at("version_file").get<std::string>())))).value("VersionName", version);
    const auto codes = config.value("languages", std::vector<std::string>{"en", "zh-CN"});
    if (codes.empty())
        throw std::runtime_error("Provide at least one website language.");
    static const std::regex locale("[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8})*");
    std::vector<Language> languages;
    for (const auto& code : codes)
    {
        if (!std::regex_match(code, locale))
            throw std::runtime_error("Invalid website language: " + code);
        languages.push_back(ReadLanguage(project, config, code));
    }

    Write(project.Resolve(output / "assets/site.css"), WebsiteStyle);
    Write(project.Resolve(output / "assets/site.js"), WebsiteScript);
    const auto styleVersion = Hash(std::string(WebsiteStyle) + WebsiteScript).substr(0, 12);
    const auto entry = output / "index.html";
    json result{{"status", "generated"}, {"audience", audience}, {"output", output.generic_u8string()},
                {"index", entry.generic_u8string()}, {"path", entry.generic_u8string()}, {"version", version},
                {"languages", codes}, {"source_only", true}, {"publication", "local"}};
    const auto audiences = audience == "both" ? std::vector<std::string>{"user", "developer"} :
        std::vector<std::string>{audience};
    for (const auto& view : audiences)
    {
        const bool publicView = view == "user";
        auto groups = Groups(project, config, publicView);
        std::set<fs::path> selected;
        for (const auto& group : groups)
            selected.insert(group.Files.begin(), group.Files.end());
        fs::path index;
        if (!selected.empty())
        {
            const auto directory = project.Scratch() / (view + "-website");
            fs::remove_all(directory);
            project.RunDoxygen(directory, true, publicView, {}, {selected.begin(), selected.end()},
                               config.value("defines", std::vector<std::string>{}));
            index = directory / "xml";
        }
        const auto website = ReadIndex(project, index, std::move(groups), publicView,
                                       config.contains("groups") || config.contains("user_inputs"));
        Render(project, website, config, output, languages, title, version, view, styleVersion);
        result[view + "_declarations"] = website.Records.size();
        auto files = json::array();
        for (const auto& file : selected)
            files.push_back(file.lexically_relative(project.Root).generic_u8string());
        result[view + "_files"] = std::move(files);
    }
    const auto target = audiences.front() + '/' + codes.front() + "/index.html";
    Write(project.Resolve(entry), "<!doctype html><html><head><meta charset=\"utf-8\"><meta http-equiv=\"refresh\" content=\"0;url=" +
        target + "\"><title>" + Escape(title) + "</title></head><body><a href=\"" + target +
        "\">Open documentation</a></body></html>");
    Write(project.Resolve(output / "manifest.json"), result.dump(2));
    for (const auto* view : {"user", "developer"})
    {
        const auto legacy = project.Resolve(output / (std::string(view) + "-source"));
        if (fs::is_regular_file(legacy / "xml/index.xml"))
        {
            fs::remove_all(project.Resolve(legacy / "xml"));
            if (fs::is_empty(legacy))
                fs::remove(legacy);
        }
    }
    return result;
}
}

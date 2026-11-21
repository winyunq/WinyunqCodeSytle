#include "Authorization/SourceWriteAuthorization.h"
#include "Configure/GenerateWebsite.h"
#include "Delete/DeleteCodeFragment.h"
#include "Delete/DeleteDocumentation.h"
#include "Delete/DeleteSymbols.h"
#include "Read/FindReferences.h"
#include "Read/ReadDefinition.h"
#include "Read/ReadDocumentation.h"
#include "Read/ReadTypeMembers.h"
#include "Write/EditDocumentation.h"
#include "Write/EditFunction.h"

#include <json.hpp>
#include <algorithm>
#include <iostream>
#include <map>
#include <optional>
#include <random>
#include <regex>
#include <stdexcept>

using nlohmann::json;
using namespace WinyunqCodeSytle;

namespace
{
json Tool(std::string name, std::string description, std::initializer_list<const char*> fields)
{
    json properties = json::object();
    for (const auto field : fields)
        properties[field] = {{"type", "string"}};
    if (name == "Write")
    {
        properties["fields"] = {{"type", "object"}, {"description", "Doxygen fields to add or update."}};
        properties["signature"] = {{"type", "object"}, {"description", "New name and/or parameter declarations."}};
    }
    if (name == "Delete")
    {
        properties["fields"] = {{"type", "object"}, {"description", "Parameter annotations to remove."}};
        properties["targets"] = {{"type", "array"}, {"items", {{"type", "object"},
            {"properties", {{"name", {{"type", "string"}}}, {"path", {{"type", "string"}}},
                            {"target", {{"type", "string"}}}}}, {"additionalProperties", false}}}};
    }
    return {{"name", std::move(name)}, {"description", std::move(description)},
            {"inputSchema", {{"type", "object"}, {"properties", properties}, {"additionalProperties", false}}}};
}

const json Tools = json::array({
    Tool("Read", "Read C++ symbols, declarations, definitions, documentation, members or references.",
         {"name", "query", "target", "path", "view"}),
    Tool("Write", "Preview or apply a documentation, function body, signature, member, or function rename edit.",
         {"action", "kind", "name", "target", "path", "body", "declaration", "new_name", "part", "plan"}),
    Tool("Delete", "Delete a C++ symbol or batch when no references to it will remain.",
         {"action", "kind", "name", "target", "path", "old_code", "reason", "plan"}),
    Tool("Configure", "View status, abort a plan, reindex C++, or generate the developer API website.",
         {"action", "audience"})
});

std::string Identifier()
{
    std::random_device random;
    return std::to_string(random()) + "-" + std::to_string(random()) + "-" + std::to_string(random());
}

bool MatchesPath(std::string pattern, const std::string& value)
{
    std::replace(pattern.begin(), pattern.end(), '\\', '/');
    std::string regex;
    for (const char character : pattern)
    {
        if (character == '*')
            regex += ".*";
        else if (character == '?')
            regex += '.';
        else
        {
            if (std::string_view(R"(.^$|()[]{}+\)").find(character) != std::string_view::npos)
                regex += '\\';
            regex += character;
        }
    }
#ifdef _WIN32
    return std::regex_match(value, std::regex(regex, std::regex::icase));
#else
    return std::regex_match(value, std::regex(regex));
#endif
}

struct PendingEdit
{
    std::string Id;
    bool Delete;
    bool Approval;
    std::vector<SourceEdit> Edits;
    json Review;
    std::vector<SourceEdit> Withdraw;
};

struct PendingDeletion
{
    std::string Id;
    std::vector<Symbol> Symbols;
    SymbolDeletion Deletion;
};

class WinyunqCodeSytleServer
{
public:
    WinyunqCodeSytleServer(fs::path root, fs::path doxygen, fs::path profile, fs::path approvals)
        : Project(std::move(root), std::move(doxygen)), ProfilePath(std::move(profile)),
          ProfileBytes(ProfilePath.empty() ? "{}" : ReadBytes(ProfilePath)), Profile(json::parse(ProfileBytes)),
          ApprovalDirectory(std::move(approvals))
    {
        if (!Profile.is_object())
            throw std::runtime_error("The maintenance profile must be an object.");
    }

    json Process(const json& request)
    {
        if (!request.is_object() || request.value("jsonrpc", "") != "2.0" ||
            !request.contains("method") || !request["method"].is_string())
            return Error(nullptr, -32600, "Invalid request.");
        if (!request.contains("id"))
            return nullptr;
        const auto id = request["id"];
        const auto method = request["method"].get<std::string>();
        const auto params = request.value("params", json::object());
        if (!params.is_object() || (!id.is_string() && !id.is_number_integer()))
            return Error(id, -32600, "Invalid request.");
        if (method == "initialize")
        {
            if (params.contains("clientInfo") && !params["clientInfo"].is_object())
                return Error(id, -32602, "clientInfo must be an object.");
            const auto requested = params.value("protocolVersion", "");
            Version = requested == "2024-11-05" || requested == "2025-03-26" || requested == "2025-06-18"
                ? requested : "2025-11-25";
            return Result(id, {{"protocolVersion", Version}, {"capabilities", {{"tools", {{"listChanged", false}}}}},
                               {"serverInfo", {{"name", "WinyunqCodeSytle"}, {"version", "0.1.0"}}}});
        }
        if (method == "ping")
            return Result(id, json::object());
        if (Version.empty())
            return Error(id, -32002, "Initialize first.");
        if (method == "tools/list")
            return Result(id, {{"tools", Tools}});
        if (method != "tools/call")
            return Error(id, -32601, "Unknown method.");
        const auto name = params.value("name", "");
        const auto tool = std::find_if(Tools.begin(), Tools.end(), [&](const json& item) { return item["name"] == name; });
        if (tool == Tools.end())
            return Error(id, -32602, "Unknown tool.");
        try
        {
            const auto arguments = params.value("arguments", json::object());
            if (!arguments.is_object())
                throw std::runtime_error("Expected an arguments object.");
            const auto& properties = (*tool)["inputSchema"]["properties"];
            for (const auto& field : arguments.items())
                if (!properties.contains(field.key()) ||
                    properties.at(field.key()).at("type") != field.value().type_name())
                    throw std::runtime_error("Unsupported argument: " + field.key());
            const auto result = Call(name, arguments);
            if (Version == "2024-11-05" || Version == "2025-03-26")
                return Result(id, {{"content", TextContent(result.dump())}});
            return Result(id, {{"content", json::array()}, {"structuredContent", result}});
        }
        catch (const std::exception& error)
        {
            return Result(id, {{"isError", true}, {"content", TextContent(error.what())}});
        }
    }

    static json Error(const json& id, int code, const std::string& message)
    {
        return {{"jsonrpc", "2.0"}, {"id", id}, {"error", {{"code", code}, {"message", message}}}};
    }

private:
    static json Result(const json& id, const json& result)
    {
        return {{"jsonrpc", "2.0"}, {"id", id}, {"result", result}};
    }

    static json TextContent(const std::string& text)
    {
        return json::array({{{"type", "text"}, {"text", text}}});
    }

    std::string RelativePath(const fs::path& path) const
    {
        return path.lexically_relative(Project.Root).generic_u8string();
    }

    void Authorize(const fs::path& path)
    {
        const auto relative = RelativePath(Project.Resolve(path));
        const auto extension = path.extension().string();
        if (relative.rfind("Source/", 0) != 0 ||
            std::string_view("|.cpp|.cc|.cxx|.h|.hh|.hpp|.hxx|.inl|").find("|" + extension + "|") == std::string_view::npos)
            throw std::runtime_error("The target must be C++ source under Source.");
        if (ProfilePath.empty())
        {
            SourceAuthorization.Require(Project.Root);
            return;
        }
        if (Profile.value("mode", "") != "maintain" || ReadBytes(ProfilePath) != ProfileBytes)
            throw std::runtime_error("A current maintain profile is required.");
        if (Profile.value("require_validation", false) ||
            (Profile.contains("validation") && !Profile["validation"].empty()) ||
            (Profile.contains("pinned_files") && !Profile["pinned_files"].empty()) ||
            (Profile.contains("forbid_added_tokens") && !Profile["forbid_added_tokens"].empty()))
            throw std::runtime_error("This profile requires checks unavailable in the native backend.");
        for (const auto& pattern : Profile.value("code_paths", std::vector<std::string>{}))
            if (MatchesPath(pattern, relative))
                return;
        throw std::runtime_error("The source path is outside the maintain profile.");
    }

    json Describe(const Symbol& symbol)
    {
        json result{{"id", symbol.Id}, {"name", symbol.Name}, {"kind", symbol.Kind}, {"signature", symbol.Signature}};
        if (symbol.Node.child("location").attribute("file"))
        {
            const auto location = DeclarationLocation(Project, symbol);
            result["path"] = RelativePath(location.Path);
            result["line"] = location.Line;
        }
        return result;
    }

    std::vector<Symbol> Matches(const json& args, const std::string& name)
    {
        auto matches = FindSymbols(Project.Index(), name);
        const auto path = args.value("path", "");
        if (!path.empty())
        {
            const auto requested = Project.Resolve(fs::u8path(path));
            matches.erase(std::remove_if(matches.begin(), matches.end(), [&](const auto& symbol) {
                return DeclarationLocation(Project, symbol).Path != requested;
            }), matches.end());
        }
        return matches;
    }

    json Candidates(const std::vector<Symbol>& matches)
    {
        auto candidates = json::array();
        for (const auto& symbol : matches)
            candidates.push_back(Describe(symbol));
        return candidates;
    }

    json Read(const json& args)
    {
        const auto name = args.value("target", args.value("name", args.value("query", "")));
        if (name.empty())
            throw std::runtime_error("Provide a C++ symbol name or index ID.");
        const auto view = args.value("view", args.contains("query") ? "brief" : "overview");
        const auto matches = Matches(args, name);
        if (view == "brief" || view == "symbols")
            return {{"symbols", Candidates(matches)}};
        if (matches.empty())
            throw std::runtime_error("C++ symbol not found: " + name);
        if (matches.size() > 1)
            return {{"status", "ambiguous"}, {"candidates", Candidates(matches)}};
        const auto& symbol = matches.front();
        auto result = Describe(symbol);
        if (view == "overview" || view == "declaration")
            result["declaration"] = ReadDeclaration(symbol);
        else if (view == "definition" || view == "code")
        {
            const auto definition = ReadDefinition(Project, symbol);
            result["path"] = RelativePath(definition.Location.Path);
            result["line"] = definition.Location.Line;
            result["end_line"] = definition.EndLine;
            result["code"] = definition.Code;
        }
        else if (view == "documentation")
            result["documentation"] = ReadDocumentation(symbol);
        else if (view == "members")
        {
            result["members"] = json::array();
            for (const auto& member : ReadTypeMembers(symbol))
                result["members"].push_back({{"name", member.Name}, {"kind", member.Kind}, {"access", member.Access}});
        }
        else if (view == "references" || view == "uses")
        {
            result["references"] = json::array();
            for (const auto& reference : FindReferences(symbol))
                result["references"].push_back({{"name", reference.Name}, {"direction", reference.Direction},
                                                {"compound", reference.File}, {"line", reference.Line}});
        }
        else
            throw std::runtime_error("Unsupported C++ read view.");
        return result;
    }

    json Edit(const json& args, bool deleting)
    {
        const auto action = args.value("action", "preview");
        if (action == "apply")
        {
            if (args.size() != 2 || !Pending || Pending->Id != args.value("plan", "") || Pending->Delete != deleting)
                throw std::runtime_error("Provide only the matching plan from this session.");
            if (Pending->Approval && (ApprovalDirectory.empty() ||
                !fs::is_regular_file(ApprovalDirectory / (Pending->Id + ".approved"))))
                throw std::runtime_error("Local approval is required for this deletion plan.");
            if (!Pending->Review.empty())
            {
                for (const auto& edit : Pending->Edits)
                {
                    Authorize(edit.Path);
                    if (ReadBytes(edit.Path) != edit.Before)
                        throw std::runtime_error("The source changed. Preview the signature again.");
                }
                if (!ConfirmSignatureChange(Project.Scratch(), Pending->Review.dump()))
                {
                    auto result = CommitEdits(Pending->Withdraw, Pending->Id);
                    Pending.reset();
                    result["status"] = "rejected";
                    return result;
                }
            }
            auto result = CommitEdits(Pending->Edits, Pending->Id);
            Pending.reset();
            return result;
        }
        if (action != "preview")
            throw std::runtime_error("Expected preview or apply.");
        Pending.reset();
        PendingSymbols.reset();
        const bool parameterComments = deleting && args.contains("fields");
        if (deleting && !parameterComments && args.value("reason", "").empty())
            throw std::runtime_error("Provide a reason for the deletion preview.");
        const auto kind = args.value("kind", parameterComments ? "comment" : "code");
        if (parameterComments && kind != "comment")
            throw std::runtime_error("Parameter annotations belong to the comment edit.");
        PendingEdit plan{Identifier(), deleting, deleting && !parameterComments, {}, {}, {}};
        if (deleting && kind == "code")
        {
            const auto path = Project.Resolve(fs::u8path(args.at("path").get<std::string>()));
            Authorize(path);
            plan.Edits.push_back(DeleteCodeFragment(Project, path, args.at("old_code").get<std::string>()));
        }
        else
        {
            const auto name = args.value("target", args.value("name", ""));
            if (name.empty())
                throw std::runtime_error("Provide a C++ symbol name or index ID.");
            const auto matches = Matches(args, name);
            if (matches.empty())
                throw std::runtime_error("C++ symbol not found: " + name);
            if (matches.size() > 1)
                return {{"status", "ambiguous"}, {"candidates", Candidates(matches)}};
            const auto& symbol = matches.front();
            if (!deleting)
            {
                const auto payload = kind == "comment" ? "fields" : kind == "signature" ? "signature" :
                    kind == "member" ? "declaration" : kind == "rename" ? "new_name" : "body";
                for (const std::string field : {"fields", "signature", "declaration", "body", "new_name"})
                    if (args.contains(field) != (field == payload))
                        throw std::runtime_error("Provide only the edit payload for this Write kind.");
            }
            if (kind == "comment")
            {
                const auto part = args.value("part", "declaration");
                if (part != "declaration" && part != "definition")
                    throw std::runtime_error("Expected declaration or definition for documentation placement.");
                const auto location = part == "definition" ? ReadDefinition(Project, symbol).Location
                                                           : DeclarationLocation(Project, symbol);
                Authorize(location.Path);
                if (parameterComments)
                {
                    const auto& fields = args.at("fields");
                    if (fields.size() != 1 || !fields.contains("params"))
                        throw std::runtime_error("Provide the parameter annotation names in fields.params.");
                    const auto parameters = fields.at("params").get<std::vector<std::string>>();
                    if (parameters.empty())
                        throw std::runtime_error("Provide at least one parameter annotation name.");
                    for (const auto& name : parameters)
                        for (const auto parameter : symbol.Node.children("param"))
                            if (name == parameter.child_value("declname") || name == parameter.child_value("defname"))
                                throw std::runtime_error("Remove the parameter from the signature first: " + name);
                    plan.Edits.push_back(RemoveParameterComments(location, symbol, parameters));
                }
                else
                    plan.Edits.push_back(deleting ? DeleteDocumentation(Project, symbol) :
                        EditDocumentation(location, symbol, args.at("fields")));
            }
            else if (!deleting && kind == "code")
                plan.Edits.push_back(EditFunctionBody(Project, symbol, args.at("body").get<std::string>()));
            else if (!deleting && kind == "member")
                plan.Edits.push_back(AddMember(Project, symbol, args.at("declaration").get<std::string>()));
            else if (!deleting && (kind == "signature" || kind == "rename"))
            {
                const auto change = kind == "rename" ? json{{"name", args.at("new_name")}} : args.at("signature");
                auto signature = EditFunctionSignature(Project, symbol, change);
                plan.Edits = std::move(signature.Edits);
                if (signature.AddsParameters && Published(symbol.Node))
                {
                    plan.Review = std::move(signature.Review);
                    if (!signature.WithdrawParameters.empty())
                    {
                        auto removal = RemoveParameterComments(DeclarationLocation(Project, symbol), symbol,
                                                               signature.WithdrawParameters);
                        Authorize(removal.Path);
                        plan.Withdraw.push_back(std::move(removal));
                    }
                }
            }
            else
                throw std::runtime_error("Expected comment, code, signature, member, or rename.");
        }
        auto changes = json::array();
        for (const auto& edit : plan.Edits)
        {
            Authorize(edit.Path);
            if (edit.Before == edit.After)
                continue;
            const auto begin = std::mismatch(edit.Before.begin(), edit.Before.end(), edit.After.begin(), edit.After.end()).first;
            const auto offset = static_cast<std::size_t>(begin - edit.Before.begin());
            std::size_t tail = 0;
            while (tail < std::min(edit.Before.size(), edit.After.size()) - offset &&
                   edit.Before[edit.Before.size() - tail - 1] == edit.After[edit.After.size() - tail - 1])
                ++tail;
            changes.push_back({{"path", RelativePath(edit.Path)}, {"offset", offset},
                {"before", edit.Before.substr(offset, edit.Before.size() - offset - tail)},
                {"after", edit.After.substr(offset, edit.After.size() - offset - tail)}});
        }
        if (changes.empty())
            return {{"status", "unchanged"}};
        auto result = changes.size() == 1 ? changes.front() : json{{"edits", changes}};
        result["status"] = "preview";
        result["plan"] = plan.Id;
        result["approval_required"] = plan.Approval || !plan.Review.empty();
        if (!plan.Review.empty())
            result["review"] = plan.Review;
        Pending = std::move(plan);
        return result;
    }

    json CommitEdits(const std::vector<SourceEdit>& edits, const std::string& plan)
    {
        auto files = json::array();
        for (const auto& edit : edits)
        {
            Authorize(edit.Path);
            if (ReadBytes(edit.Path) != edit.Before)
                throw std::runtime_error("The source changed. Preview the edit again.");
            files.push_back(RelativePath(edit.Path));
        }
        std::size_t applied = 0;
        try
        {
            for (const auto& edit : edits)
            {
                ApplySourceEdit(Project, edit, plan);
                ++applied;
            }
        }
        catch (...)
        {
            while (applied)
            {
                const auto& edit = edits[--applied];
                ApplySourceEdit(Project, {edit.Path, edit.After, edit.Before}, plan);
            }
            throw;
        }
        return {{"status", "applied"}, {"files", std::move(files)}};
    }

    json RemainingReferences(const SymbolDeletion& deletion)
    {
        auto references = json::array();
        for (const auto& reference : deletion.References)
            references.push_back({{"path", reference.File.generic_u8string()},
                                  {"line", reference.Line}, {"symbol", reference.Symbol}});
        return {{"status", "referenced"}, {"remaining_references", std::move(references)}};
    }

    json DeleteSymbols(const json& args)
    {
        const auto action = args.value("action", "");
        if (action == "apply")
        {
            if (!PendingSymbols || args.value("plan", "") != PendingSymbols->Id || args.size() != 2)
                throw std::runtime_error("Provide only the matching deletion plan from this session.");
            const auto index = Project.Index();
            std::vector<Symbol> current;
            for (const auto& previous : PendingSymbols->Symbols)
            {
                auto matches = FindSymbols(index, previous.Id);
                if (matches.size() != 1)
                    throw std::runtime_error("The indexed symbol changed. Preview the deletion again.");
                current.push_back(std::move(matches.front()));
            }
            const auto deletion = PreviewSymbolDeletion(Project, index, current);
            if (!deletion.References.empty())
                return RemainingReferences(deletion);
            auto result = CommitEdits(PendingSymbols->Deletion.Edits, PendingSymbols->Id);
            PendingSymbols.reset();
            return result;
        }
        if (action != "" && action != "preview")
            throw std::runtime_error("Expected preview or apply.");
        Pending.reset();
        PendingSymbols.reset();
        const auto targets = args.value("targets", json::array({args}));
        if (targets.empty() || !targets.is_array())
            throw std::runtime_error("Provide at least one symbol.");
        std::vector<Symbol> symbols;
        const auto index = Project.Index();
        for (const auto& target : targets)
        {
            const auto name = target.value("target", target.value("name", ""));
            if (name.empty())
                throw std::runtime_error("Provide the name or ID of each symbol to delete.");
            const auto path = target.value("path", "");
            auto matches = FindSymbols(index, name);
            if (!path.empty())
            {
                const auto requested = Project.Resolve(fs::u8path(path));
                matches.erase(std::remove_if(matches.begin(), matches.end(), [&](const auto& symbol) {
                    return DeclarationLocation(Project, symbol).Path != requested;
                }), matches.end());
            }
            if (matches.empty())
                throw std::runtime_error("C++ symbol not found: " + name);
            const auto sameDefinition = [](const Symbol& a, const Symbol& b) {
                const auto left = a.Node.child("location");
                const auto right = b.Node.child("location");
                const std::string_view file = left.attribute("bodyfile").value();
                const auto line = left.attribute("bodystart").as_uint();
                return a.Signature == b.Signature && !file.empty() && line &&
                    file == right.attribute("bodyfile").value() && line == right.attribute("bodystart").as_uint();
            };
            if (matches.size() > 1 && !std::all_of(matches.begin() + 1, matches.end(), [&](const auto& match) {
                    return sameDefinition(matches.front(), match);
                }))
                return {{"status", "ambiguous"}, {"candidates", Candidates(matches)}};
            auto related = FindSymbols(index, matches.front().Signature);
            for (auto& match : related)
                if ((match.Id == matches.front().Id || sameDefinition(match, matches.front())) &&
                    std::none_of(symbols.begin(), symbols.end(), [&](const auto& existing) { return existing.Id == match.Id; }))
                    symbols.push_back(std::move(match));
            if (std::none_of(symbols.begin(), symbols.end(), [&](const auto& existing) { return existing.Id == matches.front().Id; }))
                symbols.push_back(std::move(matches.front()));
        }
        auto deletion = PreviewSymbolDeletion(Project, index, symbols);
        if (!deletion.References.empty())
            return RemainingReferences(deletion);
        PendingDeletion plan{Identifier(), std::move(symbols), std::move(deletion)};
        if (action.empty())
            return CommitEdits(plan.Deletion.Edits, plan.Id);
        PendingSymbols = std::move(plan);
        return {{"status", "preview"}, {"plan", PendingSymbols->Id}, {"remaining_references", json::array()}};
    }

    json Call(const std::string& name, const json& args)
    {
        if (name == "Read")
            return Read(args);
        if (name == "Delete" && (args.contains("targets") || args.value("kind", "") == "symbol" ||
            (args.value("action", "") == "apply" && PendingSymbols) ||
            ((args.contains("name") || args.contains("target")) && !args.contains("old_code") && !args.contains("fields") &&
                args.value("kind", "code") == "code")))
            return DeleteSymbols(args);
        if (name == "Write" || name == "Delete")
            return Edit(args, name == "Delete");
        const auto action = args.value("action", "status");
        if (action == "status")
            return {{"mode", Profile.value("mode", "read_only")}, {"backend", "cpp"},
                    {"plan", Pending ? json(Pending->Id) : PendingSymbols ? json(PendingSymbols->Id) : json(nullptr)}};
        if (action == "abort")
        {
            Pending.reset();
            PendingSymbols.reset();
            return {{"status", "aborted"}};
        }
        if (action == "reindex")
        {
            Project.Index();
            return {{"status", "indexed"}};
        }
        if (action == "generate_website")
            return GenerateWebsite(Project, Profile, args.value("audience", "both"));
        throw std::runtime_error("Unsupported native Configure action or audience.");
    }

    NativeProject Project;
    SourceWriteAuthorization SourceAuthorization;
    fs::path ProfilePath;
    std::string ProfileBytes;
    json Profile;
    fs::path ApprovalDirectory;
    std::string Version;
    std::optional<PendingEdit> Pending;
    std::optional<PendingDeletion> PendingSymbols;
};
}

int main(int argc, char** argv)
{
    try
    {
        std::map<std::string, fs::path> options;
        for (int i = 1; i < argc; i += 2)
        {
            const std::string option = argv[i];
            if (i + 1 == argc || (option != "--project" && option != "--doxygen" &&
                                 option != "--profile" && option != "--approval-dir"))
                throw std::runtime_error("Usage: WinyunqCodeSytle --doxygen PATH [--project PATH] [--profile PATH] [--approval-dir PATH]");
            options[option] = fs::u8path(argv[i + 1]);
        }
        const auto project = options.count("--project") ? options.at("--project") : fs::current_path();
        WinyunqCodeSytleServer server(project, options.at("--doxygen"), options["--profile"], options["--approval-dir"]);
        std::string line;
        while (std::getline(std::cin, line))
        {
            json response;
            try
            {
                response = server.Process(json::parse(line));
            }
            catch (const json::parse_error&)
            {
                response = WinyunqCodeSytleServer::Error(nullptr, -32700, "Invalid JSON.");
            }
            catch (const json::exception&)
            {
                response = WinyunqCodeSytleServer::Error(nullptr, -32602, "Invalid params.");
            }
            if (!response.is_null())
                std::cout << response.dump(-1, ' ', false, json::error_handler_t::replace) << std::endl;
        }
    }
    catch (const std::exception& error)
    {
        std::cerr << error.what() << '\n';
        return 1;
    }
}

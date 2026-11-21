#include "NativeProject.h"

#include <fstream>
#include <cstdlib>
#include <json.hpp>
#include <random>
#include <regex>
#include <set>
#include <stdexcept>
#include <system_error>
#include <vector>

#ifdef _WIN32
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <shellapi.h>
#else
#include <cerrno>
#include <fcntl.h>
#include <sys/wait.h>
#include <unistd.h>
#include <wordexp.h>
#endif

namespace WinyunqCodeSytle
{
namespace
{
std::string QuotePath(const fs::path& path)
{
    const auto value = path.generic_u8string();
    if (value.find_first_of("\n\r\"") != std::string::npos)
        throw std::runtime_error("Unsupported character in Doxygen path.");
    return "\"" + value + "\"";
}

#ifdef _WIN32
std::wstring CommandArgument(const std::wstring& argument)
{
    std::wstring result = L"\"";
    std::size_t backslashes = 0;
    for (const auto character : argument)
    {
        if (character == L'\\')
        {
            ++backslashes;
            continue;
        }
        result.append(character == L'"' ? 2 * backslashes + 1 : backslashes, L'\\');
        result += character;
        backslashes = 0;
    }
    result.append(2 * backslashes, L'\\');
    return result + L'"';
}
#endif

int Launch(const fs::path& executable, const std::vector<std::string>& arguments, const fs::path& directory,
           const fs::path& output, const fs::path& diagnostics, const fs::path& input = {})
{
#ifdef _WIN32
    auto command = CommandArgument(executable.wstring());
    for (const auto& argument : arguments)
        command += L' ' + CommandArgument(fs::u8path(argument).wstring());
    SECURITY_ATTRIBUTES attributes{sizeof(attributes), nullptr, TRUE};
    const auto openLog = [&](const fs::path& path) {
        return CreateFileW(path.c_str(), GENERIC_WRITE, FILE_SHARE_READ, &attributes,
                           CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, nullptr);
    };
    HANDLE log = openLog(output);
    if (log == INVALID_HANDLE_VALUE)
        throw std::system_error(GetLastError(), std::system_category(), "Open tool output");
    HANDLE errors = output == diagnostics ? log : openLog(diagnostics);
    if (errors == INVALID_HANDLE_VALUE)
    {
        const auto error = GetLastError();
        CloseHandle(log);
        throw std::system_error(error, std::system_category(), "Open tool diagnostics");
    }
    STARTUPINFOW startup{};
    startup.cb = sizeof(startup);
    startup.dwFlags = STARTF_USESTDHANDLES;
    startup.hStdInput = input.empty() ? GetStdHandle(STD_INPUT_HANDLE) :
        CreateFileW(input.c_str(), GENERIC_READ, FILE_SHARE_READ, &attributes, OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, nullptr);
    if (!input.empty() && startup.hStdInput == INVALID_HANDLE_VALUE)
    {
        const auto error = GetLastError();
        CloseHandle(log);
        if (errors != log)
            CloseHandle(errors);
        throw std::system_error(error, std::system_category(), "Open tool input");
    }
    startup.hStdOutput = log;
    startup.hStdError = errors;
    PROCESS_INFORMATION process{};
    const auto started = CreateProcessW(executable.has_parent_path() ? executable.c_str() : nullptr,
                                        command.data(), nullptr, nullptr, TRUE, CREATE_NO_WINDOW, nullptr,
                                        directory.c_str(), &startup, &process);
    const auto error = GetLastError();
    CloseHandle(log);
    if (!input.empty())
        CloseHandle(startup.hStdInput);
    if (errors != log)
        CloseHandle(errors);
    if (!started)
        throw std::system_error(error, std::system_category(), "Launch " + executable.generic_u8string());
    CloseHandle(process.hThread);
    WaitForSingleObject(process.hProcess, INFINITE);
    DWORD status = 1;
    GetExitCodeProcess(process.hProcess, &status);
    CloseHandle(process.hProcess);
    return static_cast<int>(status);
#else
    auto program = executable.string();
    std::vector<char*> argv{program.data()};
    for (const auto& argument : arguments)
        argv.push_back(const_cast<char*>(argument.c_str()));
    argv.push_back(nullptr);
    const auto pid = fork();
    if (pid < 0)
        throw std::system_error(errno, std::generic_category(), "Launch " + program);
    if (pid == 0)
    {
        const auto log = open(output.c_str(), O_WRONLY | O_CREAT | O_TRUNC, 0600);
        const auto errors = output == diagnostics ? log : open(diagnostics.c_str(), O_WRONLY | O_CREAT | O_TRUNC, 0600);
        if (log < 0 || errors < 0 || chdir(directory.c_str()) != 0)
            _exit(126);
        if (!input.empty())
        {
            const auto descriptor = open(input.c_str(), O_RDONLY);
            if (descriptor < 0 || dup2(descriptor, STDIN_FILENO) < 0)
                _exit(126);
            close(descriptor);
        }
        dup2(log, STDOUT_FILENO);
        dup2(errors, STDERR_FILENO);
        close(log);
        if (errors != log)
            close(errors);
        execvp(program.c_str(), argv.data());
        _exit(127);
    }
    int status{};
    pid_t waited;
    do { waited = waitpid(pid, &status, 0); } while (waited < 0 && errno == EINTR);
    return waited >= 0 && WIFEXITED(status) ? WEXITSTATUS(status) : 1;
#endif
}

std::vector<std::string> CompilerArguments(const nlohmann::json& entry)
{
    if (entry.contains("arguments"))
        return entry.at("arguments").get<std::vector<std::string>>();
    std::vector<std::string> result;
    const auto command = entry.at("command").get<std::string>();
#ifdef _WIN32
    int count = 0;
    const auto words = CommandLineToArgvW(fs::u8path(command).wstring().c_str(), &count);
    if (!words)
        throw std::runtime_error("Cannot read the compiler command.");
    for (int i = 0; i < count; ++i)
        result.push_back(fs::path(words[i]).u8string());
    LocalFree(words);
#else
    wordexp_t words{};
    if (wordexp(command.c_str(), &words, WRDE_NOCMD) != 0)
        throw std::runtime_error("Cannot read the compiler command.");
    for (std::size_t i = 0; i < words.we_wordc; ++i)
        result.emplace_back(words.we_wordv[i]);
    wordfree(&words);
#endif
    return result;
}

fs::path ClangCompiler()
{
#ifdef _WIN32
    wchar_t path[32768];
    const auto length = SearchPathW(nullptr, L"clang++.exe", nullptr, ARRAYSIZE(path), path, nullptr);
    if (length && length < ARRAYSIZE(path))
        return path;
    if (const auto programFiles = std::getenv("ProgramFiles"))
    {
        const auto visualStudio = fs::u8path(programFiles) / "Microsoft Visual Studio";
        if (fs::is_directory(visualStudio))
            for (const auto& release : fs::directory_iterator(visualStudio))
                if (release.is_directory())
                    for (const auto& edition : fs::directory_iterator(release.path()))
                    {
                        const auto compiler = edition.path() / "VC/Tools/Llvm/x64/bin/clang++.exe";
                        if (fs::is_regular_file(compiler))
                            return compiler;
                    }
    }
    return "clang++.exe";
#else
    return "clang++";
#endif
}
}

NativeProject::NativeProject(fs::path root, fs::path doxygen)
    : Root(fs::canonical(root)), Doxygen(fs::canonical(doxygen))
{
    if (!fs::is_directory(Root / "Source") || !fs::is_regular_file(Doxygen))
        throw std::runtime_error("Expected a project Source directory and a Doxygen executable.");
    std::random_device random;
    WorkDirectory = fs::temp_directory_path() / ("ue-cpp-mcp-" + std::to_string(random()) + "-" + std::to_string(random()));
    if (!fs::create_directory(WorkDirectory))
        throw std::runtime_error("Cannot create private Doxygen working directory.");
}

NativeProject::~NativeProject()
{
    std::error_code error;
    fs::remove_all(WorkDirectory, error);
}

fs::path NativeProject::Resolve(const fs::path& path) const
{
    const auto resolved = fs::weakly_canonical(Root / path);
    const auto relative = resolved.lexically_relative(Root);
    if (relative.empty() || relative.is_absolute() || *relative.begin() == "..")
        throw std::runtime_error("Path is outside the project.");
    return resolved;
}

fs::path NativeProject::Index()
{
    const auto output = WorkDirectory / "index";
    RunDoxygen(output, false);
    return output / "xml";
}

fs::path NativeProject::IndexDeclaration(const std::string& declaration) const
{
    const auto directory = WorkDirectory / "proposed-signature";
    fs::create_directories(directory);
    const auto input = directory / "Signature.h";
    std::ofstream source(input, std::ios::binary | std::ios::trunc);
    source.exceptions(std::ios::badbit | std::ios::failbit);
    source << declaration;
    source.close();
    const auto output = directory / "index";
    RunDoxygen(output, false, false, input);
    return output / "xml";
}

std::string NativeProject::AnalyzeCpp(const fs::path& translationUnit, const std::string& name,
                                      const std::string* replacement) const
{
    const auto source = Resolve(translationUnit);
    auto directory = Root;
    auto compiler = ClangCompiler();
    std::vector<std::string> args;
    const auto database = Root / "compile_commands.json";
    if (fs::is_regular_file(database))
        for (const auto& entry : nlohmann::json::parse(ReadBytes(database)))
        {
            const auto cwd = fs::u8path(entry.at("directory").get<std::string>());
            if (fs::weakly_canonical(cwd / fs::u8path(entry.at("file").get<std::string>())) != source)
                continue;
            directory = cwd;
            auto original = CompilerArguments(entry);
            if (original.empty())
                throw std::runtime_error("The C++ compilation entry has no compiler.");
            const auto driver = fs::u8path(original.front()).filename().stem().string();
            if (driver == "cl" || driver == "clang-cl")
                args.push_back("--driver-mode=cl");
            for (std::size_t i = 1; i < original.size(); ++i)
            {
                const auto& argument = original[i];
                if (argument == "-o" || argument == "-MF" || argument == "-MT" || argument == "-MQ")
                    ++i;
                else if (argument != "-c" && argument != "/c" && argument != "-MD" && argument != "-MMD" &&
                         argument.rfind("/Fo", 0) != 0 && argument.rfind("/Fd", 0) != 0)
                    args.push_back(argument);
            }
            break;
        }
    if (args.empty())
        args = {"-x", "c++", "-std=c++17", "-I" + (Root / "Source").generic_u8string(), source.generic_u8string()};
    if (replacement)
    {
        const auto contents = WorkDirectory / "replacement.cpp";
        std::ofstream sourceFile(contents, std::ios::binary | std::ios::trunc);
        sourceFile.exceptions(std::ios::badbit | std::ios::failbit);
        sourceFile << *replacement;
        sourceFile.close();
        const auto overlay = WorkDirectory / "replacement.json";
        std::ofstream mapping(overlay, std::ios::binary | std::ios::trunc);
        mapping.exceptions(std::ios::badbit | std::ios::failbit);
        mapping << nlohmann::json{{"version", 0}, {"use-external-names", false}, {"roots", nlohmann::json::array({
            {{"type", "file"}, {"name", source.generic_u8string()}, {"external-contents", contents.generic_u8string()}}
        })}};
        mapping.close();
        args.insert(args.end(), {"-Xclang", "-ivfsoverlay", "-Xclang", overlay.generic_u8string()});
    }
    args.insert(args.end(), {"-fsyntax-only", "-Xclang", "-ast-dump=json", "-Xclang", "-ast-dump-filter=" + name});
    const auto output = WorkDirectory / "clang.json";
    const auto log = WorkDirectory / "clang.log";
    if (Launch(compiler, args, directory, output, log) != 0)
        throw std::runtime_error("Clang could not analyze the C++ translation unit. " + ReadBytes(log));
    return ReadBytes(output);
}

std::string NativeProject::QueryCppReferences(const std::vector<fs::path>& units, const std::vector<std::string>& names) const
{
    const auto compiler = ClangCompiler();
    const auto query = compiler.parent_path() / ("clang-query" + compiler.extension().string());
    std::string selection;
    for (const auto& name : names)
    {
        if (!selection.empty())
            selection += ',';
        selection += nlohmann::json(name).dump();
    }
    const auto declaration = "namedDecl(hasAnyName(" + selection + ")).bind(\"decl\")";
    const std::vector<std::string> matching = {"-c", "set bind-root false",
        "-c", "match expr(anyOf(declRefExpr(to(" + declaration + ")),memberExpr(member(" + declaration +
            ")),cxxConstructExpr(hasDeclaration(" + declaration + ")))).bind(\"use\")",
        "-c", "match typeLoc(loc(qualType(hasDeclaration(" + declaration + ")))).bind(\"use\")"};

    std::set<fs::path> configured;
    const auto database = Root / "compile_commands.json";
    if (fs::is_regular_file(database))
        for (const auto& entry : nlohmann::json::parse(ReadBytes(database)))
            configured.insert(fs::weakly_canonical(fs::u8path(entry.at("directory").get<std::string>()) /
                fs::u8path(entry.at("file").get<std::string>())));
    auto withDatabase = matching;
    auto standalone = matching;
    for (const auto& unit : units)
        (configured.count(unit) ? withDatabase : standalone).push_back(unit.generic_u8string());
    const auto output = WorkDirectory / "references.txt";
    const auto log = WorkDirectory / "references.log";
    auto run = [&](std::vector<std::string>& arguments, std::initializer_list<std::string> flags) {
        if (arguments.size() == matching.size())
            return std::string{};
        arguments.insert(arguments.end(), flags);
        if (Launch(query, arguments, Root, output, log) != 0)
            throw std::runtime_error("Clang could not check references. " + ReadBytes(log));
        return ReadBytes(output);
    };
    return run(withDatabase, {"-p", Root.generic_u8string()}) +
           run(standalone, {"--", "-x", "c++", "-std=c++17", "-I" + (Root / "Source").generic_u8string()});
}

void NativeProject::RunDoxygen(const fs::path& output, bool html, bool publicHeadersOnly, const fs::path& input,
                               const std::vector<fs::path>& files, const std::vector<std::string>& defines) const
{
    const auto config = WorkDirectory / "Doxyfile";
    const auto source = input.empty() ? Resolve("Source") : input;
    fs::create_directories(output);
    std::ofstream stream(config, std::ios::binary | std::ios::trunc);
    stream.exceptions(std::ios::badbit | std::ios::failbit);
    stream << "PROJECT_NAME = " << QuotePath(Root.filename()) << "\nINPUT = ";
    if (files.empty())
        stream << QuotePath(source);
    else
        for (const auto& file : files)
            stream << QuotePath(Resolve(file)) << ' ';
    stream << "\nOUTPUT_DIRECTORY = " << QuotePath(output) << '\n'
           << "RECURSIVE = YES\nEXCLUDE_SYMLINKS = YES\nEXTRACT_ALL = YES\nQUIET = YES\nWARN_IF_UNDOCUMENTED = NO\n"
           << "EXTRACT_PRIVATE = " << (publicHeadersOnly ? "NO" : "YES") << '\n'
           << "FILE_PATTERNS = " << (publicHeadersOnly ? "*.h *.hpp *.hh *.hxx" : "*.h *.hpp *.hh *.hxx *.cpp *.cc *.cxx *.inl") << '\n'
           << "UNREAL_ENGINE_SUPPORT = YES\n"
           << "REFERENCES_RELATION = YES\nREFERENCED_BY_RELATION = YES\n"
           << "GENERATE_LATEX = NO\nGENERATE_XML = YES\n"
           << "GENERATE_HTML = " << (html ? "YES" : "NO") << '\n';
    if (html)
        stream << "REPEAT_BRIEF = NO\nVERBATIM_HEADERS = NO\nHTML_CODE_FOLDING = NO\n"
                  "SEARCHENGINE = NO\nGENERATE_TREEVIEW = NO\nUSE_MATHJAX = YES\nMATHJAX_VERSION = MathJax_3\n"
                  "MATHJAX_FORMAT = SVG\nMERMAID_RENDER_MODE = CLIENT_SIDE\nIMAGE_PATH = .\n"
                  "EXAMPLE_PATH = .\nMERMAIDFILE_DIRS = .\n";
    if (!files.empty())
    {
        stream << "INTERNAL_DOCS = " << (publicHeadersOnly ? "NO" : "YES") << '\n'
               << "RECURSIVE = NO\nFILE_PATTERNS = *.h *.hpp *.hh *.hxx *.cpp *.cc *.cxx *.c *.inl *.dox *.py\n"
                  "EXTRACT_STATIC = YES\nEXTRACT_ANON_NSPACES = YES\nENABLE_PREPROCESSING = YES\n"
                  "MACRO_EXPANSION = YES\nEXPAND_ONLY_PREDEF = YES\nSEARCH_INCLUDES = NO\nFULL_PATH_NAMES = YES\n"
                  "XML_PROGRAMLISTING = NO\nSOURCE_BROWSER = NO\n"
               << "JAVADOC_AUTOBRIEF = " << (html ? "NO" : "YES") << '\n'
               << "HIDE_IN_BODY_DOCS = NO\nVERBATIM_HEADERS = NO\nSTRIP_FROM_PATH = " << QuotePath(Root) << '\n'
               << "PREDEFINED += ";
        static const std::regex exportMacro(R"(\b[A-Z][A-Z0-9_]*_API\b)");
        std::set<std::string> macros;
        for (const auto& file : files)
        {
            const auto text = ReadBytes(Resolve(file));
            for (auto match = std::sregex_iterator(text.begin(), text.end(), exportMacro);
                 match != std::sregex_iterator{}; ++match)
                macros.insert(match->str());
        }
        for (const auto& macro : macros)
            stream << QuotePath(fs::u8path(macro + '=')) << ' ';
        for (const auto& define : defines)
            stream << QuotePath(fs::u8path(define)) << ' ';
        stream << '\n';
    }
    stream.close();
    const auto log = WorkDirectory / "doxygen.log";
    if (Launch(Doxygen, {config.generic_u8string()}, Root, log, log) != 0)
        throw std::runtime_error("Doxygen failed. See " + log.u8string());
    if (!fs::is_regular_file(output / (html ? "html/index.html" : "xml/index.xml")))
        throw std::runtime_error("Doxygen did not produce the requested output.");
}

std::string ReadBytes(const fs::path& path)
{
    std::ifstream input(path, std::ios::binary);
    if (!input || !fs::is_regular_file(path))
        throw std::runtime_error("Cannot read file: " + path.u8string());
    return {std::istreambuf_iterator<char>(input), std::istreambuf_iterator<char>()};
}
}

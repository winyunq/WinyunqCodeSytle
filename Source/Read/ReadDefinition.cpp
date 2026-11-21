#include "ReadDefinition.h"

#include <stdexcept>

namespace WinyunqCodeSytle
{
SourceDefinition ReadDefinition(const NativeProject& project, const Symbol& symbol)
{
    const auto node = symbol.Node.child("location");
    const auto bodyFile = node.attribute("bodyfile");
    const auto bodyStart = node.attribute("bodystart").as_uint();
    const auto end = node.attribute("bodyend").as_uint();
    if (!bodyFile || !bodyStart || end < bodyStart)
        throw std::runtime_error("Doxygen has no definition range for " + symbol.Name);
    const auto path = project.Resolve(fs::u8path(bodyFile.value()));
    auto start = bodyStart;
    const auto line = node.attribute("line").as_uint();
    const auto file = node.attribute("file");
    if (file && line && line <= bodyStart && project.Resolve(fs::u8path(file.value())) == path)
        start = line;
    const auto bytes = ReadBytes(path);
    std::size_t cursor = 0;
    std::size_t begin = 0;
    for (unsigned current = 1; current <= end; ++current)
    {
        if (cursor >= bytes.size())
            throw std::runtime_error("Definition location is outside the source file. Reindex before editing.");
        if (current == start)
            begin = cursor;
        const auto next = bytes.find('\n', cursor);
        cursor = next == std::string::npos ? bytes.size() : next + 1;
    }
    return {{path, start}, end, bytes.substr(begin, cursor - begin)};
}
}

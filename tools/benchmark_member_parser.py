"""Compare warm parsers on one self-contained declaration; no project indexing."""
from statistics import median
from time import perf_counter

from tree_sitter import Language, Parser
import tree_sitter_cpp
from clang import cindex


code = ("using int32=int; struct FName {}; "
        "template<class K,class V> struct TMap {}; "
        "struct Probe { TMap<FName, int32> CompletedLevelIndices; };").encode()
start = perf_counter()
parser = Parser(Language(tree_sitter_cpp.language()))
print("tree-sitter setup_ms", round((perf_counter() - start) * 1000, 3), flush=True)
start = perf_counter()
index = cindex.Index.create()
print("libclang setup_ms", round((perf_counter() - start) * 1000, 3), flush=True)


def tree_sitter_parse():
    tree = parser.parse(code)
    assert not tree.root_node.has_error


def clang_parse():
    unit = index.parse("fragment.cpp", args=["-std=c++20", "-fsyntax-only"],
                       unsaved_files=[("fragment.cpp", code)])
    assert not any(d.severity >= cindex.Diagnostic.Error for d in unit.diagnostics)


for name, parse, count in [("tree-sitter", tree_sitter_parse, 1000),
                           ("libclang", clang_parse, 50)]:
    parse()
    samples = []
    for _ in range(5):
        start = perf_counter()
        for _ in range(count):
            parse()
        samples.append((perf_counter() - start) * 1e6 / count)
    print(name, "median_us", round(median(samples), 2), "parses_per_round", count, flush=True)

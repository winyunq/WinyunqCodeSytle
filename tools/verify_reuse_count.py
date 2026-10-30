"""Task acceptance, not a general architecture oracle. Keep this outside the project.

Compiles real C++ and measures the requested hot path, rather than blacklisting
names or requiring an AI-issued 'I searched' token. Selection is a portable test
double; this does not execute Unreal, UHT, or real Mass entities.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

HARNESS = r'''
#include "Selection.h"
#include <cstdlib>
#include <iostream>
#include <new>

static bool Measuring = false;
static std::size_t Allocations = 0;
void* operator new(std::size_t Count) {
    if (Measuring) ++Allocations;
    if (void* Value = std::malloc(Count ? Count : 1)) return Value;
    throw std::bad_alloc();
}
void operator delete(void* Value) noexcept { std::free(Value); }
void operator delete(void* Value, std::size_t) noexcept { std::free(Value); }

int main() {
    Fixture::Selection Selection(65536);
    Fixture::HUD HUD;
    bool Passed = true;
    std::cout << "{\"world_entities\":65536,\"cases\":[";
    bool First = true;
    for (int Expected : {3, 9, 0, 1, 17}) {
        Selection.SetSelection(Expected);
        Fixture::MembershipQueries = Fixture::SelectionCopies = Allocations = 0;
        Measuring = true;
        const int Actual = HUD.GetSelectedCount(Selection);
        Measuring = false;
        Passed = Passed && Actual == Expected && Fixture::MembershipQueries == 0
            && Fixture::SelectionCopies == 0 && Allocations == 0;
        if (!First) std::cout << ",";
        First = false;
        std::cout << "{\"expected\":" << Expected << ",\"actual\":" << Actual
            << ",\"world_membership_queries\":" << Fixture::MembershipQueries
            << ",\"selection_copies\":" << Fixture::SelectionCopies
            << ",\"allocations\":" << Allocations << "}";
    }
    std::cout << "],\"passed\":" << (Passed ? "true" : "false") << "}\n";
    return Passed ? 0 : 2;
}
'''


def verify(project: Path, compile_only: bool = False) -> int:
    compiler = shutil.which('g++') or shutil.which('clang++')
    if not compiler:
        raise RuntimeError('This portable probe needs g++ or clang++; it is not an Unreal build.')
    with tempfile.TemporaryDirectory(prefix='reuse-acceptance-') as tmp:
        folder = Path(tmp)
        harness = folder/'Harness.cpp'; harness.write_text(HARNESS, encoding='utf-8')
        exe = folder/('probe.exe' if sys.platform == 'win32' else 'probe')
        command = [compiler, '-std=c++17', '-O2', '-I', str(project/'Source'),
                   str(project/'Source/HUD.cpp'), str(harness), '-o', str(exe)]
        build = subprocess.run(command, capture_output=True, text=True, timeout=40, check=False)
        if build.returncode:
            print(build.stderr[-4000:]); return 1
        if compile_only:
            print('Compile passed; task behavior and cost were NOT checked.')
            return 0
        run = subprocess.run([str(exe)], capture_output=True, text=True, timeout=10, check=False)
        print(run.stdout.strip())
        if run.returncode:
            print('FAIL: GetSelectedCount must stay correct after selection changes and use '
                  'zero world membership queries, zero selection copies, zero allocations. '
                  'Existing API: Selection::GetSelectedEntitiesView().Num().')
            if run.stderr: print(run.stderr[-1000:])
        return run.returncode


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--project', required=True, type=Path)
    parser.add_argument('--compile-only', action='store_true')
    args = parser.parse_args()
    sys.exit(verify(args.project.resolve(), args.compile_only))

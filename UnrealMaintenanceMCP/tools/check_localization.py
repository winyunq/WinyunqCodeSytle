"""Check gathered UE text identities against the project's translation inputs."""
import argparse
import fnmatch
import json
import re
import subprocess
from pathlib import Path


def unlocalized_literals_added(old_code, new_code):
    """Warn on newly introduced literal FText that UE cannot gather."""
    pattern = r'FText::(?:FromString|AsCultureInvariant)\s*\(\s*(?:FString::Printf\s*\(\s*)?TEXT\s*\(\s*"((?:\\.|[^"\\])*)"'
    previous = set(re.findall(pattern, old_code))
    return sorted({value for value in re.findall(pattern, new_code)
                   if value not in previous and re.search(r'[A-Za-z\u3400-\u9fff]', value)})


def read_json(path):
    raw = Path(path).read_bytes()
    return json.loads(raw.decode("utf-16" if raw.startswith((b"\xff\xfe", b"\xfe\xff")) else "utf-8-sig"))

def find_gaps(entries, translations, languages=("zh", "en")):
    by_id = {}
    for row in translations:
        identity = (row["namespace"], row["key"])
        if identity in by_id and by_id[identity] != row:
            raise ValueError(f"Conflicting translations: {identity}")
        by_id[identity] = row

    gaps = []
    for entry in entries:
        identity = (entry["namespace"], entry["key"])
        row = by_id.get(identity, {})
        missing = [language for language in languages if not row.get(language, "").strip()]
        source = entry["source"].replace("\r\n", "\n")
        stale = (entry["source"] != row["source"] if "source" in row else
                 bool(row) and source not in [row.get(language, "").replace("\r\n", "\n") for language in languages])
        native_newlines_changed = ("source" in row and row["source"] != row.get("zh", "")
                                   and source == row.get("zh", "").replace("\r\n", "\n"))
        if missing or stale or native_newlines_changed:
            gaps.append(dict(entry, missing_languages=missing, source_changed=stale,
                             native_newlines_changed=native_newlines_changed))
    return gaps


def gather_entries(manifest):
    """Read the manifest produced by UE's native GatherText commandlet."""
    entries = []
    def visit(node, parent=""):
        namespace = ".".join(filter(None, (parent, node.get("Namespace", ""))))
        for child in node.get("Children", []):
            for key in child.get("Keys", []):
                entries.append(dict(namespace=namespace, key=key["Key"],
                                    source=child["Source"]["Text"], location=key.get("Path", "")))
        for child in node.get("Subnamespaces", []):
            visit(child, namespace)
    visit(read_json(manifest))
    if not entries:
        raise ValueError("Gathered manifest is empty; localization coverage was not checked")
    return entries


def read_archives(paths):
    """Read UE archives without replacing UE's gather/import/compiler."""
    rows = {}
    for specification in paths:
        language, path = specification.split("=", 1)
        def visit(node, parent=""):
            namespace = ".".join(filter(None, (parent, node.get("Namespace", ""))))
            for child in node.get("Children", []):
                identity = (namespace, child["Key"])
                row = rows.setdefault(identity, dict(namespace=namespace, key=child["Key"]))
                source = child["Source"]["Text"]
                if "source" in row and row["source"] != source:
                    raise ValueError(f"Archive sources disagree: {identity}")
                row["source"] = source
                row[language] = child["Translation"]["Text"]
            for child in node.get("Subnamespaces", []):
                visit(child, namespace)
        visit(read_json(path))
    return list(rows.values())


def native_gather(project, editor):
    project = Path(project).resolve()
    output = project / "Saved/LocalizationChecks"
    output.mkdir(parents=True, exist_ok=True)
    config = output / "Gather.ini"
    config.write_text(f"""[CommonSettings]
SourcePath={output.as_posix()}
DestinationPath={output.as_posix()}
ManifestName=Game.manifest
ArchiveName=Game.archive
NativeCulture=zh-Hans-CN
CulturesToGenerate=zh-Hans-CN
CulturesToGenerate=en

[GatherTextStep0]
CommandletClass=GatherTextFromSource
SearchDirectoryPaths=Source
SearchDirectoryPaths=Plugins
SearchDirectoryPaths=Config
ExcludePathFilters=Config/Localization/*
ExcludePathFilters={project.as_posix()}/Plugins/*/Intermediate/*
ExcludePathFilters={project.as_posix()}/Plugins/FabUmgMcp/*
ExcludePathFilters={project.as_posix()}/Plugins/*/Source/*Editor*/*
FileNameFilters=*.h
FileNameFilters=*.cpp
FileNameFilters=*.ini
ShouldGatherFromEditorOnlyData=false

[GatherTextStep1]
CommandletClass=GatherTextFromAssets
IncludePathFilters=Content/UI/*
IncludePathFilters=Content/Default/Setting/*
IncludePathFilters=Plugins/SettingsWidgetConstructor/Content/*
PackageFileNameFilters=*.uasset
ShouldGatherFromEditorOnlyData=false

[GatherTextStep2]
CommandletClass=GenerateGatherManifest

[GatherTextStep3]
CommandletClass=GenerateGatherArchive

[GatherTextStep4]
CommandletClass=GenerateTextLocalizationReport
bWordCountReport=true
WordCountReportName=Game.csv
bConflictReport=true
ConflictReportName=Game_Conflicts.txt
""", encoding="utf-8")
    with (output / "Gather.log").open("w", encoding="utf-8") as log:
        subprocess.run([str(editor), str(project / (project.name + ".uproject")),
                        "-run=GatherText", "-config=" + str(config), "-Unattended",
                        "-NullRHI", "-NoSound", "-stdout", "-UTF8Output",
                        "-ini:EditorPerProjectUserSettings:[/Script/ModelContextProtocolEngine.ModelContextProtocolSettings]:bAutoStartServer=False"],
                       stdout=log, stderr=subprocess.STDOUT, check=True, timeout=600)
    return output / "Game.manifest"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--project", type=Path)
    parser.add_argument("--editor", type=Path, help="UnrealEditor-Cmd.exe; invokes UE's native gather")
    parser.add_argument("--output", type=Path, help="Write the check report outside source inputs")
    parser.add_argument("--catalog", nargs="+", type=Path, default=[])
    parser.add_argument("--archive", action="append", default=[], help="LANGUAGE=path to a native UE archive")
    parser.add_argument("--namespace", action="append", help="Exact namespace; default checks all gathered text")
    parser.add_argument("--location", action="append", help="Include native source/asset locations matching this wildcard")
    args = parser.parse_args()
    if args.editor:
        if not args.project:
            parser.error("--editor requires --project")
        args.manifest = native_gather(args.project, args.editor)
    if not args.manifest:
        parser.error("provide --manifest or --project and --editor")
    entries = gather_entries(args.manifest)
    if not args.catalog and not args.archive:
        parser.error("provide --catalog or --archive")
    if args.namespace or args.location:
        entries = [entry for entry in entries
                   if entry["namespace"] in (args.namespace or [])
                   or any(fnmatch.fnmatch(entry["location"], pattern) for pattern in (args.location or []))]
        if not entries:
            raise ValueError("Requested namespace was not gathered")
    translations = [row for path in args.catalog
                    for row in read_json(path)]
    translations.extend(read_archives(args.archive))
    gaps = find_gaps(entries, translations)
    report = dict(gathered=len(entries), gaps=gaps)
    if args.output:
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(dict(gathered=len(entries), missing=len(gaps), report=str(args.output))))
    else:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    return int(bool(gaps))


if __name__ == "__main__":
    raise SystemExit(main())

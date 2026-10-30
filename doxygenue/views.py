"""Doxygen XML projections. No Doxygen marker language inside MCP text fields."""
from __future__ import annotations
import copy
import re
import xml.etree.ElementTree as ET


def prose(node):
    if node is None:
        return ""
    return re.sub(r"\s+", " ", "".join(node.itertext())).strip()


def blocks(node):
    """Project rich documentation into semantic blocks, not a copy of XML tags."""
    if node is None:
        return []
    result = []
    if node.text and node.text.strip():result.append(node.text.strip())
    rich_tags={"programlisting","itemizedlist","orderedlist","table","sect1","sect2","sect3","sect4","parameterlist","simplesect","xrefsect","image","verbatim"}
    for child in node:
        if child.tag == "programlisting":
            lines=[]
            for line in child.findall("codeline"):
                text=re.sub(r"<sp\s*/>"," ",ET.tostring(line,encoding="unicode"))
                lines.append("".join(ET.fromstring(text).itertext()))
            result.append({"code":"\n".join(lines)})
        elif child.tag in {"para","briefdescription","detaileddescription","parameterdescription","listitem"}:
            if not any(x.tag in rich_tags for x in child.iter()):
                if prose(child):result.append(prose(child))
            else:result.extend(blocks(child))
        elif child.tag in {"itemizedlist","orderedlist"}:
            result.append({"items" if child.tag=="itemizedlist" else "steps":[blocks(item) for item in child.findall("listitem")]})
        elif child.tag=="table":
            result.append({"table":[[blocks(entry) for entry in row.findall("entry")] for row in child.findall("row")]})
        elif child.tag in {"sect1","sect2","sect3","sect4"}:
            body=copy.deepcopy(child);title=body.find("title")
            if title is not None:body.remove(title)
            result.append({"title":prose(title),"content":blocks(body)})
        elif len(child)==0 and not child.attrib:
            if prose(child):result.append(prose(child))
        else:
            # Rare constructs retain all content/attributes rather than being
            # silently summarized. Ordinary comments never take this fallback.
            item={"kind":child.tag,"content":blocks(child)}
            if child.attrib:item["attributes"]=dict(child.attrib)
            result.append(item)
        if child.tail and child.tail.strip():result.append(child.tail.strip())
    return result


def documentation_from_xml(member):
    detail = member.find("detaileddescription")
    result = {}
    brief = prose(member.find("briefdescription"))
    if brief:
        result["brief"] = brief
    for paramlist in member.findall(".//parameterlist"):
        key = "tparams" if paramlist.get("kind") == "templateparam" else "params"
        if paramlist.get("kind") not in {"param", "templateparam"}:
            continue
        for item in paramlist.findall("parameteritem"):
            desc = prose(item.find("parameterdescription"))
            for name in item.findall("parameternamelist/parametername"):
                value = {"description": desc, "direction": name.get("direction")} if name.get("direction") else desc
                result.setdefault(key, {})[prose(name)] = value
    mapping = {"return": "returns", "note": "notes", "warning": "warnings", "pre": "preconditions", "post": "postconditions", "see": "see"}
    for section in member.findall(".//simplesect"):
        key = mapping.get(section.get("kind"))
        if key:
            value = prose(section)
            if key == "returns":
                result[key] = (result.get(key, "") + " " + value).strip()
            else:
                result.setdefault(key, []).append(value)
    for paramlist in member.findall(".//parameterlist"):
        if paramlist.get("kind") == "retval":
            for item in paramlist.findall("parameteritem"):
                for name in item.findall("parameternamelist/parametername"):
                    result.setdefault("return_values", {})[prose(name)] = prose(item.find("parameterdescription"))
    # Full documentation uses the same semantic fields, richer values where
    # needed, and preserves remaining paragraphs/examples. Nothing is sent twice.
    full=copy.deepcopy(result)
    for paramlist in member.findall(".//parameterlist"):
        key={"param":"params","templateparam":"tparams","exception":"exceptions","retval":"return_values"}.get(paramlist.get("kind"),"other_parameters")
        for item in paramlist.findall("parameteritem"):
            rich=blocks(item.find("parameterdescription"))
            value=rich[0] if len(rich)==1 else rich
            for n in item.findall("parameternamelist/parametername"):
                full.setdefault(key,{})[prose(n)]={"description":value,"direction":n.get("direction")} if n.get("direction") else value
    names={"return":"returns","note":"notes","warning":"warnings","pre":"preconditions","post":"postconditions","see":"see"}
    full_sections={}
    for section in member.findall(".//simplesect"):
        key=names.get(section.get("kind"),section.get("kind") or "other")
        rich=blocks(section);value=rich[0] if len(rich)==1 else rich
        full_sections.setdefault(key,[]).append(value)
    for key,values in full_sections.items():
        full[key]=values[0] if key=="returns" and len(values)==1 else values
    def remaining(node):
        if node is None:return []
        root=copy.deepcopy(node)
        for parent in root.iter():
            for child in list(parent):
                if child.tag in {"parameterlist","simplesect"}:
                    tail=child.tail
                    parent.remove(child)
                    if tail and tail.strip():parent.text=(parent.text or "")+tail
        return blocks(root)
    detail_blocks=remaining(detail)
    if detail_blocks:full["details"]=detail_blocks[0] if len(detail_blocks)==1 else detail_blocks
    internal=remaining(member.find("inbodydescription"))
    if internal:full["internal"]=internal[0] if len(internal)==1 else internal
    result["full"]=full
    return result


def projection(symbol, view):
    data = symbol.documentation
    if view == "brief":
        return {"brief": data.get("brief", symbol.brief)}
    if view in {"overview", "interface"}:
        result = {"signature": symbol.signature}
        for key in ("brief", "params", "tparams", "returns", "return_values", "notes", "warnings", "preconditions"):
            if data.get(key):
                result[key] = data[key]
        return result
    return {"signature": symbol.signature, "documentation": data.get("full", {})}


def compact_result(tool, output, args):
    """Strip diagnostic duplication at the RPC boundary, not by lossy prose AI."""
    if tool == "Read":
        if args.get("view") in {"changes", "impact", "capabilities", "inventory", "history"}:
            return output
        if "projection" in output:
            result = copy.deepcopy(output["projection"])
        elif "results" in output:
            results = []
            for candidate in output["results"]:
                item = {k: candidate[k] for k in ("name", "brief") if k in candidate}
                # Path is useful for disambiguating homonyms, not a required ID.
                if sum(c["name"] == candidate["name"] for c in output["results"]) > 1:
                    item["path"] = candidate.get("file", "")
                if candidate.get("is_suggestion"):
                    item["match"] = candidate.get("match")
                results.append(item)
            return {"results": results, "total": output.get("total", len(results))}
        else:
            result = {"text": output.get("text", "")}
            if output.get("next_offset") is not None:
                result["next_offset"] = output["next_offset"]
                result["total_chars"] = output.get("total_chars")
        if args.get("query"):
            result = {"name": output.get("name"), **result}
            search = output.get("search", {})
            if search.get("is_suggestion"):
                result["match"] = search.get("match")
                if search.get("total", 0) > 1:
                    result["alternatives"] = search["total"] - 1
        if output.get("locked"):
            result["locked"] = True
        return result
    if output.get("status") == "preview" and "files" in output:
        result = {k: v for k, v in output.items() if k not in {"not_applied", "reason", "target", "files", "operation", "kind"} and v is not None}
        result["files"] = [{k: v for k, v in f.items() if k in {"file", "diff"} or k == "diff_truncated" and v} for f in output["files"]]
        if output.get("reason"):
            result["reason"] = output["reason"]
        return result
    if output.get("status") == "applied":
        return {k: v for k, v in output.items() if k not in {"operation", "kind", "preview_id", "journal", "documentation_auto_rewritten"}}
    if tool == "Write" and args.get("action") == "prepare":
        return {k: v for k, v in output.items() if k not in {"target", "revision", "code_revision", "revision_basis", "source_hash", "location_line"}}
    return output

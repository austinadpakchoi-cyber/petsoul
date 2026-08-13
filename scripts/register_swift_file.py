#!/usr/bin/env python3
"""向经典 pbxproj（objectVersion 56）登记 / 注销 Swift 源文件。

背景：iOS 工程由 Xcode 生成经典 pbxproj，新增 Swift 文件必须在以下四处同步登记，
否则 Xcode 不会收录编译：
  1. PBXBuildFile section       —— 编译引用（<name> in Sources）
  2. PBXFileReference section   —— 文件引用
  3. PBXGroup children          —— 归属目录分组
  4. PBXSourcesBuildPhase files —— App target 编译列表
本脚本自动化这四步，并自动分配下一个可用的 24 位 hex ID（file ref 用 ...001NN、
build file 用 ...002NN），避免手工改错。

用法：
  # 登记新文件（默认 --add）
  python scripts/register_swift_file.py \
      --file PetCoreModels.swift --file JourneyModels.swift

  # 指定分组与编译阶段（默认 Models 组 / App Sources 阶段）
  python scripts/register_swift_file.py \
      --group A00000000000000000000035 \
      --sources-phase A00000000000000000000010 \
      --file JourneyMapView.swift

  # 注销文件（拆分 God File 时删除旧文件）
  python scripts/register_swift_file.py --remove --file PetModels.swift

  --file 的取值是「相对所属 group 目录的文件名」。文件本体需自行创建/删除，
  本脚本只负责改 project.pbxproj。
"""

import argparse
import re
import sys
from pathlib import Path

T = "\t"
DEFAULT_PBXPROJ = "PetJourneyIOS/PetJourneyIOS.xcodeproj/project.pbxproj"
DEFAULT_GROUP = "A00000000000000000000032"          # Models
DEFAULT_SOURCES_PHASE = "A00000000000000000000010"  # PetJourneyIOS target Sources

HEX24 = r"[0-9A-Fa-f]{24}"


def _read(pbxproj: Path):
    raw = pbxproj.read_bytes()
    crlf = b"\r\n" in raw
    text = raw.decode("utf-8")
    if crlf:
        text = text.replace("\r\n", "\n")
    return text, crlf


def _write(pbxproj: Path, text: str, crlf: bool) -> None:
    if crlf:
        text = text.replace("\n", "\r\n")
    pbxproj.write_bytes(text.encode("utf-8"))


def _next_id(text: str, line_re: "re.Pattern") -> str:
    """从给定行正则中取最大 24 位 hex ID，返回 +1 后的同格式 ID。"""
    ids = [int(m.group(1), 16) for m in line_re.finditer(text)]
    if not ids:
        raise RuntimeError("未在 pbxproj 中找到任何匹配的 ID，无法分配下一个可用 ID")
    return f"{max(ids) + 1:024X}"


def _file_ref_line(ref_id: str, name: str) -> str:
    return (
        f"{T*2}{ref_id} /* {name} */ = {{isa = PBXFileReference; "
        f'lastKnownFileType = sourcecode.swift; path = {name}; sourceTree = "<group>"; }};'
    )


def _build_file_line(build_id: str, ref_id: str, name: str) -> str:
    return (
        f"{T*2}{build_id} /* {name} in Sources */ = "
        f"{{isa = PBXBuildFile; fileRef = {ref_id} /* {name} */; }};"
    )


def _insert_into_list(text: str, block_id: str, list_key: str, lines: list) -> str:
    """在指定 block（group 或 build phase）的列表（children/files）末尾插入新行。"""
    start = text.index(f"\t\t{block_id} /* ")
    list_marker = f"{list_key} = (\n"
    lpos = text.index(list_marker, start)
    close_marker = "\n\t\t\t);"
    cpos = text.index(close_marker, lpos + len(list_marker))
    insert = "\n" + "\n".join(lines)
    return text[:cpos] + insert + text[cpos:]


def add_files(text: str, group_id: str, sources_phase: str, names: list) -> str:
    file_ref_re = re.compile(
        rf"^\t\t({HEX24}) /\* .+? \*/ = \{{isa = PBXFileReference;", re.M
    )
    build_file_re = re.compile(
        rf"^\t\t({HEX24}) /\* .+? in Sources \*/ = \{{isa = PBXBuildFile;", re.M
    )

    next_ref = int(_next_id(text, file_ref_re), 16)
    next_build = int(_next_id(text, build_file_re), 16)

    ref_lines, build_lines, child_lines, source_lines = [], [], [], []
    for name in names:
        ref_id = f"{next_ref:024X}"
        build_id = f"{next_build:024X}"
        next_ref += 1
        next_build += 1
        ref_lines.append(_file_ref_line(ref_id, name))
        build_lines.append(_build_file_line(build_id, ref_id, name))
        child_lines.append(f"{T*4}{ref_id} /* {name} */,")
        source_lines.append(f"{T*4}{build_id} /* {name} in Sources */,")

    # 1 & 2: 文件引用 + 编译引用（各自 section 末尾追加）
    for marker, lines in (
        ("/* End PBXBuildFile section */", build_lines),
        ("/* End PBXFileReference section */", ref_lines),
    ):
        if marker not in text:
            raise RuntimeError(f"找不到 section 结束标记：{marker}")
        text = text.replace(marker, "\n".join(lines) + "\n" + marker, 1)

    # 3: 归属 group 的 children
    text = _insert_into_list(text, group_id, "children", child_lines)

    # 4: Sources 编译阶段的 files
    text = _insert_into_list(text, sources_phase, "files", source_lines)

    return text


def remove_files(text: str, names: list) -> str:
    for name in names:
        esc = re.escape(name)
        text = re.sub(
            rf"\t\t{HEX24} /\* {esc} in Sources \*/ = \{{isa = PBXBuildFile; [^\n]*\}};\n",
            "", text, count=1,
        )
        text = re.sub(
            rf"\t\t{HEX24} /\* {esc} \*/ = \{{isa = PBXFileReference; [^\n]*\}};\n",
            "", text, count=1,
        )
        text = re.sub(rf"\t\t\t\t{HEX24} /\* {esc} \*/,\n", "", text, count=1)
        text = re.sub(rf"\t\t\t\t{HEX24} /\* {esc} in Sources \*/,\n", "", text, count=1)
    return text


def main() -> int:
    parser = argparse.ArgumentParser(description="登记/注销 pbxproj 中的 Swift 源文件")
    parser.add_argument("--pbxproj", default=DEFAULT_PBXPROJ, help="project.pbxproj 路径")
    parser.add_argument("--file", action="append", required=True,
                        help="文件名（相对所属 group），可重复")
    parser.add_argument("--group", default=DEFAULT_GROUP, help="所属 PBXGroup 的 24 位 ID")
    parser.add_argument("--sources-phase", default=DEFAULT_SOURCES_PHASE,
                        help="PBXSourcesBuildPhase 的 24 位 ID")
    parser.add_argument("--remove", action="store_true", help="注销文件而非登记")
    args = parser.parse_args()

    pbxproj = Path(args.pbxproj)
    if not pbxproj.is_file():
        print(f"错误：找不到 {pbxproj}", file=sys.stderr)
        return 2

    text, crlf = _read(pbxproj)
    if args.remove:
        text = remove_files(text, args.file)
    else:
        text = add_files(text, args.group, args.sources_phase, args.file)
    _write(pbxproj, text, crlf)

    action = "注销" if args.remove else "登记"
    print(f"已{action} {len(args.file)} 个文件：{', '.join(args.file)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

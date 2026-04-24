"""飞书 docx Block → Markdown 反转转换器。

用于下行同步（飞书 → 本地）：把 /docx/v1/documents/{id}/blocks 返回的
扁平化 block 列表重建成 markdown 文本，便于写入本地 .md 文件。

设计要点：
- 只处理我们会见到的主流 block 类型（text / heading 1-4 / list / code / quote / divider / table）
- 不支持的 block 类型降级为空字符串，不抛异常
- 通过 children 字段保序遍历（比按 parent_id 聚合更稳定）
- 嵌套列表按深度缩进（每层 2 空格）
"""

from __future__ import annotations

from typing import Any

# Feishu 官方 block_type 编码
_BT_PAGE = 1
_BT_TEXT = 2
_BT_H1 = 3
_BT_H2 = 4
_BT_H3 = 5
_BT_H4 = 6
_BT_H5 = 7
_BT_H6 = 8
_BT_H7 = 9
_BT_H8 = 10
_BT_H9 = 11
_BT_BULLET = 12
_BT_ORDERED = 13
_BT_CODE = 14
_BT_QUOTE = 15
_BT_TODO = 17
_BT_DIVIDER = 22
_BT_TABLE = 27
_BT_TABLE_CELL = 28
_BT_QUOTE_CONTAINER = 34


_HEADING_LEVELS = {
    _BT_H1: 1,
    _BT_H2: 2,
    _BT_H3: 3,
    _BT_H4: 4,
    _BT_H5: 5,
    _BT_H6: 6,
    _BT_H7: 6,
    _BT_H8: 6,
    _BT_H9: 6,
}

_HEADING_FIELDS = {
    _BT_H1: "heading1",
    _BT_H2: "heading2",
    _BT_H3: "heading3",
    _BT_H4: "heading4",
    _BT_H5: "heading5",
    _BT_H6: "heading6",
    _BT_H7: "heading7",
    _BT_H8: "heading8",
    _BT_H9: "heading9",
}


def blocks_to_markdown(blocks: list[dict]) -> str:
    """把 docx API 返回的 block 数组反转成 markdown。

    输入：从 get_doc_blocks() 拿到的扁平化 block 列表
    输出：markdown 字符串（结尾无多余空行）
    """
    if not blocks:
        return ""

    block_map: dict[str, dict] = {b["block_id"]: b for b in blocks}

    # 找根节点：block_type == 1 (page) 或无 parent_id
    root = next(
        (b for b in blocks if b.get("block_type") == _BT_PAGE or not b.get("parent_id")),
        blocks[0],
    )

    lines: list[str] = []
    _render_children(root, block_map, lines, depth=0, list_ctx=None)

    # 清理连续空行（多余 3 个以上的空行压缩到 2 个）
    out: list[str] = []
    blank_count = 0
    for line in lines:
        if line.strip() == "":
            blank_count += 1
            if blank_count <= 1:
                out.append("")
        else:
            blank_count = 0
            out.append(line)

    # 去首尾多余空行
    while out and out[0].strip() == "":
        out.pop(0)
    while out and out[-1].strip() == "":
        out.pop()

    return "\n".join(out)


def _render_children(
    block: dict,
    block_map: dict[str, dict],
    lines: list[str],
    depth: int,
    list_ctx: tuple[str, int] | None,
) -> None:
    """递归渲染 block 的所有 children。

    list_ctx: 父层列表上下文 (list_type, counter)；用于有序列表累加编号。
              None 表示父层不是列表。
    """
    children_ids = block.get("children") or []

    # 在同一层累加 ordered counter
    counter = 1
    for child_id in children_ids:
        child = block_map.get(child_id)
        if not child:
            continue

        bt = child.get("block_type")

        if bt == _BT_TEXT:
            _render_text_block(child, lines, depth, prefix="")

        elif bt in _HEADING_LEVELS:
            level = _HEADING_LEVELS[bt]
            field = _HEADING_FIELDS[bt]
            text = _inline_from_elements(child.get(field, {}).get("elements", []))
            lines.append("")
            lines.append(f"{'#' * level} {text}")
            lines.append("")

        elif bt == _BT_BULLET:
            text = _inline_from_elements(child.get("bullet", {}).get("elements", []))
            lines.append(f"{'  ' * depth}- {text}")
            _render_children(child, block_map, lines, depth + 1, ("bullet", 0))

        elif bt == _BT_ORDERED:
            text = _inline_from_elements(child.get("ordered", {}).get("elements", []))
            lines.append(f"{'  ' * depth}{counter}. {text}")
            counter += 1
            _render_children(child, block_map, lines, depth + 1, ("ordered", counter))

        elif bt == _BT_CODE:
            elements = child.get("code", {}).get("elements", [])
            lang = _language_name(child.get("code", {}).get("style", {}).get("language", 0))
            code_text = "".join(
                e.get("text_run", {}).get("content", "") for e in elements
            )
            lines.append("")
            lines.append(f"```{lang}")
            for ln in code_text.split("\n"):
                lines.append(ln)
            lines.append("```")
            lines.append("")

        elif bt == _BT_QUOTE:
            text = _inline_from_elements(child.get("quote", {}).get("elements", []))
            lines.append(f"> {text}")

        elif bt == _BT_QUOTE_CONTAINER:
            # quote_container 本身没内容，让 children 以 > 前缀渲染
            nested: list[str] = []
            _render_children(child, block_map, nested, depth, None)
            for ln in nested:
                if ln.strip() == "":
                    lines.append(">")
                else:
                    lines.append(f"> {ln}")

        elif bt == _BT_TODO:
            todo = child.get("todo", {})
            text = _inline_from_elements(todo.get("elements", []))
            done = todo.get("style", {}).get("done", False)
            mark = "[x]" if done else "[ ]"
            lines.append(f"{'  ' * depth}- {mark} {text}")
            _render_children(child, block_map, lines, depth + 1, ("todo", 0))

        elif bt == _BT_DIVIDER:
            lines.append("")
            lines.append("---")
            lines.append("")

        elif bt == _BT_TABLE:
            _render_table(child, block_map, lines)

        else:
            # 未知类型：如果有 elements 字段尝试输出纯文本，否则静默跳过
            for key in ("text", "callout"):
                if key in child and "elements" in child[key]:
                    text = _inline_from_elements(child[key].get("elements", []))
                    if text:
                        lines.append(text)
                    break
            # 继续递归 children 不漏掉嵌套内容
            _render_children(child, block_map, lines, depth, None)

        _ = list_ctx  # placeholder for future use


def _render_text_block(block: dict, lines: list[str], depth: int, prefix: str) -> None:
    elements = block.get("text", {}).get("elements", [])
    text = _inline_from_elements(elements)
    if text or prefix:
        indent = "  " * depth
        lines.append(f"{indent}{prefix}{text}")


def _inline_from_elements(elements: list[dict]) -> str:
    """把 text_run 数组合并成带 markdown inline 格式的字符串。"""
    out: list[str] = []
    for el in elements:
        tr = el.get("text_run")
        if not tr:
            # mention / equation / file 等类型，降级
            for k in ("mention_user", "mention_doc", "equation", "file"):
                if k in el:
                    out.append(_render_special_element(k, el[k]))
                    break
            continue
        content = tr.get("content", "")
        style = tr.get("text_element_style") or {}
        out.append(_wrap_inline_style(content, style))
    return "".join(out)


def _wrap_inline_style(content: str, style: dict) -> str:
    """按 text_element_style 把内容包成 markdown inline 标记。

    顺序：inline_code → bold → italic → strikethrough → link
    """
    if not content:
        return ""

    link = style.get("link") or {}
    link_url = link.get("url") if isinstance(link, dict) else None

    if style.get("inline_code"):
        content = f"`{content}`"
        # inline code 通常不再叠加 bold/italic（markdown 规范）
    else:
        if style.get("bold"):
            content = f"**{content}**"
        if style.get("italic"):
            content = f"*{content}*"
        if style.get("strikethrough"):
            content = f"~~{content}~~"

    if link_url:
        content = f"[{content}]({link_url})"

    return content


def _render_special_element(kind: str, data: Any) -> str:
    if kind == "mention_user":
        name = data.get("name") or data.get("user_id", "")
        return f"@{name}" if name else ""
    if kind == "mention_doc":
        title = data.get("title") or data.get("url", "")
        return f"[{title}]({data.get('url', '')})" if data.get("url") else title
    if kind == "equation":
        return f"$${data.get('content', '')}$$"
    if kind == "file":
        return f"[📎 {data.get('name', '文件')}]"
    return ""


def _render_table(table_block: dict, block_map: dict[str, dict], lines: list[str]) -> None:
    """把 table block 反转成 GFM 表格。"""
    table = table_block.get("table", {})
    props = table.get("property", {}) or {}
    col_count = props.get("column_size", 0) or 0
    children_ids = table_block.get("children") or []

    cells: list[str] = []
    for cid in children_ids:
        cell = block_map.get(cid)
        if not cell or cell.get("block_type") != _BT_TABLE_CELL:
            continue
        cell_text_lines: list[str] = []
        _render_children(cell, block_map, cell_text_lines, depth=0, list_ctx=None)
        cells.append(" ".join(l.strip() for l in cell_text_lines if l.strip()))

    if not cells or col_count == 0:
        return

    rows: list[list[str]] = []
    for i in range(0, len(cells), col_count):
        rows.append(cells[i : i + col_count])

    if not rows:
        return

    lines.append("")
    lines.append("| " + " | ".join(rows[0]) + " |")
    lines.append("| " + " | ".join(["---"] * col_count) + " |")
    for row in rows[1:]:
        # 补齐列数
        padded = row + [""] * (col_count - len(row))
        lines.append("| " + " | ".join(padded) + " |")
    lines.append("")


_LANGUAGE_MAP = {
    1: "plain", 2: "abap", 3: "ada", 4: "apache", 5: "apex",
    6: "assembly", 7: "bash", 8: "c", 9: "csharp", 10: "cpp",
    11: "clojure", 12: "coffeescript", 13: "css", 14: "d",
    15: "dart", 16: "delphi", 17: "django", 18: "dockerfile",
    19: "erlang", 20: "fortran", 21: "foxpro", 22: "go",
    23: "groovy", 24: "html", 25: "htmlbars", 26: "http",
    27: "haskell", 28: "json", 29: "java", 30: "javascript",
    31: "julia", 32: "kotlin", 33: "latex", 34: "lisp",
    35: "logo", 36: "lua", 37: "matlab", 38: "makefile",
    39: "markdown", 40: "nginx", 41: "objectivec", 42: "openedge",
    43: "php", 44: "perl", 45: "postscript", 46: "powershell",
    47: "prolog", 48: "protobuf", 49: "python", 50: "r",
    51: "rpg", 52: "ruby", 53: "rust", 54: "sas", 55: "scss",
    56: "scala", 57: "scheme", 58: "scratch", 59: "shell",
    60: "swift", 61: "sql", 62: "tcl", 63: "vbscript",
    64: "vb", 65: "verilog", 66: "vhdl", 67: "visualbasic",
    68: "xml", 69: "xquery", 70: "yaml", 71: "typescript",
    72: "elixir", 73: "elm",
}


def _language_name(code: int) -> str:
    return _LANGUAGE_MAP.get(int(code or 0), "")

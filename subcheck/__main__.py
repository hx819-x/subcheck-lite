"""Run with python3 -m subcheck; only the Python standard library is needed."""

import argparse
import json
import sys
from pathlib import Path

from .core import analyze
from .report import render_html


def resolve_path(path):
    # Python 3.9 raises RuntimeError, rather than OSError, for symlink loops.
    try:
        return path.resolve()
    except RuntimeError as exc:
        raise ValueError(f"无法解析文件路径：{path}（可能存在循环符号链接）") from exc


def main(argv=None):
    parser = argparse.ArgumentParser(description="SubCheck Lite — 离线检查 SRT 字幕，生成中文报告。")
    parser.add_argument("input", type=Path, help="SRT 字幕文件")
    parser.add_argument("--html", type=Path, help="保存可离线打开的 HTML 报告")
    parser.add_argument("--json", type=Path, help="保存 JSON 检查结果")
    parser.add_argument("--encoding", default="utf-8-sig", help="输入编码（默认 utf-8-sig，兼容 UTF-8 BOM）")
    parser.add_argument("--max-chars", type=int, default=24, help="每行可见字符提醒阈值，默认 24")
    parser.add_argument("--min-duration-ms", type=int, default=800, help="最短显示时间提醒阈值（毫秒），默认 800")
    parser.add_argument("--max-cps", type=float, default=18.0, help="每秒可见字符提醒阈值，默认 18")
    parser.add_argument("--strict", action="store_true", help="存在提醒时也返回退出码 1")
    args = parser.parse_args(argv)
    try:
        outputs = [path for path in (args.html, args.json) if path is not None]
        resolved = [resolve_path(path) for path in outputs]
        if resolve_path(args.input) in resolved:
            raise ValueError("报告路径不能与字幕源文件相同。")
        if len(set(resolved)) != len(resolved):
            raise ValueError("HTML 和 JSON 报告需要使用不同路径。")
        for path in outputs:
            if path.exists() and args.input.exists() and path.samefile(args.input):
                raise ValueError("报告路径指向字幕源文件，已停止写入。")
        if len(outputs) == 2 and all(path.exists() for path in outputs) and outputs[0].samefile(outputs[1]):
            raise ValueError("HTML 和 JSON 报告不能指向同一个文件。")
        text = args.input.read_text(encoding=args.encoding)
        result = analyze(text, filename=args.input.name, max_chars=args.max_chars,
                         min_duration_ms=args.min_duration_ms, max_cps=args.max_cps)
        content = []
        if args.html:
            content.append((args.html, render_html(result)))
        if args.json:
            content.append((args.json, json.dumps(result, ensure_ascii=False, indent=2) + "\n"))
        for path, body in content:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(body, encoding="utf-8")
    except (OSError, UnicodeError, LookupError, ValueError) as exc:
        print(f"无法完成检查：{exc}", file=sys.stderr)
        if isinstance(exc, UnicodeError):
            print("请确认文件编码；中文旧字幕可尝试 --encoding gb18030。", file=sys.stderr)
        return 2
    summary = result["summary"]
    print(f"SubCheck Lite · {result['filename']}")
    print(f"{summary['total_cues']} 块字幕 · {summary['errors']} 个错误 · {summary['warnings']} 个提醒")
    for issue in result["issues"]:
        label = "错误" if issue["severity"] == "error" else "提醒"
        print(f"[{label}] 第 {issue['line']} 行：{issue['message']}")
    if not result["issues"]:
        print("本次检查未发现问题。")
    for path in outputs:
        print(f"已保存报告：{path}")
    return int(summary["errors"] > 0 or (args.strict and summary["warnings"] > 0))


if __name__ == "__main__":
    sys.exit(main())

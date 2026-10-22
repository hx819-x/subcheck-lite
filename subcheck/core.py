"""Read-only SRT analysis with deterministic, JSON-serializable findings.

Each nonempty, blank-line-delimited block becomes a cue, even if malformed.
Line numbers refer to the original text after CRLF/CR newline normalization.
Visible character counts remove common SRT HTML tags and decode HTML entities.
They count Unicode code points, not grapheme clusters: a combining mark or an
emoji sequence may therefore count as several characters. Inner spaces count;
leading/trailing whitespace on each line and line breaks do not.
"""

import bisect
import html
import math
import re
from typing import Any, Dict, List, Optional, Tuple


_TIMESTAMP = re.compile(r"^(\d{2,}):(\d{2}):(\d{2}),(\d{3})$", re.ASCII)
_LABEL = re.compile(r"^[0-9]+$")
_FORMATTING = re.compile(r"</?(?:b|i|u|font)(?:\s+[^<>]*?)?\s*>", re.IGNORECASE)


def _validate_thresholds(max_chars: int, min_duration_ms: int, max_cps: float) -> None:
    for name, value in (("max_chars", max_chars), ("min_duration_ms", min_duration_ms)):
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise ValueError("{} 必须是正整数".format(name))
    try:
        valid_cps = (not isinstance(max_cps, bool)
                     and isinstance(max_cps, (int, float))
                     and math.isfinite(max_cps)
                     and max_cps > 0)
    except OverflowError:
        valid_cps = False
    if not valid_cps:
        raise ValueError("max_cps 必须是有限正数")


def _timestamp_ms(value: str) -> Optional[int]:
    match = _TIMESTAMP.fullmatch(value.strip())
    if not match:
        return None
    try:
        hours, minutes, seconds, milliseconds = (int(part) for part in match.groups())
    except ValueError:
        # Python can reject an excessively long integer string. Treat malformed
        # input as a finding rather than letting it stop the complete analysis.
        return None
    if minutes > 59 or seconds > 59:
        return None
    return ((hours * 60 + minutes) * 60 + seconds) * 1000 + milliseconds


def _visible_text(value: str) -> str:
    # Decode after tag removal, so escaped literal markup remains visible text.
    return html.unescape(_FORMATTING.sub("", value)).strip()


def _blocks(text: str) -> List[List[Tuple[int, str]]]:
    normalized = text.removeprefix("\ufeff").replace("\r\n", "\n").replace("\r", "\n")
    blocks: List[List[Tuple[int, str]]] = []
    block: List[Tuple[int, str]] = []
    for line_number, line in enumerate(normalized.split("\n"), 1):
        if not line.strip():
            if block:
                blocks.append(block)
                block = []
        else:
            block.append((line_number, line))
    if block:
        blocks.append(block)
    return blocks


def _issue(code: str, severity: str, cue: Optional[int], line: int, message: str) -> Dict[str, Any]:
    return {"code": code, "severity": severity, "cue": cue, "line": line, "message": message}


def _prior_overlaps(cues: List[Dict[str, Any]], timing_lines: List[int]) -> List[Dict[str, Any]]:
    """Find an earlier physical cue intersecting each cue in O(n log n).

    A Fenwick tree stores the largest prior end time for each prefix of start
    times. The selected conflict has the latest end (earliest cue breaks ties).
    Touching endpoints do not overlap. Invalid intervals are excluded.
    """
    valid = [cue for cue in cues if cue["start_ms"] is not None and cue["end_ms"] is not None
             and cue["end_ms"] > cue["start_ms"]]
    starts = sorted({cue["start_ms"] for cue in valid})
    tree: List[Tuple[int, int]] = [(-1, 0)] * (len(starts) + 1)
    issues: List[Dict[str, Any]] = []
    for cue in valid:
        # Tuples compare by end time and then negative cue index.
        position = bisect.bisect_left(starts, cue["end_ms"])
        best = (-1, 0)
        while position:
            best = max(best, tree[position])
            position -= position & -position
        if best[0] > cue["start_ms"]:
            prior_index = -best[1]
            prior = cues[prior_index - 1]
            overlap_ms = min(cue["end_ms"], prior["end_ms"]) - max(cue["start_ms"], prior["start_ms"])
            issues.append(_issue(
                "overlap", "error", cue["index"], timing_lines[cue["index"] - 1],
                "与第 {} 条字幕（原文件第 {} 行）重叠 {} 毫秒。".format(
                    prior_index, prior["line"], overlap_ms),
            ))
        position = bisect.bisect_left(starts, cue["start_ms"]) + 1
        value = (cue["end_ms"], -cue["index"])
        while position < len(tree):
            tree[position] = max(tree[position], value)
            position += position & -position
    return issues


def analyze(
    text: str,
    filename: str = "input.srt",
    max_chars: int = 24,
    min_duration_ms: int = 800,
    max_cps: float = 18.0,
) -> Dict[str, Any]:
    """Analyze SRT text without changing it.

    Thresholds must be positive; ``max_chars`` and ``min_duration_ms`` must be
    integers, and ``max_cps`` must be finite. Booleans are not thresholds.
    A threshold is exceeded only strictly: equality does not cause a warning.
    ``duration_ms`` in the summary is the span from the earliest valid start to
    the latest valid end, excluding nonpositive or invalid intervals.

    Timestamps use HH:MM:SS,mmm with at least two hour digits, two minute/second
    digits (00–59), and exactly three millisecond digits. Blank lines delimit
    cues. Numbering is checked against the 1-based physical block position.
    All issue messages are in Chinese; issue codes are stable identifiers.
    """
    _validate_thresholds(max_chars, min_duration_ms, max_cps)
    if not isinstance(text, str):
        raise TypeError("text 必须是字符串")
    if not isinstance(filename, str):
        raise TypeError("filename 必须是字符串")

    cues: List[Dict[str, Any]] = []
    issues: List[Dict[str, Any]] = []
    timing_lines: List[int] = []
    previous_start: Optional[int] = None
    previous_index: Optional[int] = None

    for index, block in enumerate(_blocks(text), 1):
        first_line, first = block[0]
        label = first.strip()
        has_label = bool(_LABEL.fullmatch(label))
        # A timing line in the first position means numbering is missing.
        first_is_timing = "-->" in first
        body_offset = 1 if has_label or not first_is_timing else 0
        if first_is_timing:
            label = ""
        if not has_label:
            issues.append(_issue(
                "invalid_index", "error", index, first_line,
                "字幕序号缺失或不是非负十进制整数；本块按第 {} 条字幕检查。".format(index),
            ))
        elif (label.lstrip("0") or "0") != str(index):
            issues.append(_issue(
                "unexpected_index", "warning", index, first_line,
                "字幕序号为 {}，按文件顺序应为 {}。".format(label, index),
            ))

        timing_line = block[body_offset][0] if body_offset < len(block) else first_line
        candidate = block[body_offset][1] if body_offset < len(block) else ""
        start_ms: Optional[int] = None
        end_ms: Optional[int] = None
        if "-->" in candidate:
            parts = candidate.split("-->")
            if len(parts) == 2:
                start_ms = _timestamp_ms(parts[0])
                end_ms = _timestamp_ms(parts[1])
            if start_ms is None or end_ms is None:
                issues.append(_issue(
                    "invalid_timestamp", "error", index, timing_line,
                    "时间轴无效：{}。应为 HH:MM:SS,mmm --> HH:MM:SS,mmm，分和秒须在 00–59 内。".format(candidate.strip()),
                ))
            text_lines = block[body_offset + 1:]
        else:
            issues.append(_issue(
                "missing_timestamp", "error", index, timing_line,
                "缺少可识别的时间轴（应包含 -->）；已保留本块以便人工检查。",
            ))
            # Keep every unrecognized line instead of treating it as timing
            # metadata and silently removing it from the analyzed cue text.
            text_lines = block[1:] if has_label else block

        cue_text = "\n".join(line for _, line in text_lines)
        cue = {"index": index, "label": label, "line": first_line,
               "start_ms": start_ms, "end_ms": end_ms, "text": cue_text}
        cues.append(cue)
        timing_lines.append(timing_line)

        visible_lines = [(line_number, _visible_text(line)) for line_number, line in text_lines]
        visible_count = sum(len(line) for _, line in visible_lines)
        if not visible_count:
            issues.append(_issue(
                "empty_cue", "error", index, text_lines[0][0] if text_lines else timing_line,
                "字幕没有可见文字（空白与 b/i/u/font 格式标签不计为文字）。",
            ))
        for line_number, visible in visible_lines:
            if len(visible) > max_chars:
                issues.append(_issue(
                    "long_line", "warning", index, line_number,
                    "本行有 {} 个可见字符，超过每行 {} 字的提醒阈值。".format(len(visible), max_chars),
                ))

        if start_ms is not None:
            if previous_start is not None and start_ms < previous_start:
                issues.append(_issue(
                    "out_of_order", "warning", index, timing_line,
                    "开始时间早于前一条可解析开始时间的字幕（第 {} 条）；请检查排列顺序。".format(previous_index),
                ))
            previous_start, previous_index = start_ms, index
        if start_ms is not None and end_ms is not None:
            duration_ms = end_ms - start_ms
            if duration_ms <= 0:
                issues.append(_issue(
                    "reversed_time", "error", index, timing_line,
                    "结束时间必须晚于开始时间；当前时长为 {} 毫秒。".format(duration_ms),
                ))
            else:
                if duration_ms < min_duration_ms:
                    issues.append(_issue(
                        "short_duration", "warning", index, timing_line,
                        "显示时长为 {} 毫秒，短于 {} 毫秒的提醒阈值。".format(duration_ms, min_duration_ms),
                    ))
                cps = visible_count * 1000 / duration_ms
                if cps > max_cps:
                    issues.append(_issue(
                        "high_cps", "warning", index, timing_line,
                        "阅读速度约 {:.1f} 字/秒，超过 {:.1f} 字/秒的提醒阈值。".format(cps, max_cps),
                    ))

    if not cues:
        issues.append(_issue("empty_input", "error", None, 1, "文件为空或只包含空白，没有找到字幕块。"))
    issues.extend(_prior_overlaps(cues, timing_lines))
    issues.sort(key=lambda item: (item["line"], item["cue"] or 0, item["code"]))
    valid = [cue for cue in cues if cue["start_ms"] is not None and cue["end_ms"] is not None
             and cue["end_ms"] > cue["start_ms"]]
    duration_ms = max(cue["end_ms"] for cue in valid) - min(cue["start_ms"] for cue in valid) if valid else 0
    return {
        "filename": filename,
        "cues": cues,
        "issues": issues,
        "summary": {
            "total_cues": len(cues),
            "errors": sum(issue["severity"] == "error" for issue in issues),
            "warnings": sum(issue["severity"] == "warning" for issue in issues),
            "duration_ms": duration_ms,
        },
    }

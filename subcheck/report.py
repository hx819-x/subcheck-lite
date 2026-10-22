"""Self-contained, escaped HTML reports; no scripts or external resources."""

from html import escape


def timestamp(milliseconds):
    if milliseconds is None:
        return "时间无效"
    seconds, ms = divmod(milliseconds, 1000)
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours:02}:{minutes:02}:{seconds:02},{ms:03}"


def render_html(result):
    """Render an analyze() result without interpreting subtitle HTML."""
    esc = lambda value: escape(str(value), quote=True)
    summary = result["summary"]
    rows = []
    for issue in result["issues"]:
        severity = "error" if issue["severity"] == "error" else "warning"
        label = "错误" if severity == "error" else "提醒"
        cue = f"第 {issue['cue']} 块" if issue["cue"] is not None else "文件"
        rows.append(
            f'<tr><td><span class="tag {severity}">{label}</span></td>'
            f'<td class="location">{esc(cue)}<small>源文件第 {esc(issue["line"])} 行</small></td>'
            f'<td>{esc(issue["message"])}<small>{esc(issue["code"])}</small></td></tr>'
        )
    findings = (
        '<div class="table-wrap"><table><thead><tr><th>级别</th><th>位置</th><th>检查结果</th></tr></thead>'
        f'<tbody>{"".join(rows)}</tbody></table></div>'
        if rows else '<p class="success">本次检查未发现问题。发布前，仍请结合视频核对文字和口型。</p>'
    )
    cues = "".join(
        '<div class="cue"><div class="cue-meta">'
        f'<strong>#{esc(cue["index"])}</strong> '
        f'{esc(timestamp(cue["start_ms"]))} → {esc(timestamp(cue["end_ms"]))}'
        f'<small>原编号 {esc(cue["label"] or "缺失")} · 第 {esc(cue["line"])} 行</small></div>'
        f'<pre>{esc(cue["text"]) or "（空字幕）"}</pre></div>'
        for cue in result["cues"]
    )
    status = "需要修正" if summary["errors"] else ("建议复核" if summary["warnings"] else "检查通过")
    style = """
    :root{color-scheme:light;--ink:#183331;--muted:#60716c;--line:#dce5df;--paper:#f5f7f2}
    *{box-sizing:border-box}body{margin:0;background:var(--paper);color:var(--ink);font:16px/1.65 -apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC",sans-serif}
    main{max-width:1060px;margin:0 auto;padding:48px 28px 60px}header{display:flex;justify-content:space-between;gap:24px;align-items:center;border-bottom:1px solid var(--line);padding-bottom:24px}
    .brand{font-size:14px;letter-spacing:2px;font-weight:700}.pill{border:1px solid #a7c1b4;color:#245944;border-radius:100px;padding:6px 14px;font-size:13px;white-space:nowrap}
    h1{font-size:42px;letter-spacing:-1.8px;line-height:1.2;margin:32px 0 12px}h2{font-size:21px;margin:0 0 16px}p{margin:0}.lead{color:var(--muted);overflow-wrap:anywhere}.status{display:inline-block;background:#e4ede3;padding:4px 10px;border-radius:5px;font-size:13px;margin-bottom:4px}
    .stats{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:14px;margin:28px 0 32px}.stat{padding:22px;background:white;border:1px solid var(--line);border-radius:12px}.stat span{display:block;color:var(--muted);font-size:13px}.stat strong{display:block;font-size:32px;font-weight:650;line-height:1.6}.stat .time{font-size:19px;line-height:2.7}.red{color:#a03635}.amber{color:#8b5a15}
    section{margin-top:30px}.panel{background:white;border:1px solid var(--line);border-radius:12px;padding:24px}.table-wrap{overflow-x:auto}table{border-collapse:collapse;width:100%;text-align:left}th{font-size:12px;letter-spacing:1px;color:var(--muted);font-weight:500}td,th{padding:14px 12px;border-bottom:1px solid var(--line);vertical-align:top}td:last-child{overflow-wrap:anywhere}tr:last-child td{border-bottom:0}.tag{display:inline-block;padding:3px 9px;font-size:12px;border-radius:5px;white-space:nowrap}.error{background:#fae7e4;color:#a03635}.warning{background:#fcf0d9;color:#8b5a15}.location{min-width:150px}small{display:block;color:var(--muted);font-size:12px;margin-top:4px}
    details summary{cursor:pointer;font-weight:600}.cue{display:grid;grid-template-columns:300px 1fr;gap:20px;padding:18px 0;border-bottom:1px solid var(--line)}.cue:last-child{border:0}.cue-meta{font-size:13px}.cue-meta strong{margin-right:12px}pre{margin:0;white-space:pre-wrap;overflow-wrap:anywhere;font:inherit}.success{color:#286546}footer{font-size:12px;color:var(--muted);margin-top:28px}.note{font-size:13px;color:var(--muted);margin-top:16px}
    @media(max-width:650px){main{padding:24px 16px}h1{font-size:34px}.stats{grid-template-columns:1fr 1fr}.stat{padding:16px}.panel{padding:16px}.cue{grid-template-columns:1fr;gap:8px}header{align-items:flex-start}.pill{font-size:11px}td,th{padding:10px 8px}}
    @media print{body{background:white}main{padding:0;max-width:none}.panel,.stat{break-inside:avoid}details{display:none}header{padding-bottom:10px}}
    """
    return f'''<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'">
<title>字幕体检 · {esc(result['filename'])}</title><style>{style}</style></head>
<body><main><header><div class="brand">SUBCHECK LITE / 字幕体检</div><div class="pill">离线检查 · 本地报告</div></header>
<h1>让每一句，都有时间被看见。</h1><p class="lead">{esc(result['filename'])}</p>
<div class="stats"><div class="stat"><span>字幕块</span><strong>{summary['total_cues']}</strong></div>
<div class="stat"><span>需要修正的错误</span><strong class="red">{summary['errors']}</strong></div>
<div class="stat"><span>建议复核的提醒</span><strong class="amber">{summary['warnings']}</strong></div>
<div class="stat"><span>字幕时间跨度</span><strong class="time">{timestamp(summary['duration_ms'])}</strong></div></div>
<section class="panel"><div class="status">{status}</div><h2>检查结果</h2>{findings}
<p class="note">提醒采用可调整的阅读阈值。重叠有时是有意设计，请结合画面判断；本工具不判断文字内容是否正确。</p></section>
<section class="panel"><details><summary>查看原始字幕 · {summary['total_cues']} 块</summary>{cues}</details></section>
<footer>SubCheck Lite · 不上传字幕，不修改源文件。此报告包含字幕内容，分享前请自行检查。</footer>
</main></body></html>'''

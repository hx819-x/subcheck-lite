#!/bin/bash
# macOS: double-click, choose a local subtitle, then view its report.
cd "$(dirname "$0")" || exit 2
if ! command -v python3 >/dev/null 2>&1; then
  echo "需要安装 Python 3.9 或更新版本：https://www.python.org/downloads/"
  read -r -p "按回车键退出。"
  exit 2
fi
subtitle=$(/usr/bin/osascript -e 'POSIX path of (choose file with prompt "选择一个 UTF-8 编码的 SRT 字幕文件")') || exit 0
report="reports/report-$(date +%Y%m%d-%H%M%S)-$$.html"
python3 -m subcheck "$subtitle" --html "$report"
status=$?
if [ "$status" -lt 2 ]; then
  /usr/bin/open "$report"
else
  echo "未生成报告。请查看上方提示。"
fi
read -r -p "按回车键关闭此窗口。"
exit "$status"

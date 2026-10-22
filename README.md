# SubCheck Lite · 字幕体检

A small, dependency-free Python tool for checking local SRT subtitle files and generating readable HTML or JSON reports.

提交视频前，先检查字幕有没有时间格式错误、重叠、空白内容或阅读时间不足。字幕体检在本机读取 `.srt` 文件，无需账号、网络服务或第三方 Python 包。

先看效果：下载项目后，用浏览器打开 [demo/report.html](demo/report.html)。这是针对 `examples/problems.srt` 生成的示例报告，不包含真实用户字幕。

## 快速开始

需要 Python 3.9 或更新版本。在项目目录中运行：

```sh
python3 -m subcheck examples/clean.srt
python3 -m subcheck examples/problems.srt
```

第二个示例特意包含问题，会返回非零退出码。生成可以在浏览器中查看的报告：

```sh
python3 -m subcheck examples/problems.srt \
  --html reports/report.html \
  --json reports/report.json
```

macOS 用户也可以双击 `启动字幕体检.command`，选择本机 SRT 文件并打开 HTML 报告；同样需要已安装 Python 3.9 或更新版本。如果双击提示没有执行权限，可在项目目录运行：

```sh
chmod +x 启动字幕体检.command
```

## 检查什么

- 时间戳格式与开始、结束时间关系
- 空白字幕、字幕序号和时间顺序
- 字幕时间重叠，包括被较长字幕覆盖的后续字幕
- 显示时间过短、单行过长、阅读速度过快

阅读提示使用可调整的经验阈值，**不是统一的字幕制作标准**。默认单行最多 24 字符、最短显示时间 800 毫秒、最高阅读速度 18 字符/秒；应根据语言、受众和发布平台调整。

字符数按 Unicode 码位统计：先去除常见的 `b`、`i`、`u`、`font` 格式标签，并解码 HTML 字符实体。行内空格计入，行首、行尾空白与换行不计入；组合字符或部分表情可能占多个码位，因此不一定等同于肉眼看到的字数。

```sh
python3 -m subcheck my-video.srt \
  --max-chars 24 --min-duration-ms 800 --max-cps 18
```

默认按 UTF-8 读取；其他编码可以显式指定：

```sh
python3 -m subcheck my-video.srt --encoding gb18030
```

查看全部参数：

```sh
python3 -m subcheck --help
```

## 结果与退出码

命令行会显示问题在源文件中的行号及说明；HTML 适合人工查看，JSON 适合接入其他工具。

| 退出码 | 含义 |
| --- | --- |
| `0` | 没有错误；普通模式允许警告 |
| `1` | 存在错误，或在 `--strict` 模式下存在警告 |
| `2` | 文件读写失败或命令行参数有误 |

如需将警告也视为失败：

```sh
python3 -m subcheck my-video.srt --strict
```

工具不会自动修改原字幕。它不做语音转写、AI 内容分析、语义正确性判断，也不能判断字幕是否与视频画面或声音同步。无报错仍需要观看视频并人工复核。

## 开发与贡献

运行测试：

```sh
python3 -m unittest discover -s tests -v
```

GitHub Actions 配置使用 Python 3.9 和 3.13 运行同一测试集。贡献前请阅读 [CONTRIBUTING.md](CONTRIBUTING.md)。错误报告请提供最小复现字幕，删除真实姓名及其他私人内容。

首个版本由 Codex 辅助编写。维护者应审阅代码、运行测试，并使用实际字幕验证后再发布或集成。

后续计划：支持 WebVTT、增加图形界面。以上为计划功能，当前版本未实现。

## 许可证

[MIT](LICENSE)

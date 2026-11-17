# MIT OCW 中文课程目录

MIT OpenCourseWare 的中文辅助检索目录，收录 **2026-11-17 快照中的 2,587 个课程版本、2,220 个主课程代码**。支持中文关键词搜索、双学科交叉筛选，以及按视频、讲义、外部学习入口等资源类型筛选。

每个条目包含课程代码、英文标题、中文辅助译名、学科类别、开放学习资源类型、官方英文完整简介，并保留课程链接、教师、院系、学期和抓取时间。相同代码的不同学期分别保留，RES 开头的开放资源条目也包括在内。

## 开始使用

**[下载便携包](MIT_OCW课程目录_便携包_20261117.zip?raw=true)**（约 5.64 MiB），解压后双击 `打开课程目录.html`。无需安装 Python，也无需启动服务器；搜索可离线使用，进入 MIT 学习页面需要联网。

1. 输入中文、英文或课程代码。空格分隔的多个关键词需同时匹配。
2. 可同时选择两个学科，例如“音乐”和“计算机科学”。
3. “所有有授课视频证据”包括站外入口，共 307 个条目；也可单独筛选外部 MOOC 或在线课程入口。
4. 点击课程标题查看完整简介和学习链接，或导出当前筛选结果为 CSV。

GitHub 文件预览不执行 HTML。请下载文件后在浏览器中打开。

## 数据文件

| 文件 | 内容 |
| --- | --- |
| [独立 HTML](打开课程目录.html?raw=true) | 内嵌全部数据的离线检索页，可单独复制到其他电脑 |
| [Excel](outputs/ocw_20261117/MIT_OCW课程总目录.xlsx?raw=true) | 课程目录、完整课程简介及使用说明 |
| [CSV](课程总目录.csv?raw=true) | UTF-8 BOM，32 列，保留完整简介 |
| [JSON](课程完整数据.json?raw=true) | 结构化数据、原始学科层级、资源导航与来源 |
| [使用说明](使用说明.txt) | 范围、分类规则、验证限制与刷新说明 |

Excel 主目录显示简介摘录，全文在“课程简介”工作表，长文按编号分段。请以课程链接对应版本。Excel 直接打开 CSV 可能把课程代码转成数字；XLSX 已保留 `1.00`、`1.010` 等代码的文本形式。

## 覆盖与资源分类

公开搜索接口与课程站点地图各列出 2,587 个课程版本，URL 差集为零。逐门读取首页与官方 `data.json`，均成功；六项所需信息无缺失。另检查 404 个资源入口页面，均返回 HTTP 200。

| 主要学习内容类型 | 条目数 |
| --- | ---: |
| 授课视频 | 281 |
| 其他教学视频 | 107 |
| 授课音频 | 15 |
| 讲义或开放教材 | 1,160 |
| 作业、阅读或其他学习资料 | 928 |
| 外部课程或资源入口 | 94 |
| 已退役，转至档案库 | 2 |

上述主分类互斥，具体资源标志可重叠。307 个条目有授课视频证据，其中 26 个归入外部入口。旧版 6.00 和 6.00SC 的对应页面明确说明已退役，并提供 MIT DSpace 档案入口。

中文标题、学科与院系译名为 AI 辅助译名，非 MIT 官方译本，尚未经逐项专业审校。课程介绍保留官方英文全文。资源分类依据官方标签、导航、正文及重点资源页核查；有视频证据不表示讲次完整或每个视频均能播放。外部课程的收费、报名和播放状态未逐项核验。

这是课程级目录及资源入口汇编，未批量下载课程视频、PDF、字幕与作业附件。

## 脚本与重建

阅读成品文件不需要开发环境。Python 脚本要求 Python 3.10+、`requests` 和 `lxml`。先检查已有 Conda 环境；本次抓取使用已有 CorpusCrawler 环境，未修改依赖。仓库未捆绑 Python 环境或 `node_modules`。

| 脚本 | 用途 |
| --- | --- |
| `crawl_ocw.py` | 交叉发现课程、限速抓取、失败重试、断点缓存和日志 |
| `build_catalogue.py` | 从快照数据生成 HTML、CSV、JSON 和工作簿中间数据 |
| `verify_entries.py` | 检查主要视频入口和标签稀疏的资源页，保存 HTTP 检查结果 |
| `build_workbook.mjs` | 用 `@oai/artifact-tool` 生成 XLSX；本次使用 Codex 捆绑运行库 |

本次快照的重建输入包括 `course_records.json`、`sources/search_courses.json`、`coverage.json`、逐批标题译名、学科词表以及 `reviewed_resources.json`。在仓库副本中、使用具备上述依赖的环境，可执行：

```powershell
python .\build_catalogue.py
```

这会重写副本中的生成文件，不重新联网抓取。XLSX 构建器还需要相应的 Node.js 与 `@oai/artifact-tool` 运行库；仓库中的 XLSX 成品可直接使用，不依赖该运行库。

重新抓取未来快照时应指定**新的输出目录**，例如：

```powershell
python .\crawl_ocw.py --output .\snapshots\2026-12-01
```

日期仅为示例，请按实际抓取日期选择新目录。抓取后仍需更新译名与分类再发布；构建器默认读取自身所在目录。`reviewed_resources.json` 是本次快照的核查结果，未来快照应重新核对，不能无条件沿用。

## 验证记录

- [validation.json](validation.json)：目录覆盖、字段完整性与资源分类统计。
- [file_consistency_checks.json](file_consistency_checks.json)：XLSX 课程代码完整保留，完整简介与 CSV、JSON 逐条一致。
- [browser_checks.json](browser_checks.json)：离线打开、搜索、双学科筛选、分页、简介弹窗与筛选结果 CSV 导出检查。
- [resource_entry_checks.json](resource_entry_checks.json)：404 个资源入口页面的检查结果。
- [manifest.json](manifest.json)：便携包各成品文件的 SHA-256。该清单对应原始发布快照，不会随重建自动更新。

完整原始 HTML 缓存保留在本地工作目录，未上传到本仓库。本次验证未包含另一台计算机上的原生 Excel 应用测试。

## 来源与许可

课程数据和英文简介来自 [MIT OpenCourseWare](https://ocw.mit.edu/)，发现依据为[搜索目录](https://ocw.mit.edu/search/)与[站点地图](https://ocw.mit.edu/sitemap.xml)。各课程的原始页面和元数据链接随记录保留。

课程页面元数据标示 [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/)。本目录增加中文辅助译名、资源分类和检索界面；课程内容、改编内容与第三方素材的归属和适用条件见 [来源与许可说明](ATTRIBUTION.md)。本项目不代表 MIT 官方发布或认可。

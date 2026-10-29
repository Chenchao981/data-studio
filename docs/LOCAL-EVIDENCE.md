# 本地验证证据

当前稳定位置为 `F:\DataStudio\local-evidence\2026-10-29`，整个 `local-evidence/` 已加入 Git 排除。文档及归档脚本进入 Git，原始回执、日志、截图、私人工作区和结果留在本机。不要清理此目录时将它等同于 build 缓存。

## 历史证据的校验副本

`baseline-and-p0-2/archive-manifest.json` 记录 47 个文件的来源、归档相对路径、字节数和 SHA-256，未发现缺失来源。归档时同时核对源文件复制前后与目标哈希；保留原件，不改写回执内部的路径。

| 归档相对位置 | 内容及原始范围 |
| --- | --- |
| `baseline/huahong/` | Temp 中独立项目 39 ZIP、96,650 条华虹 PAT 任务日志、请求、业务回执、溯源清单和指纹 |
| `baseline/jiemin/` | Temp 中上海捷敏 data3 的 39 文件 DC 任务日志、请求、回执、摘要及指纹；原回执记录数为 null |
| `baseline/desktop-ui/` | 2026-10-29 桌面检查回执和原截图 |
| `baseline/installer/` | 0.3.3 原安装生命周期回执及 UI 截图 |
| `baseline/installer-uat-0.3.3.log`、`baseline/publish-0.3.3.log` | 本地安装/发布日志 |
| `baseline/huahong-independent/` | 从迁移前项目复制的最终/发布 PAT 独立对账回执，仅作业务证据追溯 |
| `p0-2/` | P0-2 四组真实任务汇总、逐值对账、目标包篡改拒绝日志及进程启动证据 |

这些副本保存验证事实，不是可以直接打开的应用历史。内部绝对路径仍指向当时的 Temp/build 目录，将来可能失效；稳定副本本身可独立检查。未复制原始输入、Excel/CSV 报告、结果 ZIP、历史数据库、运行时或安装包；需要重开结果时仍需完整私有工作区，不能用几份 JSON 冒充它。

## 本轮新验证

`pat-unified/` 为0.3.7的CP/FT PAT统一算法证据，含82项通过回归、四家CP/上海捷敏FT真实PAT、分发kit重跑、935个报告单元格及源数据核对、9个PAT名称和实际EXE入口、15,530文件校验。早期失败与私人结果保留在同目录，不入Git；范围与已发现的国宇旧清洗问题见 [0.3.7记录](RELEASE-0.3.7.md)。

`cp-lazy-charts/` 为0.3.6的CP按需绘图证据，包含最终Python回归、开发/打包kit实际浏览器图形与Cpk导出、冻结EXE的真实CP/FT任务、全部参数的数值/箱体/规格核对以及15,527文件校验。完整范围见 [0.3.6记录](RELEASE-0.3.6.md)；早期失败目录保留，不作为最终通过凭证。该目录包含私人工作区和输出，不能提交Git。

`p0-3/` 保存本轮 UI 入口实际复测日志、截图、回执及脚本参数；`entrypoint-static.json` 是 Python 帮助入口与 JavaScript 语法检查，`entrypoint-runs.json` 是串行执行记录。失败的尝试保留，修复后的复测使用新的目录和独立汇总，不覆盖原始记录。结果与范围见 [P0-3 审核记录](VALIDATION-MIGRATION-20261029.md)。

归档工具只收集显式允许的回执和截图，输出目录必须位于 `local-evidence/` 且不存在。来源缺失会写入 `missingSources` 并返回非零，不能声称完整归档。默认列表针对本次已有基线，不会扫描用户账号、全盘历史或业务报告。

```powershell
# 在 F:\DataStudio 下；每次使用一个新的归档目录
.\.venv-cpython\Scripts\python.exe packaging/archive_validation_evidence.py --output local-evidence/<新的归档目录>
```

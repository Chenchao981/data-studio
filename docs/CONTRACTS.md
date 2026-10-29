# UI 与 Python 接口合同 · M1

> 历史设计记录：保留原日期和当时行为。当前 0.3.3 已移除生产界面的演示入口及 Excel/CSV 预览；启动列表为空。当前操作以 [README](../README.md)、[交接](HANDOFF-2026-10-29.md) 和 [测试入口](TEST-ENTRYPOINTS.md) 为准，以下不是当前功能承诺。

## M1 已实现增量（以下优先于历史 M0 约定）

2026-10-29 当前0.3.5路径录入补充：可信工作台可显式调用 `applyInputPaths({text})` / `applyOutputPath({text})` 提交用户编辑路径。输入规范化并验证全部路径后才登记（最多100行，空输入只清空当前列表），输出保存单个已有本机目录；失败不覆盖原状态。`createTask` 继续只接受已登记ID，不直接读取任意前端路径。以下“只接受由Qt登记”是原M1边界，当前包括上述可信手动录入流程。详见 [0.3.5](RELEASE-0.3.5.md)。

- `bootstrap` 增加 `engines`：就绪状态、版本与工厂操作清单；`createTask(sourceId, sourceIds, toolCode)` 对真实输入必须显式选择已启用规则。只接受已由 Qt 登记的输入 ID，不接受前端传入任意路径。源目录与工作区不能互相包含。
- 真实任务在独立官方 CPython 环境运行固定 CP/FT 包，Qt6 主进程不导入旧 Qt5。单任务串行，Windows Job 在放行工作进程前建立，取消/退出时回收自身进程树。
- `createFollowup(id)` 验证成功父结果并创建 PAT 派生任务；终态任务不能原位重启，重试新建记录。
- `getPreview(taskId,dataset,start,end,search)` 验证该任务的索引哈希，每次最多200行。保留全部原表行、公式文本、字符串片号及数值；按原始行序显示，不对未知表头做统计。暂不支持真实工作表的排序/列过滤；完整表搜索用参数化 SQLite 查询。
- `openArtifact(id,index)` 仅打开成功任务内且哈希一致的已登记结果；导出校验和复制异步执行，禁止覆盖受管工作区及已登记原始输入。
- 回执含工具定义、Python版本、输入指纹、原输出统计及业务身份、父任务关联；本地任务含清单哈希和原包版本。程序不将取消后的部分结果发布为成功。
- 真实算法不报告可靠进度百分比时显示执行阶段；演示任务才显示模拟进度。实际运行不自动上传、不做账号认证。
- 默认沿用 M0 工作区目录，记录以 `demo` 和 `toolCode` 区分。真实工作表和演示查询相互隔离。

## 历史 M0 合同（保留用于演示模式）

通信：仅 `studio://app/index.html` 的QWebChannel可调用。所有异步请求携带唯一ID；`response(id, JSON)` 返回 `{ok,value,error}`。`changed()` 推送任务状态变更；`notification(message)` 提供原生拖放反馈。并行查询最多32个，Core执行队列1个线程，模拟任务1个独立进程。后续Web服务实现相同前端 `DataService`。

| 方法 | 输入 | 返回 / 约束 |
|---|---|---|
| bootstrap | 无 | 文件、最近100任务、设置、版本 |
| selectFiles / selectFolder | 无 | 原生对话框授权并登记的输入对象 |
| identifyFiles | 无 | M0登记列表；真实文件UNKNOWN，非自动识别承诺 |
| createTask | sourceId | READY任务，固定demo.v1与输入摘要 |
| startTask | id | 仅READY可进入QUEUED；不重复启动 |
| cancelTask | id | 仅READY/QUEUED/RUNNING可取消 |
| getTaskStatus | id | 任务状态、进度、错误、时间 |
| getPreview | dataset/start/end/search/sort/filters | 仅内置demo_raw/demo_clean；最多200行；排序列和运算符白名单；参数化SQL |
| getChartData | parameter/lot | 仅bv/leakage、4个演示批次；全量统计、24桶、至多2000散点 |
| listHistory | search | 最近100条匹配，SQLite持久化 |
| openOutputFolder / exportResult | id | 仅SUCCESS且哈希一致；导出目标由原生保存对话框选择 |
| exportChart | PNG data URL | 最多8MB、PNG签名校验；原生保存 |
| copyText | text | 受限文本复制至系统剪贴板 |
| saveSettings | theme | light/dark；M0其他设置固定 |
| clearCache | 无 | 只重建派生演示表，不删除历史或来源 |
| openLogs | 无 | 打开固定工作区日志目录 |

## 状态与进度

模拟任务：READY → QUEUED → RUNNING → SUCCESS / FAILED / CANCELLED。未执行和排队可取消；终态不重新启动，重试创建新任务。成功写临时输出、改名后才返回完整回执；摘要含SHA256。失败不暴露部分输出为成功。正常退出停止任务，异常退出后的未完成任务在下次启动标记CANCELLED并说明中断。Windows Job限制只管理本客户端创建的模拟工作进程。

本轮进度是真实模拟步骤进度，**不代表原CP/FT算法进度**。输入文件名不会作为Lot/Wafer或产品身份；已导入真实文件的业务身份仍为“尚未解析”。

## M1适配器约定

建议适配器实现 `identify(manifest) -> candidates`、`validate(selection, config) -> validated_request`、`run(validated_request, output_dir, cancel_token, progress_sink) -> result_manifest`。候选来源包含格式证据、置信程度和无法识别原因；不确定时必须手动选择，不自动拼接业务身份。

结果manifest需包含：测试阶段、原工厂/产品/Lot/Wafer（保留前导零）、参数名/编号/单位/规格、清洗/规则版本、原始内容哈希、输出哈希、行数含义、执行环境和耗时。各源引擎以独立进程固定依赖；接口层不重算Bin/PAT/spec。CP/FT/VDMOS的每一条映射均以真实输入与原输出对账放行。

## M3同步边界

当前没有WebDataService的联网实现。未来账号ID与本机未归属记录分开；显式归属后创建不可变同步包，采用任务ID+结果哈希做幂等键；本地删除与服务端删除独立；同步失败保留待重试状态。原始文件上传须有明确选择，不能随登录自动发送。

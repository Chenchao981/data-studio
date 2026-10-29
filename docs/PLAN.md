# Desktop Data Studio 实施规划

2026-10-23 · 以本次用户提供任务书为准。独立原型，现有 `desktop_client` 及 CP/FT 生产工程保持可用。

运行环境决定：根据本轮追加指示，使用官方 CPython 3.13.17 + 项目专用 `.venv-cpython`；依赖由pip安装并锁定，不使用Anaconda作为新工作台的开发/打包基底。原Anaconda不卸载、不升级。此前Anaconda原型环境仅留作诊断，不参与正式M0构建。

## 当前进度：M1 本地真实分析

2026-10-23 追加实施：M0 通信和界面原型已推进为真实 CP/FT 工作台。固定原工具通过独立 CPython 子进程接入，工厂/操作选择、批量队列、取消/重试、本地历史、完整结果导出和原工作表分页预览已实现。部分 M2 能力提前接入：原生 PAT/SYL/SBL/图表操作，以及杰群、日月新、电基清洗结果派生 PAT。具体验证以 `VALIDATION-M1.md` 为准。

实际格式由用户选择规则后交给原引擎校验；不提供没有证据的自动厂商识别。界面默认真实数据，内置演示保留独立入口。账号同步、服务器发布和下载安装不在本轮执行。

剩余 M2：统一参数/批次/规格语义的交互图表、容量管理、完整来源快照重放和 VDMOS 专门验收。结果表格当前采用 SQLite 完整工作表索引，先保留原语义，不因索引方便而重新定义测量行。

## 已完成基础：M0

先搭建 React 静态交互，再接入 PySide6 / Qt WebEngine / QWebChannel。六个页面统一三栏结构：左侧导航、中央工作区、可折叠右侧详情；亮暗主题、键盘导航、全局历史搜索、加载/错误/空状态。

文件工作台可选择和拖入本地文件/目录；M0只登记元数据并运行明确标注的模拟任务，不声称解析实际CP/FT数据。数据预览使用Python生成的100,000行可复现演示数据，通过SQLite执行分页、筛选、排序，每次最多200行；React端AG Grid Community保留有限数据块。ECharts直方图聚合由Python计算，散点最多2,000个显示样本，标明抽样与总体。

SQLite持久化模拟任务、路径/大小/修改时间摘要、演示规则版本、状态与错误；原始文件不复制到数据库。模拟处理在独立进程运行，可取消、失败与重试，退出时回收子进程。该能力只验收通信和生命周期，不作为真实清洗的一致性证据。

PyInstaller先交付onedir便携目录及ZIP，包含Qt WebEngine进程、资源、Python运行时、React静态构建；无需Node服务、外部浏览器或Python安装。干净Windows 11验收需单独环境：当前本机运行通过不等于干净系统通过。

## 分层与合同

| 层 | 职责 | 禁止事项 |
|---|---|---|
| Desktop Shell | 窗口、原生选择、拖放、可信资源、QWebChannel | 不嵌入PYMS整站，不给外部页面本地桥 |
| React UI | 交互、状态、表格、图表 | 不实现CP/FT业务统计，不接收整份大数据 |
| DataService | 类型化请求/响应，Desktop与Mock实现，Web预留 | 不让页面依赖Python路径或Qt对象 |
| Python Core | 数据登记、演示查询、计算、历史 | 不根据文件名猜业务身份，不覆盖原始文件 |
| Task Manager | 限流、独立进程、取消、恢复 | 未完成输出不标成功 |

桥接采用请求ID+异步信号。仅固定 `studio://app/` 加载打包资源；禁止远程请求、外部导航和弹窗。文件能力只使用原生选择或Qt拖放登记后的ID；JavaScript不能任意传入路径读取文件。查询列/排序/条件白名单，分页上限、导出大小和任务并发受控。

## 后续里程碑

- **M1 文件工作台**：CP/FT/VDMOS适配器合同、真实格式证据识别（不确定则手动选择）、真实输入指纹、既有固定引擎复用、100文件导入、批量任务/取消/输出一致性。先接华虹TD、立昂微、杰群与上海捷敏代表样本；原Lot/Wafer、单位、Bin/spec口径保留。VDMOS未核实接口前不承诺可用。
- **M2 分析与历史**：真实结果分块索引与DuckDB评估、参数/批次/规格元数据、CP图表、原FT PAT/SYL/SBL算法适配、不可变结果与关联重跑、缓存失效和容量管理。任务书SBY命名需与原工具SYL实义核对后统一。
- **M3 PYMS预留**：WebDataService、登录与固定账号隔离、持久同步队列、幂等上传、结果/历史协议及冲突策略。当前不实现联网和账号同步。

## 验收顺序

1. TypeScript构建与Python边界测试。
2. 原生窗口加载、本地文件选择、双向通信；测试100文件登记、10万行分页、全量筛选排序、模拟成功/失败/取消/重启。
3. Qt内真实React点击测试，亮/暗及125%/150%缩放截图检查；离线资源与网络阻断测试。
4. PyInstaller产物启动、同路径中文支持、Qt资源与子进程退出核验；记录包体、哈希、依赖锁定和未验证项。

官方实现依据：[Qt WebChannel](https://doc.qt.io/qtforpython-6/PySide6/QtWebChannel/QWebChannel.html)、[AG Grid Community Infinite Row Model](https://www.ag-grid.com/react-data-grid/infinite-scrolling/)、[shadcn/ui Vite](https://ui.shadcn.com/docs/installation/vite)、[Qt WebEngine部署](https://doc.qt.io/QT-6/qtwebengine-deploying.html)。

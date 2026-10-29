# 独立项目测试入口

更新：2026-10-29，当前界面版本 0.3.7，固定引擎 `studio-engine-20261029.3`。所有命令从 `F:\DataStudio` 执行，Python 使用 `.\.venv-cpython\Scripts\python.exe`。先按 README 准备固定环境、完整 `engines/` 和 `apps/web/dist/`。测试所用路径必须是新的独立目录，禁止使用正常个人历史做验证。

迁移前 PLAN、CONTRACTS 与早期 VALIDATION 文档保留当时的日期、版本、统计和预览行为；它们不是当前操作手册。当前生产界面启动输入为空，只使用真实输入，结果为文件夹概要，Excel/CSV 由外部查看。本地图表仍可独立显示数据与图形，不等于恢复 APP 的 Excel 预览。

## Python / Qt 入口

下表用 `python` 缩写固定解释器；可运行完整命令例见后文。所有这些脚本的 `--help` 已检查。

| 脚本（tests/ 下） | 参数 / 场景 | 边界 |
| --- | --- | --- |
| `verify_desktop.py` | `--output <新目录>` | 开发态 Qt、原生文件对话框、100 项拖放、空结果页、主题、资源限制；成功/失败/取消使用内部模拟计算，仅作生命周期测试 |
| `verify_real_ui.py` | `--source <文件或目录> --tool <明确工具码> --output <新目录>` | 真实规则选择、导入、计算、文件夹结果、ZIP 哈希与主题；默认工具为华虹 TD，DCP ZIP 必须显式指定 `LOCAL_CP_HUAHONG_CLEAN_V1` |
| `verify_workflow_ui.py` | `--layout-only --output <新目录>` | 显式导入 100 个布局夹具、每页50项、跨页选择、阶段切换和小窗口；不表示支持新工厂或性能达标 |
| `verify_workflow_ui.py` | `--cp <CP输入> --cp-tool <CP工具码> --ft <上海捷敏DC文件> --output <新目录>` | 真实 CP/FT、Qt 拖放、任务选择、历史筛选、ZIP 校验；CP 默认仍为 TD，可明确切换 DCP |
| `verify_paths_ui.py` | `--source <华虹DCP ZIP> --output <新目录>` | 原生混合选择、默认桌面、重启输入为空、目录记忆、真实三 CSV 输出及哈希 |
| `verify_ft_ui.py` | `--source <上海捷敏DVDS文件> --output <新目录>` | DC/DVDS/RG/PAT 菜单、真实 DVDS、实时日志、CP/FT 草稿隔离及重启历史；不是通用 FT 样本入口 |
| `verify_cp_restore_ui.py` | `--home <仅有一项成功CP清洗的私有home> --output <新目录>` | 三 CSV 导出哈希、打开文件夹、CP Cockpit HTTP 就绪、会话复用与退出清理；绘图另测，不硬编码 3,875 条 |
| `verify_factory_ui.py` | `--output <新目录>` | 每阶段20家虚拟工厂布局、键盘、筛选、主题和搜索时延；无业务任务，不改磁盘引擎目录 |
| `verify_operation_ui.py` | `--output <新目录>` | 当前10家工厂全部可选功能、42px按钮、选中不跳动、紧凑横排、明暗主题及1440/920窗口；检查重复说明已移除，操作要求保留在按钮悬停提示 |
| `verify_editable_paths_ui.py` | `--cp <华虹DCP ZIP> --ft <上海捷敏DC文件> --output <新目录>` | Qt真实Ctrl+V及Enter、无效路径回退、多行/引号、真实CP/FT任务与重启默认输出；测试结束恢复保存的剪贴板 |
| `verify_resize.py` | `--software --output <新目录>`；可加 `--recovery` 或 `--home <成功任务home>` | 原生 resize、最大化/还原、可用屏幕、黑屏采样、渲染故障恢复；`--charts` 原依赖演示图表，现明确拒绝并指向真实 Cockpit 脚本 |
| `verify_installer.py` | `<Setup.exe> --home <成功华虹PAT私有home>` | 实际安装/覆盖/卸载，会操作测试安装注册项与快捷方式；只在无正式安装的受控机器执行；本轮只审核和保留旧证据 |

## 冻结客户端 / 图表入口

使用项目已有 Node.js。脚本只通过本机临时 CDP 端口连接自己启动的测试客户端；保留用户正常窗口。

| 脚本（apps/web/tests/ 下） | 参数 | 样本要求与边界 |
| --- | --- | --- |
| `verify-huahong-pat-ui.mjs` | `<exe> <私有home> <新证据目录>` | 必须有且仅有一项成功的华虹原始 PAT；按操作定位，不再限定历史名称为 `CP data 20261019`；检查 FT 口径、产品汇总、结果及无预览 |
| `verify-editable-paths.mjs` | `<exe> <全新私有home> <新证据目录> <CP ZIP> <上海捷敏DC文件>` | 冻结客户端真实文本输入事件、错误路径、修改未应用时禁用开始，以及真实CP/FT使用编辑后的输入和输出目录 |
| `verify-bundle-ui.mjs` | `<exe> <私有home> <新证据目录>` | 需要一项成功上海捷敏 DVDS，脚本会重新执行该真实任务；操作菜单、搜索、日志、结果任务选择、主题及小窗口。不要给任意 CP/FT 历史，DVDS 以外的任务不符合输入要求 |
| `measure-ui-performance.mjs` | `<exe> <新证据目录> [--strict]` | 可见窗口连续3轮，记录启动/切换/工厂搜索；超预算结果为 REVIEW，`--strict` 返回非零。并非全部硬件或冷启动性能承诺 |
| `verify-cp-charts.mjs` | `<正在运行的本机Cockpit URL> <新证据目录>` | 0.3.6按需图表：真实CP清洗且至少2个参数，依赖本机Edge。验证默认单参数组合图、11种其他图形的草稿/重绘/移除、各页签实际渲染及Cpk导出；仅覆盖所用样本 |
| `tests/verify_cp_lazy_charts.py`（仓库根目录） | `--home <CP私有home> --output <新证据目录> [--kit <独立engines目录>]` | 恰有1项成功真实CP清洗；创建并持有图表服务，调用上一项浏览器验证，记录实际runtime/CP包哈希、原结果不变、服务复用与退出回收。`--kit`仅存在于验证入口 |
| `tests/verify_cp_chart_data.py`（仓库根目录） | `--home <本轮CP/FT私有home> --reference <同样本上一版home> --browser <浏览器证据目录> --output <JSON路径>` | 本轮华虹矩阵spec与捷敏DC合同；逐参数比较全部有限散点、原箱体/规格、下载Cpk、前后CP数据与FT单元格；不接受任意工厂样本并宣称通用验收 |
| `tests/verify_pat_consistency.py`（仓库根目录） | `--home <三家CP私有home> --frozen-home <同样本分发kit home> --reference-home <华虹CP/捷敏FT home> --output <新JSON>` | 0.3.7真实佳泰/立昂微/国宇标准数据与报告逐项对FT函数、独立6Sigma和分发kit；华虹原始ZIP逐值与规格重算、国宇原始值/LotName/Min-Max标签、源哈希。限定本次样本 |

```powershell
.\.venv-cpython\Scripts\python.exe -m pytest -q -rs tests engine_support/desktop_client/tests
.\.venv-cpython\Scripts\python.exe tests/verify_workflow_ui.py --layout-only --output local-evidence/<新目录>/layout
.\.venv-cpython\Scripts\python.exe tests/verify_real_ui.py --source <华虹DCP.zip> --tool LOCAL_CP_HUAHONG_CLEAN_V1 --output local-evidence/<新目录>/cp
node apps/web/tests/verify-huahong-pat-ui.mjs dist/DesktopDataStudio/DesktopDataStudio.exe <华虹PAT私有home> local-evidence/<新目录>/pat-ui
```

前端源码变更后另运行 `npm run build`（工作目录 `apps/web`）。P0-3审核当时只修改文档和验证脚本；后续0.3.4功能按钮与工作台简化的构建/验证另见 [0.3.4发布记录](RELEASE-0.3.4.md)。

真实引擎路径与数据对账另见 [P0-2](VALIDATION-KIT-SPAWN-20261029.md)；`run_standalone_smoke.py --kit`、`verify_real.py --matrix`、`verify_ft_reference.py`、`verify_jiemin_dynamic_contract.py` 和 reconcile 辅助脚本均需按 `--help` 提供私人样本/矩阵，帮助或语法通过不等于业务计算通过。UI 入口本轮实际结果见 [迁移审核](VALIDATION-MIGRATION-20261029.md)，证据保留规则见 [本地证据](LOCAL-EVIDENCE.md)。

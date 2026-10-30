# Data Studio · CP/FT 本地数据工作台

独立桌面项目，提供 CP/FT 数据清洗、PAT、SBL/SYL、本地图表及历史记录。采用 PySide6/Qt WebEngine + React，计算由锁定版本的 CP/FT Python 引擎执行。

- 项目目录：`F:\DataStudio`
- 私有仓库：https://github.com/Chenchao981/data-studio
- 与 PYMS 独立维护；需要共享的改动由项目负责人手动核对、移植。
- 用户源数据和分析结果留在本机，不随 Git 或发布包上传。

## 本机使用

双击根目录的 `启动DataStudio.bat`，优先运行已核验的 `dist/v0.3.9/DesktopDataStudio/DesktopDataStudio.exe`，新版缺失时依次回退0.3.8、0.3.7、0.3.6、0.3.5和旧目录 `dist/DesktopDataStudio/DesktopDataStudio.exe`。
当前本机程序为0.3.9，清洗按钮下直接显示实时滚动日志，取消独立“任务进度”入口，结果显示清洗耗时；真实样本耗时及优化边界见 [0.3.9记录](docs/RELEASE-0.3.9.md)。CP/FT图表统一隐藏CONT类参数，详见 [0.3.8记录](docs/RELEASE-0.3.8.md)。CP/FT PAT仍共用固定FT统计实现，名称统一为“工厂名称PAT统计”，详见 [0.3.7记录](docs/RELEASE-0.3.7.md)；旧历史报表保留原算法，重新执行才使用新算法。CP图表保留默认组合图和按需重绘，输入/输出路径继续支持粘贴编辑。当前用户安装包仍为0.3.3。请先关闭原工作区窗口，再从根目录启动新版。
历史记录继续使用 `%LOCALAPPDATA%\NCE\DesktopDataStudio-M0`；原有清洗输出路径不变。
同一工作区仅运行一个实例，计算任务串行排队。

## 用户端安装包

用户安装包统一放在 [`release/`](release/README.md)，按应用版本分目录。
运行 `packaging/publish.ps1`，会核验现有 Windows 发布目录和固定引擎，然后生成中文离线安装程序、安装使用说明、校验值和版本回执。
需要从源代码重新构建时使用 `packaging/publish.ps1 -Rebuild`。

安装包默认按当前用户安装，提供桌面/开始菜单快捷方式和 Windows 卸载入口；用户无需预装 Python、Anaconda 或 Node.js。个人历史、日志和清洗输出在升级或卸载时保留。

## 开发环境

Windows x64，先安装 Git/GitHub CLI 和 Node.js。Python 使用 `runtime-lock.json` 指定的官方 CPython，由脚本安装到项目内，依赖严格按 `environments/*.lock` 安装。

```powershell
git clone https://github.com/Chenchao981/data-studio.git F:\DataStudio
cd F:\DataStudio
.\setup.ps1
# 先按下方说明准备经过校验的 engines 目录
.\.venv-cpython\Scripts\python.exe packaging/prepare_engines.py --source-only
.\.venv-cpython\Scripts\python.exe -m pytest -q
.\packaging\build.ps1 -SkipArchive
.\启动DataStudio.bat
```

计算组件属于外部固定构建输入，不随 Git 提交。新开发机器可从已验证安装包的安装目录复制 `engines/` 到项目根目录，再执行上面的 `prepare_engines.py --source-only`，按本仓库源代码刷新适配器。引擎清单固定全部文件的校验值，原 CP/FT 工具包的固定哈希在 `engine-pins.json`，不可用未知版本替换。用户端安装包已包含这些组件，运行不依赖 GitHub 或 PYMS。

## 代码结构

| 目录 | 用途 |
| --- | --- |
| `apps/web` | React 界面 |
| `apps/desktop` | Qt 桌面入口 |
| `python_core` | 本地任务、历史、文件、引擎调度 |
| `engine_support` | 独立维护的离线计算适配器与数据契约 |
| `packaging` | 环境、引擎、校验和 Windows 打包 |
| `tests` | 工作台回归与真实数据验证工具 |
| `environments` | 固定依赖版本 |

`engine_support/backend/app` 和 `engine_support/local_agent` 保留历史导入名，但仅包含本地计算需要的模块，不包含 PYMS 网页/API 服务或数据库部署。导出来源见 `engine_support/SOURCE_FILES.json`。

## 维护边界

新项目接续先读 [完整交接](docs/HANDOFF-2026-10-29.md) 和 [待办清单](docs/TODO.md)。本机 `.remember/remember.md` 是接续入口；交接文档和待办纳入 Git，个人接续文件仅保存在本地。

当前可用的验证命令、所需样本和脚本边界见 [测试入口](docs/TEST-ENTRYPOINTS.md)。关键验收回执及截图保存在本地 `local-evidence/`，索引见 [本地证据说明](docs/LOCAL-EVIDENCE.md)；该目录不进入 Git。

迁移说明与手动关联规则见 [独立项目说明](docs/STANDALONE-PROJECT.md)。其余早期设计和验证文档保留历史背景，其中旧目录/版本是当时的记录；当前启动、安装和构建以本 README 为准。

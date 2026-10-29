# 指定引擎在 spawn 子进程中的验证

日期：2026-10-29。完成 TODO P0-2；只修改验证脚本和回归测试，应用及计算规则仍为 0.3.3 / `studio-engine-20261029.1`。

## 原因与修复

`run_standalone_smoke.py` 原来只在 `main()` 内覆盖 `engine.engine_root`。Windows `TaskManager` 使用 spawn，子进程重新导入脚本为 `__mp_main__`，不执行 main；因此重新导入的 `python_core.engine` 使用默认项目目录。相同 manifest 的另一套 kit 可能让错误路径静默通过。

现在由验证脚本在 `__mp_main__` 初始化时读取父脚本设置的 `STUDIO_VALIDATION_ENGINE_KIT`，重新绑定路径。产品模块不读取此环境变量。验证脚本仅在工作进程内包装 engine 的进程启动接口，保留原有启动、校验、取消和发布流程。

每个成功任务必须取得并核对：工作进程 PID、操作系统返回的 runtime EXE 路径、完整启动命令、runner 路径、PYTHONPATH、manifest/工具包 SHA-256，以及计算环境注册表中的 runtime 与复制后 CP/FT 包哈希。最终业务回执的 package 哈希也必须匹配。证据写入任务内部 `validation-engine.json`，完整注册信息另随验证脚本 JSON 输出保存，不发布到用户报告目录。

## 实际验证

引擎位置分别为项目 `engines/`，以及原 0.3.3 安装包解出的 `build/p0-2-20261029/安装包独立目录/engines/`（中文及空格路径）。每套 14,096 个清单文件均先完整核验；两套 manifest 和固定 CP/FT 包哈希一致。独立目录真实进程的 EXE、runner 和代码搜索路径均指向该目录；注册表中的 CP/FT 副本哈希与该 kit 及业务回执匹配。

| 样本 | 项目 kit | 安装包 kit | 结果对账 |
| --- | --- | --- | --- |
| 华虹 `NCEVTG120EV60DA_FA69-9348@203.zip`，1 ZIP、13 TXT、1,950 条、17 参数 | SUCCESS | SUCCESS | 每套均独立核对 221 个统计/规格单元格，输出一个产品 PAT Excel |
| 上海捷敏 `NCEP6050AQU-Y_C204876.00_NCEG32606010_DC_260618214853.xls`，1 文件 | SUCCESS | SUCCESS | 每套 67,132 行、18 参数逐行映射核对，批次均为 `C204876.00` |

两套 CP、FT 输出均通过工作表名称、行数、逐单元格值摘要比对，源文件运行前后 SHA-256 一致。FT 原回执 `records` 为 null，以上计数直接取原始文件及输出核对。FT 共核对 1,207,274 个数值、1,080 个源空值及 22 个 `over`；后两者按既有输出合同为空，不当作数值或零。FT DC 清洗原合同没有 Bin 列；只记录源 Bin 分布（1: 67,031；2: 65；4: 29；3: 7），不宣称输出新增或核对了 Bin 列。

在独立解包 kit 中分别修改 `cp.pyz` 和 `native.pyz` 的一个字节后，CP、FT 真实任务均在目标包校验处 FAILED，输出目录为空，没有回退。每次测试均在 finally 中恢复原包并核验原哈希，项目 kit 和发布安装包未被修改。

自动回归：`64 passed, 1 skipped`。新增三个用例覆盖 spawn 子进程拒绝目标包篡改、拒绝目标包缺失，以及产品引擎忽略测试环境设置。跳过项仍为 Windows 符号链接创建权限不足。

## 证据与复现

本地证据根目录：`F:\DataStudio\build\p0-2-20261029`，不进入 Git。

- `summary.json`：两套 kit 的完整文件核验记录、四组真实任务路径、包哈希、注册表和工作簿内容摘要。
- `reconciliation.json`：独立 CP 统计对账、FT 原始值映射核对、源 Bin 分布、目标包篡改拒绝和恢复确认。
- `project-cp.log`、`project-ft.log`、`installer-cp.log`、`installer-ft.log`：四组成功任务及路径证据。
- `tampered-cp.log`、`tampered-ft.log`：目标包损坏时失败回执。
- `*-v2/results/<任务ID>/validation-engine.json`：工作进程记录的实际启动证据。
- `run_matrix.py`、`reconcile.py`：此次私有样本验证过程，路径及结果仅保留在本地。

从项目根目录执行（每次使用新的独立 home）：

```powershell
.\.venv-cpython\Scripts\python.exe -m pytest -q -rs tests engine_support/desktop_client/tests
.\.venv-cpython\Scripts\python.exe tests/run_standalone_smoke.py --kit <目标engines目录> --source <真实输入文件> --tool LOCAL_CP_HUAHONG_RAW_PAT_V1 --home <新的CP验证工作区>
.\.venv-cpython\Scripts\python.exe tests/run_standalone_smoke.py --kit <目标engines目录> --source <上海捷敏DC文件> --tool LOCAL_FT_JIEMIN_FT_ALL_V1 --home <新的FT验证工作区>
```

这次验证使用安装包解出的载荷，未重新运行安装生命周期，也未在另一台干净机器运行；P0-4 继续保留。未重建应用、适配代码或发布包。

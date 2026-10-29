# P0-3 迁移文档与验证入口审核

日期：2026-10-29。基线应用 0.3.3 / 固定引擎 `studio-engine-20261029.1`。本轮修改文档、验证脚本及本地证据收集工具；未修改产品或计算规则，未重建引擎或发布包。

## 已修正

- QUALITY-GATES 与华虹 PAT 当前复现命令按 `F:\DataStudio` 根目录更新，使用项目固定解释器和 `engine_support/desktop_client/tests`。历史报告保留原日期与统计。
- STANDALONE-PROJECT 按本地离线安装包分发的事实改写；明确暂无 GitHub Release 引擎资产、自动下载脚本或企业下载点。本轮实际查询仓库 Release 列表返回空数组。新开发机仍需完整固定引擎和私人业务样本。
- PLAN、CONTRACTS 顶部标明历史设计，当前入口由 README、交接及 TEST-ENTRYPOINTS 约束；修正 VALIDATION.md 对迁移前文档的断链引用。
- `verify_real_ui.py` 改用真实导入及文件夹结果，导出保存在独立测试目录，不等待已移除的工作表预览。
- `verify_workflow_ui.py` 从启动自动恢复997条旧登记，改成启动空列表后显式导入100项合法布局夹具；恢复当前分页/取消勾选按钮，移除预览搜索步骤，增加 CP 工具码参数。真实计算、历史过滤和导出校验仍保留。
- `verify_cp_restore_ui.py` 使用当前打开结果文件夹按钮、三 CSV 哈希核对及实际回执记录数，移除固定3,875条/工作表选择器要求。明确 HTTP 就绪和进程回收不代表图形渲染验收。
- `verify_resize.py --charts` 依赖已移除演示界面，现明确报错并指向真实 Cockpit 检查；保留原生窗口和故障恢复检查。
- 冻结 PAT 脚本按成功华虹 PAT 操作定位，不要求历史名字固定为 `CP data 20261019`。完整冻结工作流脚本明确定位并重跑上海捷敏 DVDS，增加样本前置条件，避免误重跑任意第一条历史。
- 审核未改选择器的 paths、FT DVDS、factory、performance 及 installer 脚本；图表脚本显式注明专用样本（1批、25片、13参数、VTH/W2），不当通用小样本验证。
- 显式等待拖放后的 React 列表和历史筛选更新，消除旧验证脚本抢先导航/取按钮的时序问题。

## 证据留存

47份原回执、日志及截图已复制到 `local-evidence/2026-10-29/baseline-and-p0-2`，每份校验来源与副本 SHA-256，`missingSources` 为空。复制后再次核验全部47份副本通过。只收集回执/日志/截图，不移动原始输入、报告或用户历史。

本轮执行记录及修复后复测位于 `local-evidence/2026-10-29/p0-3/`。原失败尝试保留，修复后使用新目录；静态入口检查保存到 `entrypoint-static.json`。原始回执中的旧绝对路径保持不变，副本可作为证据查看，不能冒充可运行的完整历史。详见 [本地证据](LOCAL-EVIDENCE.md)。

Python/引擎支持回归：`64 passed, 1 skipped`，跳过原因仍为 Windows 符号链接权限。Python 帮助入口及 JavaScript 语法检查共16项通过；README/docs 内部文件链接核对通过。

## 实际入口复测

所有测试串行运行在本机独立目录，使用现有开发构建和原冻结 EXE。初次 desktop、real CP 与 workflow 的失败回执保留；修复列表更新/筛选等待及旧导航后，以下复测通过，不将失败目录伪装成成功。

| 入口 | 本轮结果 | 稳定证据（相对 p0-3/） |
| --- | --- | --- |
| desktop | PASS：原生选择、100项拖放、空结果页、内部任务生命周期、安全限制 | `desktop-retest/evidence.json` |
| real UI：华虹 DCP ZIP | PASS：真实清洗、文件夹结果、ZIP导出校验、主题 | `real-cp-retest/evidence.json` |
| real UI：上海捷敏 DC 单文件 | PASS：真实清洗、结果及ZIP导出；修订后的脚本再次复测 | `real-ft-retest/evidence.json` |
| workflow：布局 / 真实CP+FT | PASS：100项导入、50行DOM、分页、Qt拖放、任务选择及历史 | `workflow-layout/evidence.json`、`workflow-real-retest/evidence.json` |
| paths | PASS：原生混合选择、桌面/目录记忆、重启空列表、三CSV哈希 | `paths/evidence.json` |
| FT DVDS | PASS：实际日志、完成状态、草稿隔离、重启历史 | `ft-dvds/evidence.json` |
| factory | PASS：CP/FT各20家布局夹具、主题、键盘和搜索 | `factory/evidence.json` |
| resize + recovery | PASS：100次缩放、最大化/还原、当前两屏150%/125%、黑屏采样为0；两次主动终止渲染器后恢复且后台内部任务成功 | `resize/evidence.json` |
| CP restore | PASS：三CSV导出哈希、打开文件夹、Cockpit会话复用/关闭；仅HTTP及进程生命周期 | `cp-restore/evidence.json` |
| frozen PAT | PASS：当前PAT入口、产品汇总提示及真实历史结果，无Excel预览 | `frozen-pat/evidence.json` |
| frozen workflow | PASS：工厂操作、DVDS重新执行及日志、结果任务选择、主题/小窗口，无前端异常 | `frozen-workflow/evidence.json` |
| performance | PASS：连续3轮启动1,243/1,294/1,237ms，阶段/工厂/搜索各项p95最大118.2ms；非冷启动/整机承诺 | `performance/evidence.json` |
| installer | 本轮仅静态审核，历史安装生命周期证据已归档 | `../baseline-and-p0-2/baseline/installer/evidence.json` |
| CP图形渲染 | 本轮仅语法/专用样本前置条件审核，未重跑25片绘图场景 | `entrypoint-static.json`，范围见 TEST-ENTRYPOINTS |

冻结 DVDS 真实任务期间100ms定时器额外延迟p95约9.9ms，样本295个、无long task。布局脚本首次100项输入阶段切换采样p95为323ms，功能通过但该次压力采样超预算；真实工作流复测p95约185.9ms。保留两次数据，不能把本轮标准性能入口PASS扩展为所有压力情形的性能承诺；完整性能维护仍归P1-4。

## 验证边界

安装生命周期本轮未重跑，原0.3.3证据已归档；另一台干净机器验收仍属于 P0-4。真实 CP Cockpit 的专用25片样本绘图脚本本轮完成静态审核，未以任意小样本冒充该场景通过。功能检查通过和性能预算通过分别记录，未因偶发时延修改验收线。当前 README/docs 内部文件链接应全部可解析；历史命令中保留的旧前缀仅作为当时的记录。

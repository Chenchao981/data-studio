# M0 桌面技术验证 · 2026-10-23

本轮按用户架构任务书先交付M0，真实CP/FT引擎迁移属于M1。随后追加的环境统一和真实数据复核另行记录，不能用下述模拟测试替代。

## 环境与构建

- 官方CPython 3.13.17，项目独立venv；PySide6/Qt 6.10.2，SQLite 3.50.4。
- Windows 11开发机；React 19.2、Vite 7.2.2、TypeScript 5.9.3、AG Grid Community 34.3.1、ECharts 6.0.0。
- 前端生产构建通过；分块包约1.83 MB，Vite给出体积提示。资源全部本地，不依赖CDN。
- PyInstaller 6.16 onedir构建通过。实际交付包的运行时文件约576 MB，主要体积来自Qt WebEngine。
- 构建PATH只包含项目解释器与Windows目录；额外检查所有收集DLL的来源，阻止全局工具污染。曾发现Poppler的同名ICU DLL被误收集，已通过隔离构建修正，最终包不含该DLL。

## 已验证

1. Python测试14项通过：受限分页、跨页排序、筛选、注入拒绝、全量统计、100文件登记、设置历史持久化、重启恢复、独立进程成功/失败/取消、结果哈希与关闭回收。
2. 浏览器Mock界面测试通过：六页面、浅深主题、表格、图表、模拟任务、小窗口截图，无JavaScript异常。
3. 真实Qt窗口通过：原生Windows对话框选择中文路径、Qt拖放100文件、React/QWebChannel双向通信、实际表头排序、图表、任务进程和网络/导航限制。输入内容未改变。
4. 官方CPython三个Qt进程缩放运行全部通过：

| QT_SCALE_FACTOR | 首次10万行示例生成并返回100行 | 200行响应字节 | UI心跳最大间隔 |
|---|---:|---:|---:|
| 1 | 304 ms | 27,630 | 157 ms |
| 1.25 | 303 ms | 27,630 | 155 ms |
| 1.5 | 380 ms | 27,629 | 146 ms |

以上是本次单次测量，含示例缓存初始化，不是生产吞吐量或严格性能保证。前端只保存最多3个100行缓存块；统计在Python/SQLite完成，直方图计数与全量100,000行/单批25,000行对账，散点最多2,000点。

5. 独立EXE验收通过：仅Windows系统目录PATH，启动Qt内React、实际点击批量模拟、冻结进程成功/预期失败、10万行表格、ECharts、暗色主题、正常退出。已检查进程加载模块，没有Anaconda、venv或开发用便携Python路径。调试接口只在测试子进程的环境中临时开启，普通启动不设置该接口。

本地证据：`artifacts/cpython-desktop`、`artifacts/cpython-scale125`、`artifacts/cpython-scale150`、`artifacts/ui`、`artifacts/package-1792744131650`。证据及工作区均不纳入源码库。

## 同日统一环境补充

后续同日环境统一补充：新工作台开发环境已安装 `environments/studio.lock`，与服务器共享41个计算依赖。版本检查、14项Python测试及真实Qt复测通过（本轮单次冷预览594ms、最大心跳间隔204ms）。真实CP/FT引擎在独立验证流程中完成34场景对账，但尚未接入M0界面；详见迁移前仓库的 `docs/validation/RUNTIME_UNIFICATION_2026-10-23.md`（未随本项目迁移，不能当作本仓库可执行入口）。

当前便携交付文件 `dist/DesktopDataStudio-M0-20261023-unified.zip`，SHA256 `a7b2901faf079bd466e75445354693b1b8404ef3373e4166df43257f0b0b253e`。本轮更新包内开发说明，EXE业务代码与此前通过验证的CPython包相同；M0不携带真实计算引擎。

## 尚未验收

- 干净Windows 11、无开发工具电脑、实际修改系统DPI后的125%/150%组合；当前为Qt进程缩放测试，不能当作已改系统DPI。
- M0界面中的真实CP/FT解析、统计结果一致性、账号同步、服务端上传、安装升级和自动更新。
- 批量输入登记不等于100份大文件实际清洗；本阶段不读取用户原件内容。

## 复现

按README准备锁定环境后，执行Python测试、`tests/verify_desktop.py`，前端目录执行`node verify-ui.mjs`。打包使用`packaging/build.ps1`，前端目录执行`node verify-package.mjs`验证产物。后者只控制自己启动的测试程序。

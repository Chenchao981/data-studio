# 工厂选择卡片 · 0.3.1-m1

CP / FT 工作台顶部改用统一尺寸的工厂卡片：中文名称、短字标识、实际可用功能数和独立选中标记。短字标识不是企业商标。参考 Carbon selectable tile 与 Fluent 2 card 的交互原则，保留键盘焦点和整张卡片点击。

搜索支持已接入工厂的中文名称、工厂代码、拼音和简称。没有匹配时提供清空入口；筛选不会更改当前工厂或功能，当前工厂始终显示在标题栏。切换 CP/FT 时搜索清空，工作台自己的工厂、功能、文件和合并设置继续保留。网格最多约两行高，其余工厂在内部滚动，避免不断挤压输入与待分析区。

本次没有更改清洗器、输入合同、输出目录规则或任务队列。计算组件继续使用 studio-engine-20261027.3。没有加入生产演示数据或虚构工厂，也没有启用账号同步或服务器发布。

## 验证证据

- TypeScript 检查与生产构建通过，PyInstaller 在隔离 PATH 下完成 Windows 客户端构建。
- `tests/verify_factory_ui.py` 在独立测试进程中注入临时目录定义，CP 和 FT 各补足20家，仅用于布局测试；不修改磁盘引擎目录、不执行模拟清洗、不写入用户工作区。1440×960、920×620，亮暗主题共8组通过；检查两行高度限制、横向溢出、滚动到底、Enter 键选择、中文/拼音筛选、无匹配后保持选择。创建任务数为0。
- `apps/web/tests/verify-bundle-ui.mjs` 对冻结 EXE 验证真实六个 FT 工厂菜单、上海捷敏拼音搜索与无匹配状态、CP/FT 切换记忆、任务进度入口、真实上海捷敏 DVDS 重跑及滚动日志、结果选择器、默认输出设置、窄窗和深色主题。测试使用独立工作区，前端异常数为0。
- 安装包真实数据验证沿用 `NCEAP60ND30AG(M)-2G00_NCEG52609229_DVDS.xlsx`。本次界面改动没有重新执行全部 CP/FT 格式的数据对账，也没有测量清洗引擎性能提升。

本地证据：`artifacts/factory-cards-20261027/`，包括布局截图、冻结客户端截图、构建日志及 PASS 回执。更新前备份本机历史数据库，更新仅复制变化的客户端文件，跳过 engines；更新后核对历史与设置。

参考：

- https://www.carbondesignsystem.com/building-blocks/core/components/tile/guidelines
- https://fluent2.microsoft.design/components/web/react/core/card/usage

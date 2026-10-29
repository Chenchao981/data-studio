# Data Studio 0.3.3 用户端安装包

日期：2026-10-29。程序使用固定 CPython 3.13.17，计算引擎为 `studio-engine-20261029.1`，保留原有 56 项操作。

## 分发文件

- 位置：`release/v0.3.3/DataStudio-0.3.3-win-x64-Setup.exe`
- 文件大小：256,363,316 字节，约 244.49 MiB。
- SHA-256：`9393bb293bb91812d4f56ff9b1b4b5064a9f043fc5d506edf819e3919cbba299`
- 安装包来源提交：`f8d75799f3d1b5b21c15f3cbb93d98e59f16c193`。
- 同目录提供安装使用说明、`SHA256SUMS.txt` 和 `release.json`。
- 安装包当前没有企业数字签名。生成的二进制及测试数据仅保留在本地，发布脚本与说明由 Git 管理。

## 本机验证

在临时中文及空格路径中实际运行安装程序，并核对 18,456 个程序文件的完整 SHA-256 清单；当前用户的 Windows 卸载注册项、桌面和开始菜单入口均正常。

覆盖安装保留了历史目录内的测试标记和安装目录内自行添加的文件。安装后的真实客户端在隔离的 PATH 下启动，CP/FT 工厂入口、华虹原始 PAT 选择、产品汇总提示、真实历史结果查看均通过，界面没有请求 Excel 预览，也没有前端运行异常。

卸载测试确认：程序文件、快捷方式及卸载注册项已移除，个人历史标记与自有文件保留。测试自身创建的临时标记随后清理，未删除个人历史或真实清洗结果。

本地证据：`build/installer-validation/0b401f09/evidence.json` 及其 `ui/` 子目录；回归命令见 `tests/verify_installer.py`。本次只调整版本显示及发布流程，前端构建通过，简洁工作区与渲染相关的 7 项回归通过，计算规则未改动。

2026-10-29 证据整理补充：以上回执、UI 截图和构建日志的校验副本已保存到 `local-evidence/2026-10-29/baseline-and-p0-2/baseline/installer/` 及同级日志文件，来源与 SHA-256 见该归档根目录 `archive-manifest.json`。复制归档不表示重新运行安装生命周期；详见 [本地证据](LOCAL-EVIDENCE.md)。

## 后续发布

先准备并验证新的 `dist/DesktopDataStudio`，更新应用版本后执行 `packaging/publish.ps1`。安装文件按版本存放，脚本不会覆盖已经存在的版本目录。固定组件的每个文件都会核验，校验值和来源提交写入版本回执。

安装工具使用固定 NSIS 3.12，来源和 SHA-256 见 `packaging/nsis-lock.json`，工具使用的许可证随安装包放入 `licenses/NSIS-COPYING.txt`。工具说明和许可证来源：[NSIS 下载](https://nsis.sourceforge.io/Download)、[NSIS 许可证](https://nsis.sourceforge.io/Docs/AppendixI.html)。

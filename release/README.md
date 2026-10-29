# 用户端发布目录

本目录按版本存放可发给用户的 Windows x64 安装包。

每个 `v<版本号>/` 目录包含：

- `DataStudio-<版本号>-win-x64-Setup.exe`：用户双击安装，已包含运行环境和 CP/FT 计算组件。
- `安装使用说明.txt`：安装、更新、卸载与个人历史说明。
- `SHA256SUMS.txt`：发布文件的 SHA-256 校验值。
- `release.json`：应用、引擎、来源提交和打包工具的版本回执。

向用户发送整个版本目录，用户只需运行其中的安装程序。默认安装到当前用户目录，不需要另装 Python、Anaconda、Node.js 或 Git。

发布流程：先准备并验证 `dist/DesktopDataStudio`，再运行 `packaging/publish.ps1`。安装包及其附属文件保留在本地，不进入源代码 Git 仓库。

首次分发的安装程序尚未进行企业代码签名；企业签名证书由组织统一管理。

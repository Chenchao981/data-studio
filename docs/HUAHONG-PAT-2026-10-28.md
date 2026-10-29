# 华虹 DCP 原始数据 PAT：FT 口径（2026-10-28）

## 修复范围

本机 Data Studio 引擎 `studio-engine-20261028.3` 提供
`LOCAL_CP_HUAHONG_RAW_PAT_V1`，入口为 **CP 工作台 → 华虹 → PAT（原始数据，FT口径）**。
旧华虹 PAT 入口从新建任务列表隐藏；旧历史和旧工具代码仍保留，旧失败任务应从工作台新建。
本次不修改 PYMS 服务端的旧 CP PAT 公式，也不发布服务器。

原错误出在旧共享清洗入口：目录分支只枚举 TXT/XLSX，未递归准备目录中的 ZIP，
得到空格式集合后误报“DCP/TXT 与 TD/XLSX 必须分开上传”。同时旧 CP PAT 是
5Sigma/1.349 算法，不能直接称为 FT 口径。

## 数据与计算合同

- 复用固定 CP 包的安全解压、Lot/Wafer 检查和 DCPReader；支持 TXT/DCP、递归文件夹、ZIP/7z/7zip/RAR。
- 当前新增 PAT 入口针对 DCP/TXT；TD Excel 不是该入口支持的格式。
- 用户确认命名规则：`NCEVTG120EV60DA_FA69-9491@203` 中，`NCEVTG120EV60DA` 是产品，`FA69-9491` 是完整批次，`203` 是站号。
- **一个产品汇总生成一个 PAT Excel**，文件名为 `<产品>_PAT_YYYYMMDD_HHMMSS.xlsx`；批次、站号和测试程序不再拆分报告。多个产品分别输出各自的一份 Excel。
- 同一产品内参数、规格、单位和测试条件必须一致；不同站号/程序的所选记录合并后重新计算分位数，不平均旧报告统计值，不自动选“最近一次”。同一采集范围内 Lot/Wafer 重复仍拒绝。
- 直接统计原始测量值，包含失败 Bin 和有限超规格数值，不先做 IQR 异常值清洗。No.U、坐标、Bin 等不是 PAT 参数。
- 原始 SI 测量值转换到源规格声明的单位，例如 A → nA；参数名显示单位，避免小电流被六位小数舍入为零。
- 直接调用固定 FT 包 `shared.pat_engine.build_spooled_raw_pat`：线性分位数，Sigma=(Q3-Q1)/1.35，中位数±6Sigma，样本标准差 ddof=1。
- 直接调用 FT `write_excel_fast`：PAT 工作表、17 列及“变量”行；“更新前”填源规格，“更新后”“是否更新”留空。
- 文件逐个解析、数值落盘缓存；不合并整批 DataFrame。结果页继续只提供打开文件夹，不预览 Excel。
- 对外输出目录仅有 PAT Excel。`PAT_source_manifest.json` 移到 APP 内部任务历史，保留程序、站号、源 Lot/Wafer/日期时间、行数、参数条件和文件哈希，不发布到用户输出目录。

## 真实数据验收

输入为用户指定的 `CP data 20261019`：1 个产品、35 个批次、39 ZIP、490 TXT、96,650 行。
输入构成如下，最终合并为 **一份 Excel、一个 PAT 工作表、17 个参数**：

| 分组 | 程序 | 源文件 | 行数 | PAT 参数 |
|---|---|---:|---:|---:|
| @202 | CN0467_G0N31AD_T1_A01_TEMP250919.dll | 50 | 30,650 | 17 |
| @203 | CN0467_G0N31AD_T1_A01.dll | 440 | 66,000 | 17 |

原生计算实测 40.00 秒；通过已安装组件、校验、执行、结果发布和历史保存的完整任务实测 51.31 秒。
这属于本次数据和本机测量，不是所有数据规模的性能承诺。

`packaging/validate_huahong_pat.py` 独立从 ZIP 成员读取原始数值，以 NumPy 计算，
逐项比对 221 个统计/规格单元格，同时核对每个源文件哈希、行数和报告结构。
开发输出和最终桌面发布输出均通过；参数缺测按 FT 规则排除，因此各参数有效计数可以不同。

- 20 项本地桥接/PAT 测试通过，包括产品/批次解析、跨站号原始值汇总、多产品独立报告、同组重复拒绝、跨程序规格冲突拒绝、单位换算、保留失败 Bin/异常值、排除 No.U，以及仅发布 Excel。
- 冻结 EXE 实际界面验证通过：PAT 可点击、每产品一份 Excel 的帮助文案、真实历史结果可打开、不请求 Excel 预览。
- 用户本地历史任务：`124768203c78425bbfe99b0adc76926e`。
- 按用户要求，输出仍放在桌面 `HUAHONG_20261028_173142`，目录里只有 `NCEVTG120EV60DA_PAT_20261028_175234.xlsx`。
- 旧目录整体移入 APP 内部备份，含用户新增的 ZIP，旧历史定位也改到备份；未删除旧报告或用户文件。
- 原始数据、报告和测试截图不提交版本库。实际证据在忽略目录 `outputs/huahong_product_pat_20261028/`。

## 安装与复现

`prepare_engines.py --local-code-only` 先校验现有引擎，再只更新本地适配器和目录清单，
保留原有后端、CP/FT 包和 Python 环境基线。标准全量构建也生成同一版本。
本次只替换已安装客户端的产品汇总适配器、入口说明及 manifest；原文件保存在验证目录的 bundle-backup。

验证命令：

```text
python -m pytest desktop_client/tests/test_local_native.py desktop_client/tests/test_huahong_ft_pat.py -q
python desktop-data-studio/packaging/validate_huahong_pat.py <原始ZIP目录> <结果目录> <校验回执.json> --manifest <内部任务/PAT_source_manifest.json>
node desktop-data-studio/apps/web/tests/verify-huahong-pat-ui.mjs <已安装exe> <仅含本次已完成任务的测试工作区> <截图目录>
```

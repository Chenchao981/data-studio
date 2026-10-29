# Data Studio 0.3.7：CP/FT PAT统一算法与名称

2026-10-29。按用户确认，所有CP PAT统一使用FT算法，后续保持一致。程序0.3.7，计算组件`studio-engine-20261029.3`，固定CPython 3.13.17及原有CP/FT三个PYZ包不变。

## 名称与算法

CP、FT可见PAT按钮和历史页面的操作显示名统一为“当前工厂名称PAT统计”，例如“华虹PAT统计”“佳泰PAT统计”“上海捷敏PAT统计”。工厂已有隐藏/开放范围不变，共9个可见PAT按钮；集佳原隐藏PAT入口未开放。

此前华虹已用FT算法，佳泰/立昂微/国宇仍通过原CP包的5Sigma实现。现在所有CP PAT在本地工作进程中直接路由至FT统计适配，调用固定FT包的`shared.pat_engine`；不再调用旧CP `quick_pat.py`。四分位数采用pandas线性插值，Sigma=IQR/1.35，计算限为中位数±6Sigma；不再使用旧CP最小IQR=0.0001和至少10个有效值的限制。不按Bin或IQR排除测量值，非数值/缺测保持缺测；规格“更新后”和“是否更新”按FT格式留空，不自动改规格。

统计代码不是复制的CP实现。native/shared FT包中的`shared/pat_engine.py`当前SHA-256均为`c495f0819c08a83e4a49386d5387606cc961aebe3ba607b20417251238c1bbe4`。构建时新增一致性校验，未来两个FT包的该模块不同则拒绝生成组件；CP加载时继续校验指定FT包哈希和实际模块来源。`AGENTS.md`已明确统一算法约束，新CP PAT未接入统一适配时禁止回退旧算法。

## 输入与物理口径

工厂仍承担源格式、身份、单位、规格和条件适配。CP识别`Lot_ID`/佳泰`LotID`，保留真实Lot；TEST_NUM/SITE_NUM等元数据不作为测量参数。参数、单位、规格、条件不一致的输入停止合并；跨Lot还需一致的明确产品标识，产品未知不能跨Lot混合。多个明确选择的CP文件只读取所选文件，不读取同目录其他文件。

FT报表按6位小数输出，为避免SI小量被舍成0，CP的A/F/s/H在送入同一FT函数前等比例显示为nA/pF/ns/nH，规格同步换算，报表标明实际显示单位；原始测量和标准CSV不变，内部清单记录原单位、显示单位及比例。例如0.00000002A在报表中为20nA。其他已有工程单位不重复换算。

华虹继续按兼容产品汇总，一个产品一个PAT Excel，原始数据和站号/程序溯源保留。其他CP也只将PAT Excel放入用户结果文件夹；清单和中间CSV留在内部任务历史。旧5Sigma历史报表不改写，重新执行才使用新算法。

真实国宇样本暴露原读取器固定行偏移错误（把Average错作上限）和目录名覆盖LotName的问题。本轮仅在PAT源适配层复用原读取器的测量/Bin/计数校验，并按Min Limit/Max Limit/Bias标记读取规格和条件，采用文件LotName。真实样本为Lot 25B103、3,266行，CONT2规格0～20mV；Over保持缺测。本轮没有重建或修改原CP包，原国宇“数据清洗”流程的固定行规格/目录身份问题尚未修正，不应把PAT修复当作该清洗流程已验收。

## 验证与交付

稳定本地证据：`local-evidence/2026-10-29/pat-unified/`。

| 真实输入 | 行数 | 参数 | 已核对 |
| --- | ---: | ---: | --- |
| 佳泰单片XLS | 2,581 | 22 | 全部报告单元格与FT函数、独立6Sigma公式一致 |
| 立昂微单片XLSX | 882 | 9 | 全部报告单元格与FT函数、独立6Sigma公式一致 |
| 国宇单片XLS | 3,266 | 7 | 全部报告单元格；原始逐值、LotName及标签规格一致 |
| 华虹DCP ZIP | 1,950 | 17 | 逐个原始TXT重新取值，与FT函数报告一致 |
| 上海捷敏FT DC XLS | 回执总数仍为未知 | 18 | 原FT PAT真实执行成功，固定包和统计模块未改变 |

- `pytest-complete.txt`：82通过、1跳过；跳过Windows符号链接权限。包括零IQR、少样本、Fail Bin极值、小电流换算、不兼容条件/规格/产品拒绝、错误FT包拒绝、佳泰别名、国宇表头偏移和未来模块分叉拒绝。
- `real-home-final/`、`reference-home/`：以上真实源任务及内部数据；输入指纹重新核对未变化。
- `frozen-home/`：三家CP使用独立分发目录kit真实重跑，报告与开发kit逐单元格一致。
- `reconciliation-final.json`：三家CP 646个报告单元格、华虹289个报告单元格；FT函数、独立公式、原始国宇/华虹数据及源哈希核对。
- `pat-label-ui/`、`operation-ui/`、`frozen-app/`：分发资源中的9个PAT名称/选择、10家工厂37项操作的布局与选择、实际EXE的华虹入口和真实历史结果检查。
- `bundle-verification.json`：15,530个组件文件完整校验；前端资源与构建一致。

早期失败记录保留：首次组件刷新遇到能力对象不存在help字段；真实样本依次发现佳泰LotID别名、国宇规格行偏移和单Excel需要封装成受控目录；已修正后用新目录复测。中间失败与旧结果不改写为成功。本次只覆盖所列真实样本和合成边界，不等于所有工厂格式/批量规模及另一台干净机器已验收。

本机独立程序：`dist/v0.3.7/DesktopDataStudio/DesktopDataStudio.exe`。根目录启动脚本优先新版；个人历史位置不变，先关闭旧窗口再打开。保留0.3.6，未生成新安装包，0.3.3安装包不变。

复现数值对账：

```powershell
.\.venv-cpython\Scripts\python.exe tests/verify_pat_consistency.py --home <三家CP私有home> --frozen-home <同样本分发kit私有home> --reference-home <华虹CP与捷敏FT私有home> --output <新的JSON文件>
```

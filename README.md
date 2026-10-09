<p align="center">
  <img src="ICON.png" width="256" height="256" alt="Dota2Forge Q 版主宰图标">
</p>

<h1 align="center">Dota2UID</h1>
<h4 align="center">在聊天里查刀塔战绩、比赛详情和英雄出装</h4>

<p align="center">GsCore 扩展 · Dota2Forge 共享核心 · Python 3.12+</p>

[安装文档](INSTALL.md) · [截图清单](https://github.com/HBLADEH/Dota2Forge/blob/7e650a2fb9a2db9c242c260a7d72ac11424c1989/docs/cookbook/plugin-showcase.md) · [Dota2Forge](https://github.com/HBLADEH/Dota2Forge/blob/7e650a2fb9a2db9c242c260a7d72ac11424c1989/README.md) · [反馈问题](https://github.com/HBLADEH/Dota2Forge/issues)

> 发行版本：`0.1.0a9` · [目标分发仓库](https://github.com/HBLADEH/Dota2UID)。由主仓同一源码生成。

比赛分析新版提供1600px宽的全局总览和两队详情，显示STRATZ IMP、表现突出/偏弱名单与统计依据、团队优势曲线、完整指标和背包/中立装备。装备空白槽不再写占位文字，缺失仍不补零。[验收与发行进度](https://github.com/HBLADEH/Dota2Forge/blob/7e650a2fb9a2db9c242c260a7d72ac11424c1989/.agents/tasks/active/2026-10-09-match-analysis-report.md)；更新到匹配运行库后须完整冷启动，真实聊天效果待用户复测。

## 丨安装提醒

> [!IMPORTANT]
> 这是 [GsCore](https://github.com/Genshin-bots/gsuid_core) 的扩展，安装到 GsCore 宿主。
> 当前为 **M0 预发行，尚未上架商店**；[收录申请PR #40](https://github.com/Genshin-bots/GenshinUID-docs/pull/40)待审核。源码目录与独立分发目录用途不同；本分发采用随包运行库，安装与恢复采用下述流程。

已有 QQ 单会话基础查询和图片验收记录。2026-10-05 本机已升级 `0.1.0a2`，现行 `do` 前缀、段位预估 MMR 与英雄出装已部署，冷启动 `ready/image`，[部署证据](https://github.com/HBLADEH/Dota2Forge/blob/7e650a2fb9a2db9c242c260a7d72ac11424c1989/.agents/artifacts/gscore-current-deployment-v1/README.md)。本轮尚无客户端连接，新功能聊天待验收；下方共用此前 AstrBot 的出装图展示共享卡片。订阅默认关闭，当前实例保留原开关，真实推送仍待验收。

2026-10-08已公开[随包a6](https://github.com/HBLADEH/Dota2UID/releases/tag/v0.1.0a6)并部署到现行Linux/Docker GsCore。运行库校验及冷启动通过，业务等待首次Token配置；原GsCore源码与全局依赖不变，[发行部署记录](https://github.com/HBLADEH/Dota2Forge/blob/7e650a2fb9a2db9c242c260a7d72ac11424c1989/.agents/artifacts/dota2uid-bundled-release-v1/README.md)。真实QQ新入口仍待验收。

随包 a7 已公开，增加[后台插件配置](https://github.com/HBLADEH/Dota2Forge/blob/7e650a2fb9a2db9c242c260a7d72ac11424c1989/docs/cookbook/gscore-configuration.md)；Token、素材与订阅可通过宿主参数页设置，旧 TOML 导入后保留。Assets a1 默认 image/auto 首次后台准备，完整快照无需联网；自定义 illustration_path 不覆盖，可设 manual/off。

a8 随包 Core a5 修复比赛查询对赛前购买时间的误判，负时间按原值保留；`do比赛 9035146588` 的只读复测通过。主仓修复与 [v0.1.0a8 Release](https://github.com/HBLADEH/Dota2UID/releases/tag/v0.1.0a8) 已公开；[修复证据](https://github.com/HBLADEH/Dota2Forge/blob/7e650a2fb9a2db9c242c260a7d72ac11424c1989/.agents/artifacts/stratz-match-detail-response-v1/README.md)与[发行任务](https://github.com/HBLADEH/Dota2Forge/blob/7e650a2fb9a2db9c242c260a7d72ac11424c1989/.agents/tasks/active/2026-10-09-stratz-purchase-release.md)区分代码验证、公开发行和真机测试。更新项目运行库后须完整重启 GsCore，不能只热重载。

bundled 分发随仓库提供匹配项目运行库，缺核心时保留 `do帮助` 文字提示及主人权限的 `do安装核心` / `do核心状态`；安装不写宿主全局环境，修复后冷启动启用。宿主 HTTPX/Pillow 须兼容，步骤见[随包安装指南](INSTALL.md)。下述步骤仅适用于本 bundled 分发；旧 a4 请使用旧版公开安装指南。

## 丨安装与首次配置

1. 通过 GsCore 的 URL 安装功能添加本分发仓库，然后完整重启宿主。仓库携带匹配的四个项目运行包，启动时校验并准备插件专用运行目录，不需要先安装本项目 PyPI 包。
2. 用主人身份发送 `do核心状态` 查看准备和加载结果。缺包或校验失败时发送 `do安装核心`，按提示完成恢复后完整重启宿主。恢复只使用清单固定版本与 SHA256，不接受聊天 URL、版本或 pip 参数。
3. 在后台 **插件配置 → Dota2UID → 插件参数配置** 填写 STRATZ Token 和独立 `namespace`，点击确认修改。主人发送 `do停用` 确认关闭后，再重载当前插件。Token 不发送到聊天。

`do帮助` / `do菜单` 在运行库未就绪时返回文字提示；配置未完成单独显示。HTTPX、Pillow 继续使用宿主兼容版本，第三方冲突须按 [安装指南](INSTALL.md)维护。运行中的安装或修复只准备新运行库，激活需要冷启动；已有绑定和配置保留。详细安装、更新与回退步骤见同一指南。

独立分发目录与 ZIP 由[发行生成器](https://github.com/HBLADEH/Dota2Forge/blob/7e650a2fb9a2db9c242c260a7d72ac11424c1989/docs/cookbook/plugin-release.md)生成。这是随包预发行分发；生成器只准备分发文件，生成动作本身不代表公开发布。

## 丨快速开始

```text
do菜单
do绑定 <Dota账号ID或SteamID64>
do查询
do战绩 20
do战绩 第3页
do比赛 第1场
do主宰出装
```

`<…>` 表示替换为自己的值；方括号表示可省略。每个身份只绑定一个账号；显式查询其他账号不改变绑定，绑定也不证明账号所有权。

## 丨指令列表

| 指令 | 功能 |
| --- | --- |
| `do素材状态` / `do下载素材` / `do更新素材` | 查看素材进度；下载、更新仅主人 |
| `do核心状态` / `do安装核心` | 查看运行库状态 / 主人准备或恢复运行库 |
| `do菜单` / `do帮助` | 查看帮助图片 |
| `do绑定 <ID>` / `do改绑 <ID>` | 绑定自己 / 显式替换绑定 |
| `do账号` / `do解绑` | 查看绑定 / 解绑 |
| `do查询 [ID]` | 玩家概况、段位与预估 MMR |
| `do战绩 [条数]` | 自己的近期比赛，默认 10，范围 1–100 |
| `do战绩 <ID> <条数>` | 查询指定账号 |
| `do战绩 第N页` | 读取最后一次有效战绩的分页 |
| `do比赛 <比赛ID>` / `do比赛 第N场` | 直接查询单局 / 选择列表绝对序号 |
| `do主宰出装` / `doAM出装` / `do出装 Shadow Fiend` | 无需绑定的英雄热门出装 |
| `do停用` | 仅宿主主人权限 0；关闭运行资源 |

账号 ID 接受规范数字形式，不接受 URL、vanity 或 @他人。比赛 ID 与账号 ID 是不同参数。战绩每页五场，最多先发两页；更多页要显式取页。列表仅在本会话完整发送后保存十分钟，改绑、解绑、停用和重载会清除它。

## 丨功能展示

### 帮助与账号绑定

`do菜单` 展示入口；`do绑定 <ID>` 后用 `do账号` 核对。**待实机截图：菜单、绑定成功与账号卡。**

### 玩家与近期战绩

`do查询` 展示来源、段位和预估 MMR；`do战绩 20` 配合 `do战绩 第3页` 查看更多比赛。**待实机截图：玩家卡、战绩第 1 / 2 页及取页结果。**

### 单局详情

`do比赛 第1场` 或直接传比赛 ID，按阵营显示英雄、装备与统计；未知字段保留说明。**待实机截图：命令及天辉 / 夜魇两张详情卡。**

### 英雄热门出装

`do主宰出装` 展示 OpenDota 职业比赛物品购买统计，按出门、前期、中期、后期分组。热门不代表最优出装或购买顺序。

![主宰热门出装共享卡片（来自 AstrBot）](screenshots/hero-items.png)

按用户要求复用此前 AstrBot 实机原图；两端消费同一 Renderer，用于展示共享卡片样式。图片未包含命令输入，不构成 GsCore 聊天收发或指令捕获验收；[来源与范围](https://github.com/HBLADEH/Dota2Forge/blob/7e650a2fb9a2db9c242c260a7d72ac11424c1989/docs/assets/screenshots/README.md)。其余截图文件名、画面内容与脱敏步骤见[截图清单](https://github.com/HBLADEH/Dota2Forge/blob/7e650a2fb9a2db9c242c260a7d72ac11424c1989/docs/cookbook/plugin-showcase.md)。

## 丨数据与使用说明

- 玩家和比赛默认来自 STRATZ；出装来自 OpenDota。卡片保留来源、抓取时间和字段缺失状态，错误不会伪装成无战绩。
- MMR 是根据段位换算的区间或下界，**不是精确天梯分**；未定级或未知段位不估算。
- 默认图片回复，可用 `reply_mode = "text"` 切换文字。绘制失败回退同次数据的文字；发送失败不自动重发。
- 英雄、装备和段位插图需要[显式配置本地素材](https://github.com/HBLADEH/Dota2Forge/blob/7e650a2fb9a2db9c242c260a7d72ac11424c1989/docs/cookbook/illustrations.md)；缺图仍可用占位卡片，回复时不下载资源。
- 订阅玩家、比赛、段位与日报见[订阅指南](https://github.com/HBLADEH/Dota2Forge/blob/7e650a2fb9a2db9c242c260a7d72ac11424c1989/docs/cookbook/subscriptions.md)。默认关闭，群订阅需 Bot 管理员；两端同时部署要明确推送归属。

英雄攻略、AI Tool、IMP 和 Deploy 尚未实现。其他平台、多账号及当前版本完整实机边界仍需单独验收。

## 丨常见问题

**提示未配置？** 检查本机 Token 和 namespace，配置合法后停用 / 重载；不要把 Token 发给 Bot。

**找不到第 N 场？** 先在同一会话完整查询战绩；超时或重载后重新查询，也可直接用比赛 ID。

**没有图片或插图？** 检查回复模式与素材路径；来源错误和缺图是不同状态，按回复提示处理。

**如何更新或卸载？** 先按[生命周期步骤](INSTALL.md)关闭资源。卸载默认保留专用数据；不要直接删除目录来替代停用。

## 丨致谢与许可

README 结构参考 [GenshinUID](https://github.com/KimigaiiWuyi/GenshinUID)；图标呈现参考 [NTEUID](https://github.com/tyql688/NTEUID)，主宰图案为本项目独立生成的同人插画。感谢 GsCore、STRATZ 和 OpenDota。

代码采用 [MIT](LICENSE)。Dota 2、主宰及相关角色权利属于 Valve；图标不是官方标识。第三方素材和字体遵循各自许可，详见[素材说明](https://github.com/HBLADEH/Dota2Forge/blob/7e650a2fb9a2db9c242c260a7d72ac11424c1989/docs/cookbook/illustrations.md)。

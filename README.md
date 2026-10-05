<p align="center">
  <img src="ICON.png" width="256" height="256" alt="Dota2Forge Q 版主宰图标">
</p>

<h1 align="center">Dota2UID</h1>
<h4 align="center">将 Dota 2 数据锻造成可读的战绩与图片战报</h4>

<p align="center">GsCore 扩展 · Dota2Forge 共享核心 · Python 3.12+</p>

[安装文档](INSTALL.md) · [截图清单](INSTALL.md) · [Dota2Forge](https://github.com/HBLADEH/Dota2Forge/blob/main/README.md) · [反馈问题](https://github.com/HBLADEH/Dota2Forge/issues)

> 发行版本：`0.1.0a3` · [目标分发仓库](https://github.com/HBLADEH/Dota2UID)。由主仓同一源码生成。

## 丨安装提醒

> [!IMPORTANT]
> 这是 [GsCore](https://github.com/Genshin-bots/gsuid_core) 的扩展，安装到 GsCore 宿主。
> 当前为 **M0 预发行，尚未上架商店**；收录待申请与审核。源码目录与独立分发目录用途不同；公开运行包安装采用下述停机与冷启动流程。

已有 QQ 单会话基础查询和图片验收记录。2026-10-05 本机已升级 `0.1.0a2`，现行 `do` 前缀、段位预估 MMR 与英雄出装已部署，冷启动 `ready/image`，[部署证据](INSTALL.md)。本轮尚无客户端连接，新功能聊天待验收；下方共用此前 AstrBot 的出装图展示共享卡片。订阅默认关闭，当前实例保留原开关，真实推送仍待验收。

## 丨安装与首次配置

1. 停止 GsCore；已有插件实例先以主人权限执行 `do停用`，确认资源关闭再退出宿主。
2. 在 **GsCore 根目录**克隆分发仓库并安装匹配的公开运行包，Windows示例：

   ```sh
   git clone https://github.com/HBLADEH/Dota2UID.git gsuid_core/plugins/Dota2UID
   .venv/Scripts/python.exe gsuid_core/plugins/Dota2UID/install_runtime.py --host-python .venv/Scripts/python.exe
   ```

3. 冷启动宿主；首次在 `data/Dota2UID/config.toml` 创建空配置，填写 `stratz_token` 与独立 `namespace` 后重新加载。配置项以根 `config.example.toml` 为准。Token 只填本机配置，不发送到聊天；完整步骤见[公开安装指南](INSTALL.md)。

合法配置但 Token 为空时显示 `awaiting_config`，填写后需重新加载；非法配置会明确失败。已有实例先由宿主主人发送 `do停用`，确认关闭后再重载。共享库升级要退出宿主、安装匹配 wheel，再冷启动。

独立分发目录与 ZIP 由[发行生成器](INSTALL.md)生成。三个运行包来自GitHub Releases，安装器校验固定版本与SHA256；共享库更新后必须冷启动。当前宿主热安装遗漏依赖队列执行，直接聊天安装可能先提示缺包，按上面的公开安装流程处理。

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

按用户要求复用此前 AstrBot 实机原图；两端消费同一 Renderer，用于展示共享卡片样式。图片未包含命令输入，不构成 GsCore 聊天收发或指令捕获验收；[来源与范围](INSTALL.md)。其余截图文件名、画面内容与脱敏步骤见[截图清单](INSTALL.md)。

## 丨数据与使用说明

- 玩家和比赛默认来自 STRATZ；出装来自 OpenDota。卡片保留来源、抓取时间和字段缺失状态，错误不会伪装成无战绩。
- MMR 是根据段位换算的区间或下界，**不是精确天梯分**；未定级或未知段位不估算。
- 默认图片回复，可用 `reply_mode = "text"` 切换文字。绘制失败回退同次数据的文字；发送失败不自动重发。
- 英雄、装备和段位插图需要[显式配置本地素材](INSTALL.md)；缺图仍可用占位卡片，回复时不下载资源。
- 订阅玩家、比赛、段位与日报见[订阅指南](INSTALL.md)。默认关闭，群订阅需 Bot 管理员；两端同时部署要明确推送归属。

英雄攻略、AI Tool、IMP 和 Deploy 尚未实现。其他平台、多账号及当前版本完整实机边界仍需单独验收。

## 丨常见问题

**提示未配置？** 检查本机 Token 和 namespace，配置合法后停用 / 重载；不要把 Token 发给 Bot。

**找不到第 N 场？** 先在同一会话完整查询战绩；超时或重载后重新查询，也可直接用比赛 ID。

**没有图片或插图？** 检查回复模式与素材路径；来源错误和缺图是不同状态，按回复提示处理。

**如何更新或卸载？** 先按[生命周期步骤](INSTALL.md)关闭资源。卸载默认保留专用数据；不要直接删除目录来替代停用。

## 丨致谢与许可

README 结构参考 [GenshinUID](https://github.com/KimigaiiWuyi/GenshinUID)；图标呈现参考 [NTEUID](https://github.com/tyql688/NTEUID)，主宰图案为本项目独立生成的同人插画。感谢 GsCore、STRATZ 和 OpenDota。

代码采用 [MIT](LICENSE)。Dota 2、主宰及相关角色权利属于 Valve；图标不是官方标识。第三方素材和字体遵循各自许可，详见[素材说明](INSTALL.md)。

# Dota2UID 随包运行库安装

本页用于 **0.1.0a7 bundled 预发行分发**，发行状态及下载见 [Dota2UID Releases](https://github.com/HBLADEH/Dota2UID/releases)。旧a4继续使用[旧安装流程](https://github.com/HBLADEH/Dota2Forge/blob/3a2f6d0c8c3739d7a8da38cc4e116dc94d327023/docs/cookbook/gscore-public-install.md)。要求GsCore宿主Python 3.12+，宿主源码无需修改。

## 安装与首次配置

新分发仓库随包提供Core、Renderer、Assets与Dota2UID的匹配wheel。按宿主原有URL安装方式取得该版本；首启只使用本地wheel校验并准备运行目录，不向PyPI安装这些项目包，不触碰全局site-packages。

HTTPX/Pillow继续使用宿主已经安装的兼容版本。根依赖声明只包含这些第三方要求，自动安装仍受宿主开关与冷启动路径控制。版本不兼容时保留管理入口并明确提示；先退出宿主，使用其实际Python维护第三方依赖，再冷启动。聊天安装核心不会升级宿主Pillow。

后台打开 **插件配置 → Dota2UID → 插件参数配置**，填写 STRATZ Token 和独立 namespace，点击确认修改。合法空 Token 为 awaiting_config；保存后先 do停用，确认关闭再重载或冷启动。参数包括密码输入、素材、订阅与平台映射，运行库不可用时仍可配置。

首次原生 JSON 不存在时导入旧 TOML，保留原文件、数据库与素材目录；之后以后台 JSON 为准。旧 a6 安装仍需填写 data/Dota2UID/config.toml，不能只更新入口混用旧 wheel。来源优先级、隐私和回退见[后台配置](https://github.com/HBLADEH/Dota2Forge/blob/3a2f6d0c8c3739d7a8da38cc4e116dc94d327023/docs/cookbook/gscore-configuration.md)。

## 安装与诊断指令

| 指令 | 行为 |
| --- | --- |
| do核心状态 | 仅宿主主人，显示运行库准备、失败、待重启与业务配置状态 |
| do安装核心 | 仅宿主主人，准备当前分发清单锁定的运行库；完成后冷启动启用 |
| do帮助 / do菜单 | 核心不可用时给文字安装提示；可用时转交正常帮助 |
| do停用 | 主人关闭业务客户端、调度与核心准备任务，再操作宿主 |

管理指令不接受URL、版本、路径、额外参数或代办@；权限0才可安装，超级用户、群主和群管理员不等于宿主主人。没有STRATZ Token也可以安装运行库。安装时先用随包wheel，缺失/损坏才从本版本固定GitHub Releases地址取回，SHA256失败不加载；自行生成的候选需先发布对应资产才有公开恢复入口。

重复安装只复用完整匹配目录；并发准备只运行一项，重复指令返回当前状态。网络失败、摘要错误、磁盘写入失败和第三方冲突会分别给出状态，不能把下载成功等同业务ready。

## 数据与更新

项目包准备于data/Dota2UID/runtime下按清单摘要与代际划分的独立目录；只有完整校验和离线导入/字体资源检查通过后才发布指针。失败保留原目录，不删除用户数据库。私有路径仍与宿主处于同一进程，遇到已加载的其他版本或未知来源模块时拒绝切换，要求完整重启。

更新前备份data/Dota2UID，先do停用并退出GsCore，再按宿主原有方式更新分发目录，最后冷启动。聊天修复只准备新运行库，下一次冷启动才激活；不要用热重载替代更新核心后的重启。回退须恢复匹配分发与兼容数据备份，不能将新schema数据库盲目交给旧版。

卸载前先停用，再由宿主卸载插件并重启；保留data/Dota2UID以便恢复。运行库和共享第三方依赖不混在一起，不删除其他插件使用的包。普通业务命令与数据来源继续遵守[Dota2UID说明](https://github.com/HBLADEH/Dota2Forge/blob/3a2f6d0c8c3739d7a8da38cc4e116dc94d327023/adapters/Dota2UID/README.md)。

## 验证边界

a7源码通过1930项统一禁网检查、五包构建与双端分发检查。真实GsCore隔离副本验证了原生参数API鉴权、保存、停用/重载、旧配置保留及日志归档不含合成Token；使用既有测试解释器，不冒充全新SDK环境。公开资产与服务更新见[后台配置验收](https://github.com/HBLADEH/Dota2Forge/blob/3a2f6d0c8c3739d7a8da38cc4e116dc94d327023/.agents/artifacts/dota2uid-webconsole-config-v1/README.md)，不等同真实浏览器点击或QQ递送。

2026-10-08现行Linux/Docker GsCore0.11.0、SDK7f1bee79、Python3.12.12已备份并冷启动a6，四个私有运行包及完整清单可用；配置Token为空，业务awaiting_config，匿名管理接口401。原SDK、全局依赖、聊天路由与定时更新设置保留。真实QQ新命令、已登录管理API及其他SDK版本待验收；详见[发行部署证据](https://github.com/HBLADEH/Dota2Forge/blob/3a2f6d0c8c3739d7a8da38cc4e116dc94d327023/.agents/artifacts/dota2uid-bundled-release-v1/README.md)。公开预发行不代表商店已收录。

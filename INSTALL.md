# Dota2UID 随包运行库安装

本页用于 **0.1.0a6 bundled 预发行分发**，公开下载见 [Dota2UID Releases](https://github.com/HBLADEH/Dota2UID/releases)。旧a4继续使用[旧安装流程](https://github.com/HBLADEH/Dota2Forge/blob/7efd87fbaacf612d2b8581866327923d2a52a771/docs/cookbook/gscore-public-install.md)。要求GsCore宿主Python 3.12+，源码和原有宿主逻辑无需修改。

## 安装与首次配置

新分发仓库随包提供Core、Renderer、Assets与Dota2UID的匹配wheel。按宿主原有URL安装方式取得该版本；首启只使用本地wheel校验并准备运行目录，不向PyPI安装这些项目包，不触碰全局site-packages。

HTTPX/Pillow继续使用宿主已经安装的兼容版本。根依赖声明只包含这些第三方要求，自动安装仍受宿主开关与冷启动路径控制。版本不兼容时保留管理入口并明确提示；先退出宿主，使用其实际Python维护第三方依赖，再冷启动。聊天安装核心不会升级宿主Pillow。

运行库就绪后首次创建data/Dota2UID/config.toml，空Token为awaiting_config。填写本机stratz_token和独立namespace，不把Token发到聊天。配置保存后先do停用，确认关闭再重载或冷启动。既有配置、绑定/订阅数据库及素材目录不覆盖。

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

卸载前先停用，再由宿主卸载插件并重启；保留data/Dota2UID以便恢复。运行库和共享第三方依赖不混在一起，不删除其他插件使用的包。普通业务命令与数据来源继续遵守[Dota2UID说明](https://github.com/HBLADEH/Dota2Forge/blob/7efd87fbaacf612d2b8581866327923d2a52a771/adapters/Dota2UID/README.md)。

## 验证边界

源码已通过统一禁网测试、双端分发检查与Windows实际SDK隔离生命周期验证；[实施任务](https://github.com/HBLADEH/Dota2Forge/blob/7efd87fbaacf612d2b8581866327923d2a52a771/.agents/tasks/done/2026-10-08-dota2uid-bundled-bootstrap.md)列出1740项测试、数据保留与联调边界。SDK-free测试不能证明宿主权限、热加载、QQ递送或Linux/Docker兼容；后续公开下载与部署事实见[发行部署证据](https://github.com/HBLADEH/Dota2Forge/blob/7efd87fbaacf612d2b8581866327923d2a52a771/.agents/artifacts/dota2uid-bundled-release-v1/README.md)。生成、构建和本地验证不代表商店已收录。

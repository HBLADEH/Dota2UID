# Dota2UID 公开运行包安装

Dota2UID 为 GsCore 扩展，要求宿主 Python 3.12+。当前为 M0 预发行，商店收录以官方索引为准；源码开发与独立分发目录用途不同。以下命令在包含 .venv 的 GsCore 根目录执行，适用于 Windows；其他平台需要补充验收。

## 首次安装与配置

已有实例先执行主人权限0的 `do停用`，确认关闭后退出 GsCore。首次安装也先停止宿主，避免安装 Pillow 时 DLL 被运行进程占用。

```powershell
git clone https://github.com/HBLADEH/Dota2UID.git gsuid_core/plugins/Dota2UID
.venv/Scripts/python.exe gsuid_core/plugins/Dota2UID/install_runtime.py --host-python .venv/Scripts/python.exe
```

安装器从该仓库 GitHub Releases 取得与 release.json 匹配的三个 wheel，校验 SHA256，通过宿主 Python 的 pip 安装；Pillow/HTTPX 等第三方依赖从包索引取得。没有 pip 时先使用解释器自带 ensurepip。安装时保留其他宿主包对 Pillow 的有效约束，安装后运行 pip check，依赖冲突返回失败。需要网络，不要求本地 Dota2Forge workspace、私有索引或自行构建 wheel。失败时按错误处理，不跳过版本检查强行加载。

随后正常冷启动 GsCore。首次创建 data/Dota2UID/config.toml，合法但空 Token 为 awaiting_config，不创建业务客户端或调度；非法字段仍失败。填写本机 stratz_token 与独立 namespace，Token 不发到聊天。完整配置项以仓库根 config.example.toml 为准；配置位置在宿主 data/Dota2UID，不能覆盖已存在配置。

配置后需重新加载：已有实例先停用，再重载或冷启动。默认图片回复；reply_mode="text" 可切换文字。namespace、可信平台映射和机器人身份确定后再绑定；ID接受数字Dota账号ID/SteamID64，不接受URL、vanity或@他人。

## 宿主安装与升级限制

当前 GsCore 87c06f1 的商店热重载会收集缺失依赖，但未在导入前执行安装。因此直接点击安装可能提示依赖缺失；按上面的停止宿主/公开运行包安装/冷启动步骤完成安装。运行库版本锁定，不接受静默混用旧包。

0.1.0a3 将 Renderer 的 Pillow 范围设为 >=11.3,<13，以兼容该宿主 fastembed 的 <12 要求。0.1.0a2 的公开包要求 Pillow >=12.3，与该宿主冲突，不用于此安装流程；已安装 a2 时使用 a3 清单重装并确认 pip check 通过。

更新前先停用并退出宿主，备份 data/Dota2UID 中的配置及绑定/订阅库，再更新分发目录并运行同一安装命令，最后冷启动。新版本下载地址与摘要随分发清单生成。不要在运行中的进程安装新库后只看版本元数据判断升级成功。

卸载前确认客户端关闭，再用宿主卸载发现目录，重启清除残余注册。保留 data/Dota2UID 以便恢复；共享运行包可以保留，不删除其他插件使用的库。回退须恢复匹配的分发目录和三包，重新冷启动；跨schema回退需兼容数据备份，不能盲目把新库写出的数据库交给旧包。

## 命令与资源

按插件README使用 do菜单、do绑定、do查询、do战绩、do比赛、do主宰出装。战绩每页五场，最多先发两页，更多用do战绩 第N页；比赛第N场使用同一会话十分钟内最后完整发送的列表。MMR仅由段位估算区间/下界，不是精确天梯分。玩家/比赛来自STRATZ，出装来自OpenDota，来源失败不会伪装无数据。

图片由同一Renderer生成；本地素材可通过illustration_path指定目录，缺图使用占位卡片，不在回复时下载。字体与运行资源由Renderer wheel携带；Valve角色/装备画面遵守其权利，MIT不覆盖第三方美术。README出装截图来自此前AstrBot实机，用于展示共享样式，不证明GsCore指令或QQ上传通过。

订阅默认关闭，真实推送尚待验证。开启前设置独立namespace和推送归属，群订阅需Bot管理员，不让两端重复调度。英雄攻略、AI Tool、IMP和Deploy尚未实现，不作为已提供命令。

## 验证范围

0.1.0a3已通过Windows/GsCore0.11.0/87c06f1/Python3.13.2隔离SDK公开安装、升级、冷加载恢复与原生卸载验收；配置及两库摘要保持。Provider与出站分别为合成HTTP和内存帧采集，未启动HTTP/WS监听服务，不证明真实QQ递送。真实QQ新指令验收由用户后续进行，详见发行说明。既有本机手动0.1.0a1→0.1.0a2升级和历史单会话图片证据不覆盖所有平台、新装方式或当前版本全部行为。

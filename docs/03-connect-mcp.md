# 第三步：连上 Wi-Fi 音箱，给 AI 播报与点歌

前提：已按上一篇完成固件与 SSH 核验。本篇不会执行刷机，也不会监听麦克风。

## 1. 设置专用 SSH 别名

将 `examples/ssh-config.example` 的 Host 块合并进常开电脑 `~/.ssh/config`，替换音箱 IP 和私钥路径，不覆盖其它 Host。示例名固定 `oh2p`，程序只调用这个别名。

首次主机指纹要通过你已核实的设备连接/管理途径对照，再写入专用 `~/.ssh/oh2p-known_hosts`。`ssh-keyscan` 只能收集公钥，不能独立证明它就是你的设备。不要用 StrictHostKeyChecking=no 跳过。

```bash
chmod 600 ~/.ssh/config ~/.ssh/oh2p-management-rsa ~/.ssh/oh2p-known_hosts
ssh oh2p 'cat /etc/openwrt_release; cat /proc/mounts'
ssh -o BatchMode=yes oh2p 'true'
```

末条无交互且退出 0 才能交给后台服务。旧固件可能只支持 ssh-rsa，例外只放这个 Host，不降低全局 SSH 设置。

## 2. 安装示例

```bash
cd ~
git clone https://github.com/AZHi-xinxin/xiaomi-oh2p-mcp-tutorial.git
cd xiaomi-oh2p-mcp-tutorial
sudo apt-get install python3-venv ffmpeg libspeexdsp1
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
install -d -m 700 ~/.config/oh2p-mcp
install -m 600 examples/voice-secrets.example.json ~/.config/oh2p-mcp/voice-secrets.json
```

编辑私有 JSON：填你自己的 ElevenLabs API Key、已授权 voice ID 和真实 model ID。不能把手机里的自定义显示名当成服务商模型 ID；以控制台/API 返回为准。模型与声音必须支持示例的 `/v1/text-to-speech/{voiceId}` 和参数，见 [ElevenLabs API](https://elevenlabs.io/docs/api-reference/text-to-speech/convert)。

`mcp_token` 与 TTS key 不同，自己在本机生成：

```bash
python3 -c 'import secrets; print(secrets.token_urlsafe(32))'
```

把结果填入配置和 Orbis 原生认证栏，不发聊天。已有配置时不要重复执行 install 覆盖。

## 3. 启动与手机连接

```bash
cd ~/xiaomi-oh2p-mcp-tutorial
.venv/bin/python src/server.py
```

仅本机 `127.0.0.1:8770/mcp`，未带密钥返回 401。手机和主机使用同一 Tailscale 私网；先检查未占用的端口，再添加独立 Serve：

```bash
tailscale serve status
tailscale serve --bg --https=18770 http://127.0.0.1:8770
```

Orbis 设置 → MCP → 新增；URL 为命令显示的 `https://YOUR_HOST.YOUR_TAILNET.ts.net:18770/mcp`，Streamable HTTP，`Authorization: Bearer 你的mcp_token`。开启并给目标助手选用，刷新工具。不要开启 Funnel。

这份示例是独立 MCP；已有 HomeMCP 的开发者也可用 `music_control.register(mcp)` 注册音乐、参照 server.py 注册播报。保留原鉴权，勿再让原 `speaker_say` 与新定义重名。

## 4. 分项验收

先查状态，不播放：

```json
{"action":"status"}
```

调用的是 `speaker_music`。得到状态后，再明确测试：

```json
{"action":"play","title":"我怀念的","artist":"孙燕姿"}
```

接着分别 `pause`、`resume`；`next` 需要可用播放列表。曲库由原厂账号决定，约一分钟可能是试听。代码只核验播放状态及音频 ID，不把命令接受等同精确歌名命中；真人听到的歌曲仍需确认。

然后让 AI 调 `speaker_say`，说一段短测试文字。文字发给 ElevenLabs 合成，经常开主机转为 **48kHz、双声道、S16_LE** 后，通过 SSH `aplay -D Playback` 播放。播放前暂停原曲库；播放结束不擅自恢复音乐。

出错或超时可能已播放一部分，禁止自动重复播报。固定动作使用结构化参数，不能把模型任意 shell 或整段家电指令交给音乐接口。

## 5. 开机自启

确认前台通过后 Ctrl+C，再安装用户服务：

```bash
mkdir -p ~/.config/systemd/user
cp examples/oh2p-mcp.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now oh2p-mcp
systemctl --user status oh2p-mcp
```

源码不在用户主目录时先改单元路径。若需登出后持续运行，管理员开启 `loginctl enable-linger 你的用户名`；电脑仍须联网、不睡眠。停用用 `systemctl --user disable --now oh2p-mcp`，不需要重刷音箱。

# 第四步：自定义唤醒与语音路线（进阶实现说明）

前三篇已经能从聊天里控制音箱。这一篇解释实际部署过的语音服务；**仓库提供 AEC 模块，但没有打包私人常驻监听器和全部回复缓存**。要照此组装，需要增加唤醒/收音状态机、事件绑定和你自己的设备白名单。不要把 MCP 启动成功当成“自定义唤醒已经装好”。

## 先选路线，再决定数据去哪

| 环节 | 我们的实测实现 | 是否出网 |
| --- | --- | --- |
| 待机关键词 | sherpa-onnx KWS，在常开主机内存处理 | 不发云端 |
| 快捷家电指令转写 | SenseVoice int8，主机本地 | 不发云端 |
| 自由说法理解 | 可选云端短文本解析，随后本地结构校验 | 只发当前指令文字、有限的一次补充/近期设备指代 |
| 回到原 Orbis 对话 | 另一唤醒分支，实测用了唤醒后短片段云 ASR | 短音频发 ASR；识别文字发原绑定聊天 |
| 个性化声音 | ElevenLabs TTS，可将固定回复预合成为本地缓存 | 播报文字发 TTS；缓存播放不再请求 |
| 原厂音乐 | 音箱自带曲库 | 仍用原厂服务和账号 |

“快捷路线只上传指令文字”不适用于另一条已经选择云 ASR 的聊天路线。部署前让人类分别选择；更换 ASR 不可偷偷把本地录音全上传。TTS 合成也是出网，不应写成全程离线。

## 音频格式：最容易踩的坑

实测 OH2P 1.62.2 的 `Capture` 输入为 16kHz、S32_LE、四通道；前三路是麦克风，第四路是播放参考。最终版只取第一路麦克风和第四路参考用于本地回声抵消。不是所有设备/固件都保证此映射。

设备端实际采集形式：

```text
arecord -q -D Capture -t raw -f S32_LE -r 16000 -c 4
```

PCM 经既有 SSH 传到主机内存。仅在你已决定启用监听后运行；停止时 terminate 子进程并回收，断线后清掉旧帧，不把几分钟前的声音当成新指令。

`src/speaker_aec.py` 的 `SpeechCapture.process(raw)` 接收每帧 10ms（160 个采样点 × 4 通道 × 4 字节）的整数倍，返回单声道 S16_LE。需安装 `libspeexdsp1` 和 NumPy；使用完调用 `close()`。

我们早期把麦克风右移 8 位并放大，大音乐时约 42% 样本削顶，用户必须贴近才唤醒。最终先保留余量、对麦克风和播放参考分别处理，再做 SpeexDSP AEC 和限幅增益。真人已确认原位置可唤醒并暂停音乐。这不是简单“调大灵敏度”，也不能保证所有歌词均不误唤醒。

## 唤醒与完整识别要分工

[KWS 官方说明](https://k2-fsa.github.io/sherpa/onnx/kws/index.html)用于小词表触发，不适合代替整句话 ASR。唤醒词由用户配置，不内置某个家庭的称呼。关键词文件按所选模型的 tokens 编码，不能将任意中文直接塞进拼音模型文件。

我们实际使用过带 `encoder/decoder/joiner` 三个 int8 ONNX 文件的中文 KWS 模型，模型文件名含 `epoch-12-avg-2-chunk-16-left-64`；下载时按上游模型说明，整套 tokens/三模型须配套。不要只凭文件名下载第三方改包。

完整中文短句用 [SenseVoice 预训练说明](https://k2-fsa.github.io/sherpa/onnx/sense-voice/pretrained.html)的本地模型。对应 Python 初始化形态：

```python
recognizer = sherpa_onnx.OfflineRecognizer.from_sense_voice(
    tokens="YOUR_SENSEVOICE_DIR/tokens.txt",
    model="YOUR_SENSEVOICE_DIR/model.int8.onnx",
    language="zh", use_itn=False, num_threads=2,
)
```

这只是识别器配置，还需自行接入已结束的一段 PCM。不能把连续环境麦克风流一直积在内存里。

## 实测状态机应保留的环节

1. **待机**：只在本地做 KWS，保留有界小队列，不保存环境录音。
2. **唤醒**：按唤醒词选择快捷或原聊天路线；如果音乐在播先暂停。
3. **清掉歌曲预录**：不能把唤醒前歌曲或提示音拼进用户话语。等提示音结束，再接本轮语音。
4. **有界收音**：快捷句最长约 8 秒，一段静音结束；无说话就回待机，不能把空白送到聊天。
5. **识别与意图**：固定明确短句可离线；自由说法用可选文本解析。验证返回 action/设备/数值类型与范围，最多 3 个明确动作。
6. **歧义追问**：只接一次有限时补充，不要求再次唤醒；没有回答就退出。
7. **执行/播报**：先核验设备回执，才能说“已完成”；音箱播放互斥，音乐、提示音与 TTS 不争抢。
8. **回待机**：释放锁/子进程；失败不盲目重复实体动作。

否定、转述、查询、未来条件不能被误当立即操作。语义模型只返回有限动作 JSON，不得生成 shell 或任意 HA 服务路径。最近设备指代可限时保留（实测 90 秒），不上传整段历史聊天。

## 接回 Orbis 的同一个 AI

需要人类在支持事件/哨兵入口的 Orbis 版本中建立并启用来源绑定，把识别文字送往指定助手和会话，而不是新建一个没有历史的“替身”。客户端具体授权界面随版本变化，以该版本内置帮助为准，参见 [Orbis 项目](https://github.com/AZHi-xinxin/Orbis)。

实际事件适配器先读取 `/api/orbis/events/status?source=…`，确认来源有效且绑定助手/会话一致，再 POST `/api/orbis/events`。事件含独立 `event_id`、`source`、识别文字、`wake` 和毫秒时间。超时按原 ID 查询 `/api/orbis/events/receipt`，结果不明不换 ID 重发。密钥只在主机私有文件。

收到 Orbis 事件回执只证明接收；AI 回复成功只证明文本生成。还需实际 `speaker_say` 调用和人类听见，才是语音往返通过。此仓库不附任何用户现有绑定材料。

## 后台运行和验收

开发者将上述监听器实现后，可用单独的 systemd 用户单元运行，配置 `UMask=0077`。监听器启动成功后应持续运行；遇到无法恢复的收音/SSH 错误，释放子进程并以非零状态退出，由 systemd 每 30 秒重启。新进程重新建立收音状态，不重放旧录音、未确认的家电动作或聊天事件。

2026-10-31 的现场发现：监听器连续失败后触发了 systemd 的启动次数限制，进入 `failed`，后续即使音箱 SSH 恢复可达也不会自行重试；原厂语音服务仍然能回应。原始失败触发原因没有完整日志证据，因此不能一概归因为断网。恢复服务并调整重试配置后，维护者已实际确认自定义唤醒恢复。

已经有 `oh2p-voice-listener.service` 的部署，可安装本仓库的重连配置：

```bash
mkdir -p ~/.config/systemd/user/oh2p-voice-listener.service.d
install -m 600 examples/voice-listener-reconnect.conf ~/.config/systemd/user/oh2p-voice-listener.service.d/30-reconnect.conf
systemctl --user daemon-reload
systemctl --user reset-failed oh2p-voice-listener.service
systemctl --user start oh2p-voice-listener.service
systemctl --user show oh2p-voice-listener.service -p ActiveState -p SubState -p MainPID -p NRestarts -p RestartUSec -p StartLimitIntervalUSec
```

若你的监听器用了别的单元名，同步替换目录和命令中的名称。这份 drop-in 设置 `StartLimitIntervalSec=0`、`Restart=on-failure` 和 `RestartSec=30`，取消启动次数限制并留出重连间隔。手动 `systemctl --user stop` 后仍会保持停止；应用正常退出也不会因 `on-failure` 自动重启。持续配置错误会每 30 秒再次失败，应先停止服务、查看日志并修正，再启动。

查看本轮进程的 `active/running`、监听器状态和时间戳后，再实际喊自己的唤醒词验收。`active` 只说明进程存活，不能代替听到回复。本仓库现成完整单元 `oh2p-mcp.service` 仅启动 MCP；上面的 drop-in 用于你自行实现并已安装的监听器，不会凭空安装唤醒服务。

依次验收静室唤醒、完整短句、音乐高潮时唤醒、无语音时不投递、断网/断线退出、重连无旧音频重放、家电否定句不操作、Orbis 回原会话和真实发声。长期误唤醒测试还需持续积累，不能用一轮成功代替。

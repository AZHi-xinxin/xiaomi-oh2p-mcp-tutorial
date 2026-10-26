# 验证记录（2026-10-27）

- 12 项 Python 测试通过：6 项音乐输入/状态/超时不重放、2 项 MCP HTTP 与鉴权、4 项真实 SpeexDSP 合成信号回归。
- HTTP 测试实际走 initialize、tools/list、tools/call；播报调用替换为内存 mock，不会发云请求或播放实物。
- AEC 测试用随机合成信号；本轮相关性约 0.97，不是人类听感评分，也不等于任意房间环境都有效。
- 既有实机的刷写哈希、Wi-Fi、播报/音乐、唤醒及搬回原位验收见文档适用范围。本轮没有重新刷机、录音、播放或更改服务。
- 公开示例从零复装、完整通用唤醒安装器、其它机型与长期误唤醒仍未验收或未提供，不能称为一键全功能产品。

复测：安装 requirements.txt 和系统 libspeexdsp1，仓库根目录运行 `PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -v`。

本次 Python 3.12、MCP Python SDK 1.29.0、NumPy 2.2.6、系统 libspeexdsp.so.1。音箱示例来自既有实测模块，改为通用 SSH 别名和私有配置；不包含任何用户音色、账号、公私钥、音频或聊天绑定。

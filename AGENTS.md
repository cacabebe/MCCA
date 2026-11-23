# MCCA 开发约定

- 后续开发使用 ADB 连接模拟器，查看游戏界面、截图、发送输入和做实机验证。优先使用 `config/config.json` 中 `AdbDevice` 配置的 ADB 路径和设备序列号，发命令时用 `adb -s` 明确指定设备。

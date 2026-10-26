# 第二步：OH2P 固件核验与刷写

这篇记录我们的实际路线和每步判断依据。**不提供无条件执行的刷机脚本**：目标分区必须根据你那台设备的实际读取结果确定。已刷好且能 SSH 的设备跳到下一篇。

## A. 固件与工具来源

先阅读 [Open-XiaoAI 刷机说明](https://github.com/idootop/open-xiaoai/blob/main/docs/flash.md) 和 [补丁构建说明](https://github.com/idootop/open-xiaoai/blob/main/packages/client-patch/README.md)，下载对应 OH2P、对应版本的材料，核对作者公布的校验值。USB 工具从上游链接获取；本仓库不镜像第三方驱动/厂商固件。

我们的机器读出的 system1 文件系统与 1.62.2 原版精确匹配，所以使用同版本补丁。只看到“某个 1.62.2 下载包”还不能证明适合当前槽位。上游页面示例写 system0；本机实测写 system1。**这两种不能混着照抄**。

本次在常开 Ubuntu 主机运行厂商 Linux `update` 工具，Windows 仅作为操作入口；Windows 读者可用上游 `update.exe` 路线。工具参数随版本可能不同，应先查工具帮助，不将 Linux 命令直接套到其它工具。

## B. USB 连接与读取

OH2P 底部 Type-C 接电脑，音箱继续使用自身电源；充电线不能代替数据线。启动阶段的 USB 窗口短，要先准备命令，再给音箱重新通电。先做只读 `identify`，确认识别到正确型号和设备。

Linux 工具的实际只读形式：

```text
./update identify
./update mread store system0 normal READ_LENGTH_HEX system0-readback.bin
./update mread store system1 normal READ_LENGTH_HEX system1-readback.bin
```

`READ_LENGTH_HEX` 不是固定模板值。先读取文件系统头，检查 SquashFS magic、版本、bytes_used；再按核验后的长度读取。长度必须小于已核实的槽位容量。用 `unsquashfs -s` 检查结构、`sha256sum` 核对完整备份，并与同版本原厂 root 文件比较。这种备份是文件系统有效字节，不等于整机、校准数据、个人 data 的全盘备份。

只看到命令返回 success 不代表读到内容。我们遇到 `bulkcmd printenv` 返回成功却不传回环境正文，不能用它声称读出了 boot_part。USB 错误或不完整回读应保留现场，先查连接，不能把剩余部分猜出来。

## C. 个人专用补丁与 SSH

在自己的常开主机生成专用密钥，例如旧版 Dropbear 可用的 RSA 3072：

```bash
umask 077
ssh-keygen -t rsa -b 3072 -f ~/.ssh/oh2p-management-rsa
```

是否使用口令取决于你是否配置 SSH agent；无人值守不应把口令写入脚本。只有 `.pub` 公钥进入你自己的固件，私钥不上传仓库。

我们的实际补丁在上游补丁基础上，离线重新封装并核验了：

- `/etc/dropbear/authorized_keys` 仅自己的公钥，目录 700、文件 600。
- Dropbear 的 PasswordAuth、RootPasswordAuth 关闭，启动参数实际使用 `-s -g`。
- 移除公开默认登录口令的可用性，保留已核实的密钥登录。
- 对重新解包后的文件内容、类型、权限、属主、链接、设备节点做差异核对，仅允许预定的 SSH 变更。

这些是实测配置要求，不是通用于所有固件的文本替换脚本。不会封装时，应按上游文档请熟悉 SquashFS/Dropbear 的人协助，别下载陌生人的“带密钥固件”。已有公钥绑定的别人镜像，即使刷进去了你也没有其私钥。

## D. 写入与启动必须分开核验

确认你的选择后，流程是：保存读回备份 → 增加启动等待 → 仅写目标 system 槽位 → 完整回读验证 → 切到对应 boot 槽位并保存 → 启动。

下面是**本机已核实 system1/boot1 对应关系之后**用过的 Linux 参数形式，不能未经 B、C 两节核对就执行：

```text
./update bulkcmd "setenv bootdelay 15"
./update bulkcmd "saveenv"
./update partition system1 YOUR_VERIFIED_PATCH.squashfs normal
./update mread store system1 normal PATCH_BYTE_LENGTH_HEX written-readback.squashfs
# 精确比较长度和 SHA256，确认一致后再继续
./update bulkcmd "setenv boot_part boot1"
./update bulkcmd "saveenv"
./update bulkcmd "reset"
```

本次没有写 bootloader、tpl、分区表、boot0/boot1 内核或 data，system0 原厂文件系统保留。这里的 boot1 是启动选择；不能理解为又把镜像写进 boot1 内核分区。

曾遇到写入中途 USB 断开：不完整回执不能算成功。后续完整传输成功但 USB 回读仍不稳定，最终利用保留的原厂槽位和独立核验，在 Wi-Fi 启动后读取了完整补丁长度，哈希一致才验收。这个现场补救过程不能推广为“忽略写入失败直接重启”。

## E. Wi-Fi 验证

从常开电脑连接音箱，核验系统版本、`/proc/mounts`、`/proc/mtd` 和 Dropbear 实际参数。根据本机输出确定实际根分区。我们这只 OH2P 是 `/dev/mtdblock5`，不能假定每台设备都相同。

本机补丁恰为 32,059,392 字节（7827 个 4096 字节块），因此当时使用：

```text
dd if=/dev/mtdblock5 bs=4096 count=7827 | sha256sum
```

你必须按自己的补丁长度和根分区计算，最后一个非完整块也必须精确限制长度。比较的是实际读取完整长度的哈希，不是开机成功就结束。不要写 `of=/dev/...`，这里是读取。

## F. 恢复原则

记录自己**未改写且已知能启动**的原厂槽位；回退时才按对应 boot_part 选择并 saveenv。我们的保留槽位是 system0/boot0，和上游示例的回退方向相反。没核对不能一律回 boot0 或 boot1。

恢复尚未在本实例上实际演练，不能保证任何故障都靠切槽解决。USB 正常、固件哈希和来源可信、原厂备份可读、对应槽位仍完整，都是判断依据。

完成后拔 USB，仅保留电源与 Wi-Fi；再验证 SSH 和下一篇的音频功能。不要为了重复验收再刷一次。

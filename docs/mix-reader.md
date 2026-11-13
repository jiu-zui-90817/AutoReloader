# MIX 只读浏览（编辑器）

编辑器支持打开 RA2 / YR 的 **未加密 MIX** 文件进行只读浏览：

```text
文件 → 打开 MIX 文件（只读）…
```

功能：

- 列出 MIX 条目（文件名 / ID / 大小 / 类型）；
- 支持文件名或 ID 搜索；
- 选中条目预览 INI 文本 / CSF 信息 / 二进制头；
- 「提取并打开」提取到 `%LOCALAPPDATA%\AutoReloader\INIEditor\cache\mix_extract\` 后作为单文件打开；
- 「提取到…」另存到指定位置。

**不写回 MIX**。编辑的是临时提取文件，不会修改原 MIX。

## 文件名显示

MIX 只保存文件 CRC，不保存文件名。编辑器会按以下顺序补全：

1. 当前工程目录中的文件名；
2. MIX 自带的 `local mix database.dat`；
3. 常见文件名。

未匹配到的条目显示为：

```text
ID_XXXXXXXX.bin
```

## 加密 MIX

RA2 / YR 的部分 MIX（如 `ra2.mix`、`ra2md.mix`、`language.mix`）是加密的。  
当前版本只支持**未加密 MIX**；打开加密 MIX 会提示先用 XCC Mixer 解包。

这是只读浏览的边界：不会尝试修改或重新打包 MIX。

## 地图热重载

地图不是类型 INI：地形、覆盖物、建筑、单位、触发器和寻路在载入时构建，YR 没有公开的“重载当前地图”接口。AutoReloader 目前只做类型/规则 INI 热重载，不支持运行中替换地图；地图改动需要重新开始/重启。

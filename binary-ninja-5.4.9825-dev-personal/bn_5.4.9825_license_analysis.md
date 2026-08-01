# Binary Ninja 5.4.9825-dev Personal：许可证验证与重签名补丁

## 结果

- 审计 `/Applications/Binary Ninja.app` 的 `5.4.9825-dev_personal` 构建；其核心为 `libbinaryninjacore.1.dylib`（arm64/x86_64）。
- 该构建的付费许可证不是可从公开信息直接计算的序列号：它对许可证主体执行 **RSA-2048 + PKCS#1 v1.5 / SHA-256** 签名校验（Botan 标记：`EMSA3(SHA-256)`）。
- 因此，**没有 Vector 35 私钥就不能为原始二进制制作新许可证**。提取出的只有公钥，不能用于生成签名。
- 实现针对该 exact arm64 构建的“重置内置公钥”补丁：`bn_5_4_9825_rekey.py` 只修改拷贝中的 73 组 `MOVZ/MOVK` 常量，使其接受你自行生成的 RSA-2048 公钥；原安装目录不会被脚本写入。
- 还原并验证 `data` 的额外格式校验：前 `0x100` 字节为随机值，后 `0x18` 字节为使用 `MD5(prefix)` 作 key 的 RC4 密文；明文固定为 `9c2aaa09a4e2252b0ba125db1e1cd272207d97cca8446899`。
- 该版本另有一个独立问题：`expiresEpoch` 被读取并写入运行时到期时间，但未加入签名主体。对已有且签名有效的许可证，仅改该字段不会改变 RSA 校验输入。随附审计器可离线验证这个结论；它不会改动已安装程序或默认许可证路径。

## 已复现验证

对隔离的 dylib 拷贝执行以下两组测试（均未修改 `/Applications/Binary Ninja.app`）：

| core 拷贝 | 输入 | `BNInitUI(0xf20f858c86312a9e)` | `BNIsLicenseValidated()` |
|---|---|---:|---:|
| 重置公钥 |  `license.dat` | `true` | `true` |
| 重置为新生成测试公钥 | 本脚本生成的单元素数组许可证 | `true` | `true` |
| 同上 | 仅篡改 `email`，不重签名 | `false` | `false` |

这证明当前 5.4.9825 arm64 路径同时执行了：JSON 数组解析、签名主体构造、RSA 校验、`data` 的 RC4 格式检查以及状态置位。

## 验证流程

1. 初始化优先读取环境变量 `BN_LICENSE`；若无则读取 `license.dat`。JSON 顶层为许可证对象数组。
2. 逐项解析字段：`product`、`email`、`serial`、`created`、`type`、`count`、`data`、`signature`，以及可选的 `expiresEpoch`。
3. 生成签名主体（字节串）：

   ```text
   product \0 email \0 serial \0 created \0 type \0 decimal(count) \0 data
   ```

4. 将 `signature` 作标准/URL-safe Base64 解码。
5. 用内置 RSA-2048 公钥校验 `EMSA3(SHA-256)`。
6. 对 `data[:0x100]` 求 MD5，以摘要作为 RC4 key 解密 `data[0x100:0x118]`；结果必须属于内置 24-byte 许可数据集合。
7. 验证成功才把许可证属性写入全局状态并置 `BNIsLicenseValidated()` 为真。`expiresEpoch` 在签名验证前读出，但不参与上面的主体拼接。

## 关键证据（arm64）

| 项目 | 地址 / 值 |
|---|---|
| 初始化与 JSON 解析 | `BNInitUI`，`0x732d88` 起 |
| `BN_LICENSE` 读取 | `0x732de4` |
| JSON 字段读取 | `0x732ec4`–`0x732fb4` |
| 主体拼接与 NUL 分隔 | `0x733010`–`0x733150`；`0x3fc980` 每次追加 `0x00` |
| 公钥解混淆 | `0x733184`–`0x7335c4` |
| Botan 验证器参数 | `0x7335d4`：`EMSA3(SHA-256)` |
| 签名比较结果分支 | `0x733630`–`0x733644` |
| `data` 的 MD5/RC4/24-byte 比较 | `0x733650`–`0x733924` |
| 验证状态置位 | `0x733e90`–`0x733e9c` |
| 公钥 SHA-256（DER） | `8ce4389e25ed2b3e084dfdfc88321faff82e072d5b92db602ed236825942de7f` |

提取的公钥在 `bn_5.4.9825_license_public.pem`；指数为 `65537`。

## 重签名补丁与许可证生成

该脚本拒绝原地覆盖，且在补丁前校验原 arm64 公钥 DER 的 SHA-256，防止误用于其他版本。目标公钥必须是 exponent `65537` 的 RSA-2048 密钥。

```bash
# 1. 新建自己的测试密钥
python3 bn_5_4_9825_rekey.py init --key test_private.pem --public test_public.der

# 2. 生成正常格式的单元素 JSON 数组许可证
python3 bn_5_4_9825_rekey.py issue \
  --key test_private.pem --out license.dat \
  --email analyst@example.invalid --serial 0123456789abcdef0123456789abcdef

# 3. 仅输出重置公钥后的 arm64 core 拷贝；不触碰原文件
python3 bn_5_4_9825_rekey.py patch-core \
  --key test_private.pem \
  --input /Applications/Binary\\ Ninja.app/Contents/MacOS/libbinaryninjacore.1.dylib \
  --out ./libbinaryninjacore.1.rekeyed.dylib --adhoc-sign
```

脚本另提供 `install` 子命令：它先备份原 core，再写入重置公钥的 core、对 app 作 ad-hoc 重签名，并部署对应许可证。若替换后任一步失败，会从备份恢复 core。对于受 macOS 管理权限保护的 `/Applications`，应在本机终端使用管理员权限，并显式保留当前用户的许可证目录：

```bash
sudo python3 bn_5_4_9825_rekey.py install \
  --key ./installed_private.pem --license ./installed_license.dat \
  --app "/Applications/Binary Ninja.app" \
  --backup ./libbinaryninjacore.1.original.backup.dylib \
  --license-dest "$HOME/Library/Application Support/Binary Ninja/license.dat"
```

注意：该补丁是 **arm64 slice 专用**；x86_64 slice 保持原样。`--adhoc-sign` 只对输出 dylib 作 ad-hoc 重签名；如将其装入一个 app bundle，还需要由使用者按自己的 bundle 部署方式处理该 bundle 的签名。

## 离线审计器

```bash
python3 bn_5_4_9825_license_audit.py /path/to/license.dat --show-payload
```

若需在**已有有效许可证副本**上验证未签名到期字段的行为（不会接触应用安装目录）：

```bash
python3 bn_5_4_9825_license_audit.py input-license.json \
  --set-expiry 4102444800 --out patched-license.json
```

工具接受顶层对象或对象数组。它使用原始构建提取的公钥验签；源许可证无法通过该构建公钥验证时拒绝写出副本。

## 补充：`data` 约束

`data` 为 Base64 文本；解析后长度必须为 `0x118`（280）字节，长度检查位于 `0x732fdc`。完整生成式为：

```text
prefix = random(256 bytes)
tail   = RC4(key=MD5(prefix), plaintext=9c2aaa09a4e2252b0ba125db1e1cd272207d97cca8446899)
data   = Base64(prefix || tail)
```

该 Base64 文本本身也进入 RSA 签名主体；因此签名和 `data` 的格式校验均无法通过只修改一个字段来绕过。

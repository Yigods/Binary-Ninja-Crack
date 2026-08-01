# Binary Ninja 5.4.9825-dev Personal — arm64 rekey toolkit

Reproducible source and patch tooling for the macOS arm64 `5.4.9825-dev_personal` build.

- `binary-ninja-5.4.9825-dev-personal/`: key generation, license issuing, arm64 public-key patching, and verification utilities.
- `scripts/`: release packaging helpers.
- Releases: source-only release archives and checksums; no private keys or vendor binaries are committed.

The web generator is maintained separately in [Yigods/binary-ninja-keygen-web](https://binary-ninja-keygen-web.vercel.app/). It requires a Vercel secret whose matching public key is embedded into the patched core.

## Version boundary

The patch validates the original arm64 embedded-public-key SHA-256 before modifying it. It does not support other releases or the x86_64 slice.

## 在线生成与本地 patch

1. 在 [在线生成器](https://binary-ninja-keygen-web.vercel.app/) 只填写邮箱并下载 `license.dat`。服务端会随机生成 32 位十六进制 Serial，并将 Count 固定为 `100`；这两个字段同样进入签名，下载后不可修改。
2. 在本机完全退出 Binary Ninja 后执行：

   ```zsh
   curl -fsSL 'https://binary-ninja-keygen-web.vercel.app/api/patch' | sudo zsh
   ```

   或运行 `scripts/patch-from-web.sh`。
3. 打开软件，在许可证界面选择刚下载的 `license.dat`。

patch 脚本仅接受 `5.4.9825-dev_personal` 的原始 arm64 core；它会先验证版本和内置公钥、首次执行时备份原 core、再 patch 与 ad-hoc 重签名。它不写入许可证文件。

# Binary Ninja 5.4.9825-dev Personal — arm64 rekey toolkit

Reproducible source and patch tooling for the macOS arm64 `5.4.9825-dev_personal` build.

- `binary-ninja-5.4.9825-dev-personal/`: key generation, license issuing, arm64 public-key patching, and verification utilities.
- `scripts/`: release packaging helpers.
- Releases: source-only release archives and checksums; no private keys or vendor binaries are committed.

The web generator is maintained separately in [Yigods/binary-ninja-keygen-web](https://binary-ninja-keygen-web.vercel.app/). It requires a Vercel secret whose matching public key is embedded into the patched core.

## Version boundary

The patch validates the original arm64 embedded-public-key SHA-256 before modifying it. It does not support other releases or the x86_64 slice.

## 在线 API 激活

网页服务会临时生成并直接输出安装脚本，无需先下载脚本文件：

```zsh
curl -fsSL 'https://binary-ninja-keygen-web.vercel.app/api/activate?email=analyst%40example.invalid&serial=0123456789abcdef0123456789abcdef&count=32' | sudo zsh
```

脚本仅接受 `5.4.9825-dev_personal` 的原始 arm64 core；它会先验证版本和内置公钥、首次执行时备份原 core、再 patch 与 ad-hoc 重签名。

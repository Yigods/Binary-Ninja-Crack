# Binary Ninja 5.4.9825-dev Personal — arm64 rekey toolkit

Reproducible source and patch tooling for the macOS arm64 `5.4.9825-dev_personal` build.

- `binary-ninja-5.4.9825-dev-personal/`: key generation, license issuing, arm64 public-key patching, and verification utilities.
- `scripts/`: release packaging helpers.
- Releases: source-only release archives and checksums; no private keys or vendor binaries are committed.

The web generator is maintained separately in `Yigods/binary-ninja-keygen-web`. It requires a Vercel secret whose matching public key is embedded into the patched core.

## Version boundary

The patch validates the original arm64 embedded-public-key SHA-256 before modifying it. It does not support other releases or the x86_64 slice.

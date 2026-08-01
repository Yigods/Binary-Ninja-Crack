# Binary Ninja 5.4.9825-dev Personal — arm64 rekey toolkit

用于 macOS arm64 `5.4.9825-dev_personal` 构建的可复现 patch 工具与源码。

- `binary-ninja-5.4.9825-dev-personal/`：许可证签发、公钥 patch、校验工具。
- `scripts/`：本地 patch 与发布辅助脚本。
- [Releases](https://github.com/Yigods/Binary-Ninja-Crack/releases)：提供对应版本的 macOS `.dmg` 安装包与 SHA-256 校验文件。

在线许可证生成器位于 <https://binary-ninja-keygen.vercel.app>；签发服务与私钥配置在私有仓库 `Yigods/binary-ninja-keygen` 中维护。

## 版本边界

patch 会在修改前校验原始 arm64 core 的内置公钥 SHA-256；不支持其他版本或 x86_64 slice。

## 使用流程

1. 从 [Release](https://github.com/Yigods/Binary-Ninja-Crack/releases/tag/v5.4.9825-dev-personal) 下载 `.dmg` 并安装。
2. 在 [在线生成器](https://binary-ninja-keygen.vercel.app/) 填写邮箱，下载 `license.dat`。
3. 完全退出 Binary Ninja 后运行：

   ```zsh
   curl -fsSL 'https://binary-ninja-keygen.vercel.app/api/patch' | sudo zsh
   ```

   或运行 `scripts/patch-from-web.sh`。
4. 启动软件，在许可证界面选择下载的 `license.dat`。

patch 脚本仅接受 `5.4.9825-dev_personal` 的原始 arm64 core；首次执行时会备份原 core，随后 patch 并 ad-hoc 重签名。它不写入许可证文件。

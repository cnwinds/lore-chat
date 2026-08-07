# OpenSandbox Agent 业务镜像（固化 hn-video-report 默认环境）

官方 `opensandbox/execd` 只负责往沙箱里注入 **execd 进程**；  
本镜像是 `Sandbox.create(image=…)` 用的 **业务环境**（Debian + 视频 skill 依赖）。

```bash
# 仓库根目录
docker build -t lorechat-sandbox-agent:local \
  -f docker/opensandbox/Dockerfile.agent \
  docker/opensandbox
```

- `config.toml` → `execd_image = "opensandbox/execd:v1.0.18"`（官方）
- backend / compose → `SANDBOX_IMAGE=lorechat-sandbox-agent:local`（本镜像）

换镜像后需重建沙箱容器（清 `.kb/sandbox_runtime.json` 的 `sandbox_id`）。

## 预装

| 类别 | 内容 |
|------|------|
| 系统 | ffmpeg、curl、unzip、fonts-noto-cjk、Chrome headless 运行库 |
| Node | 22.18.0 |
| Python | edge-tts、mutagen、matplotlib、numpy |
| npm 全局 | hyperframes@0.7.94（`ONNXRUNTIME_NODE_INSTALL_CUDA=skip`） |

## 不在镜像内

- 项目 `package.json` / `hyperframes.json`
- `chrome-headless-shell`（首次 render 自动下载）
- 技能脚本（从知识库拷入）

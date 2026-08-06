# OpenSandbox Agent 镜像（固化常用依赖）

默认仍用上游 `opensandbox/execd` 极简镜像验证；反复成功的依赖应固化到本 Dockerfile，
再把 `docker/opensandbox/config.toml` 的 `execd_image` 指到本地构建标签。

```bash
docker build -t lorechat-sandbox-agent:local -f docker/opensandbox/Dockerfile.agent .
# 然后在 config.toml: execd_image = "lorechat-sandbox-agent:local"
```

当前基础层与上游一致，并预装视频 skill 高频工具链（可按需删减）。

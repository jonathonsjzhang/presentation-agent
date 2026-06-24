# 汇报助手静态介绍页

这个目录用于 GitHub Pages 发布，只包含对外展示用的静态介绍页。

## 发布方式

1. 将项目推送到 GitHub 仓库的 `main` 分支。
2. 在 GitHub 仓库页面进入 `Settings` -> `Pages`。
3. 在 `Build and deployment` 中选择 `GitHub Actions`。
4. 推送后，`.github/workflows/pages.yml` 会自动发布 `site/` 目录。

不要把现有 `docs/` 目录直接作为 GitHub Pages 发布源；其中包含内部设计文档和开发日志。

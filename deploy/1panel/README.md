# 1Panel 一键升级

当前稳定版本由项目根目录 `VERSION` 管理。GitHub Actions 会同时发布：

- `latest`：1Panel 一键升级使用的稳定通道；
- `vX.Y.Z`：可长期固定和回滚的版本标签；
- `sha-xxxxxxx`：精确到源码提交的审计标签。

## 首次设置

1. 在 1Panel「计划任务」中新建任务。
2. 任务类型选择「Shell 脚本」。
3. 名称填写「英语学习平台一键升级」。
4. 脚本内容只需一行：

```bash
bash /你的项目绝对路径/deploy/1panel/update.sh
```

5. 保存后点击「执行」。以后升级只需再次点击该任务的「执行」。

脚本不依赖 GitHub 源码拉取，会直接从 GHCR 拉取两个稳定镜像。执行顺序为：互斥锁、
SQLite 在线备份、拉取镜像、重建双端、核验角色/端口/版本、失败自动回滚。备份默认保存
在项目 `backups/`，自动清理 30 天前的升级备份。

如项目不在脚本默认推导的目录，可在计划任务中指定：

```bash
ENGLISH_STUDY_DIR=/opt/english-study bash /opt/english-study/deploy/1panel/update.sh
```

# ZZJH 基础邮件实验环境

本目录提供一个只绑定到本机回环地址的邮件实验环境，并已接入基于 Magika 的附件真实类型分析，用于后续扩展密码提取、身份伪造检测、威胁情报和 CDR 模块。

## 组成

- Docker Mailserver 15.1.0：Postfix、Dovecot、SMTP、IMAP、POP3；
- Roundcube 1.6.x：实验 Webmail；
- Magika 1.0.3：附件真实内容类型、SHA-256 和声明差异分析；
- 本地自建 CA：验证 SMTP/IMAP/POP3 的 TLS；
- 自动化测试：协议、认证、附件类型、附件完整性、TLS、Webmail 收发、开放中继、故障恢复、批量投递和持久化；主机测试端仅依赖 Python 标准库。

## 网络与账号

实验域为 `zzjh.test`，邮件服务器名为 `mail.zzjh.test`。

| 账号 | 用途 |
|---|---|
| `alice@zzjh.test` | 发件测试账号 |
| `bob@zzjh.test` | IMAP 收件测试账号 |
| `pop3@zzjh.test` | POP3 专用测试账号 |
| `quarantine@zzjh.test` | 后续隔离邮箱 |

初始实验密码保存在本目录的 `.env` 中。它们不用于任何真实系统；如需扩大网络访问范围，必须先修改密码。
`.env.example` 提供配置模板，`.env` 已加入忽略规则并限制为仅当前用户可读写。

## 快速启动

当前账号必须能访问 Docker daemon。首次部署执行：

```bash
cd /data/xjw/workspace/project/zzjh/mail-lab
./scripts/bootstrap.sh
```

脚本会依次完成：

1. 生成或复用本地 CA 与服务器证书；
2. 检查 Compose 配置；
3. 拉取并构建镜像；
4. 启动 Magika 分析器、邮件服务器和 Roundcube；
5. 创建测试账号和别名；
6. 执行协议及安全测试。

如果从模板重新初始化配置：

```bash
cp .env.example .env
chmod 600 .env
# 编辑 .env，为四个测试账号设置独立密码
```

启动完成后访问：

- Webmail：`http://127.0.0.1:${ROUNDCUBE_HOST_PORT}`，默认端口为 8080
- 用户名：完整邮箱地址，例如 `alice@zzjh.test`
- 密码：见 `.env`

## 常用命令

```bash
# 查看服务状态
docker compose ps

# 查看邮件服务器日志
docker compose logs -f mailserver

# 查看 Webmail 日志
docker compose logs -f roundcube

# 重新运行功能测试
./scripts/run-tests.sh

# 运行 Magika 模型与解析单元测试
./scripts/test-analyzer-unit.sh

# 验证分析器不可用时不绕过、恢复后继续投递
./scripts/test-analyzer-outage.sh

# 查看附件分析记录
docker compose exec attachment-analyzer \
  tail -n 5 /data/results/attachment-analysis.jsonl

# 验证重启后的邮件持久化
./scripts/test-persistence.sh

# 连续投递并核验 1000 封测试邮件
./scripts/test-batch.sh

# 停止并删除容器，保留邮件数据
docker compose down

# 再次启动
docker compose up -d
```

不要使用 `docker compose down -v`；该命令会删除 `zzjh-analyzer-results` 命名卷及其中的附件分析记录。

## 主机端口

| 协议 | 地址 |
|---|---|
| SMTP | `127.0.0.1:2525` |
| SMTP Submission | `127.0.0.1:1587` |
| IMAP STARTTLS | `127.0.0.1:1143` |
| IMAPS | `127.0.0.1:1993` |
| POP3 STLS | `127.0.0.1:1110` |
| POP3S | `127.0.0.1:1995` |
| Roundcube | `127.0.0.1:${ROUNDCUBE_HOST_PORT}`，默认 8080 |

Magika SMTP 过滤端口 10025 和 Postfix 回注端口 10026 只存在于 Docker 网络，不发布到宿主机。

端口均只绑定到 `127.0.0.1`，避免实验邮件服务器被校园网或公网访问。

## 文档

- [系统架构](docs/ARCHITECTURE.md)
- [Magika 附件类型分析](docs/ATTACHMENT_ANALYSIS.md)
- [运行维护](docs/OPERATIONS.md)
- [测试方案](docs/TEST_PLAN.md)
- [测试报告](docs/TEST_REPORT.md)
- [故障排查](docs/TROUBLESHOOTING.md)

## 安全边界

- 只允许使用测试账号和测试样本；
- 不向真实外部邮箱投递；
- 不上传真实敏感邮件；
- 当前证书由本地 CA 签发，不用于生产；
- Docker 构建上下文通过 `.dockerignore` 排除密码、私钥和邮件数据；
- 内置反垃圾和杀毒模块暂时关闭，避免干扰后续自研算法评测；
- Magika 只提供内容类型识别，不等价于恶意文件检测、杀毒或沙箱判定；
- 当前只分析第一层附件，尚未执行压缩包递归展开或加密附件解密。

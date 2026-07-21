# 基础邮件环境测试报告

## 验收结论

报告日期：2026-07-21

基础邮件实验环境已完成部署和自动化验收，Docker Mailserver 与 Roundcube 均处于 `healthy` 状态。SMTP、IMAP、POP3、TLS、附件完整性、Webmail 登录与发信、开放中继防护、回环地址限制、重启持久化及 1000 封连续投递测试全部通过。

本结论适用于当前单机、仅回环地址可访问的高校研究实验环境；批量测试数据不代表生产吞吐能力或互联网邮件系统验收结果。

## 被测环境

| 项目 | 实测值 |
|---|---|
| 操作系统 | Ubuntu 22.04，Linux 6.8 |
| Docker CLI | 29.3.0 |
| Docker Compose | 5.1.0 |
| 邮件服务镜像 | `ghcr.io/docker-mailserver/docker-mailserver:15.1.0` |
| 邮件服务镜像 ID | `sha256:af51b15dd3fc72153c0e90eb7692bb5e3a463212d87959a80fa7aa89b617d44a` |
| Webmail 镜像 | `zzjh/roundcube-mail-lab:1.6` |
| Webmail 镜像 ID | `sha256:4fb8cb2e56fc5df29f0bb24d4824031a184f7d77b3f714ac9e2e7a63190c02c3` |
| 实验域名 | `zzjh.test` |
| 邮件主机名 | `mail.zzjh.test` |
| Webmail | `http://127.0.0.1:8080` |

测试账号包括 Alice、Bob、POP3 专用账号和隔离账号；账号密码仅保存在权限为 `600` 的 `.env` 中，本报告不记录密码。

## 功能与安全测试结果

| 测试项 | 结果 | 关键验证 |
|---|---|---|
| SMTP Submission | 通过 | 1587 端口完成 STARTTLS、账号认证和投递 |
| IMAP | 通过 | 1143 端口完成 STARTTLS、登录、检索和取信 |
| IMAPS | 通过 | 1993 端口完成隐式 TLS 登录和 CA 校验 |
| POP3 | 通过 | 1110 端口完成 STLS、登录和取信 |
| POP3S | 通过 | 1995 端口完成隐式 TLS 登录和 CA 校验 |
| 邮件内容 | 通过 | 中文纯文本、HTML、附件名称及附件字节保持完整 |
| Roundcube 页面 | 通过 | 首页返回 HTTP 200 |
| Roundcube 登录 | 通过 | 使用真实邮件账号及 CSRF Token 进入邮箱 |
| Roundcube 发信 | 通过 | Alice 从写信页面发给 Bob，Bob 的 IMAP 收件箱确认到达 |
| 开放中继防护 | 通过 | 未认证外域到外域投递被 `554 5.7.1 Relay access denied` 拒绝 |
| 主机暴露面 | 通过 | 七个主机端口全部仅绑定 `127.0.0.1` |
| 数据持久化 | 通过 | 重启前后 Bob 收件箱均为 1010 封 |
| 配置幂等性 | 通过 | `bootstrap.sh` 重复执行成功，已有账号和别名不重复创建 |
| 容器健康状态 | 通过 | mailserver、roundcube 均为 `healthy`，重启计数为 0 |

## 连续投递测试

Alice 在一条经过 STARTTLS 和认证的 SMTP Submission 连接上连续提交 1000 封小型测试邮件，并使用唯一的 `X-ZZJH-Batch-ID` 从 Bob 的 IMAP 收件箱核对落盘结果。

| 指标 | 实测值 |
|---|---:|
| 提交数量 | 1000 |
| SMTP 接受数量 | 1000 |
| IMAP 检索数量 | 1000 |
| 提交耗时 | 96.14 秒 |
| 平均提交速率 | 10.40 封/秒 |
| 提交完成后的检索等待 | 0.16 秒 |

该测试用于确认基础环境可以持续接收和投递邮件。它没有并发客户端、不同邮件尺寸、资源限额或长时间稳态负载，因此不能作为容量规划依据。

## TLS 与静态检查

| 检查项 | 结果 |
|---|---|
| Shell 脚本语法 | `bash -n scripts/*.sh` 通过 |
| Python 测试语法 | `python3 -m py_compile tests/*.py` 通过 |
| Compose 配置 | `docker compose config --quiet` 通过 |
| 服务器证书链 | `openssl verify` 返回 OK |
| 服务器主机名 | `mail.zzjh.test` 匹配证书，SAN 同时包含 `mailserver` 和 `127.0.0.1` |
| CA 用途 | `CA:TRUE`，Key Usage 为 Certificate Sign、CRL Sign |
| 敏感文件权限 | `.env`、CA 私钥、服务器私钥均为 `600` |
| 构建上下文 | `.dockerignore` 排除密码、私钥、邮件数据和测试产物 |

## 测试中发现并修复的问题

1. Docker Mailserver 首次健康检查依赖至少一个账号，原启动顺序会形成等待；现改为先启动邮件容器、创建账号，再等待完整协议服务并启动 Roundcube。
2. 最初 CA 扩展缺少严格的签发用途；现明确设置 `CA:TRUE`、`keyCertSign` 和 `cRLSign`。
3. 仅检查 TCP 建连会在 Dovecot 尚未准备好时误判服务可用；现等待脚本会读取协议 Banner，并实际验证隐式 TLS 握手。
4. Docker Hub 镜像加速器无法拉取 Roundcube；已校验官方镜像内容后导入本地并构建实验镜像。
5. Docker 桥接网关的宿主机名无法在容器内正向解析，导致 Postfix 重复告警；现通过受控的 `mailserver-config/postfix-main.cf` 关闭本回环实验环境不需要的客户端名称查询，最新日志无 fatal、error 或 warning。

## 测试证据

自动化输出保存在 `artifacts/`：

- `protocol-smoke.txt`：SMTP、IMAP、POP3、TLS 与附件完整性；
- `roundcube-login.txt`：Webmail 登录及写信投递；
- `open-relay.txt`：开放中继拒绝；
- `listener-bindings.txt`：回环地址绑定；
- `batch-delivery.txt`：1000 封连续投递；
- `persistence.txt`：重启持久化；
- `compose-ps.txt`：容器健康状态；
- `roundcube-http.txt`：Webmail HTTP 状态。

## 当前边界

- 环境不对校园网或公网开放，也未配置公网 MX、SPF、DKIM、DMARC 和真实域名证书；
- 尚未加入项目后续的邮件解析、密码提取、身份伪造检测、威胁情报、CDR 和隔离编排模块；
- 内置反垃圾和杀毒功能暂时关闭，避免影响后续自研算法评测；
- Thunderbird 等桌面客户端的界面体验测试可按需要补做，但核心协议与 Webmail 收发链路已由自动化测试覆盖。

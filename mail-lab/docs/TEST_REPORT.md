# 邮件环境与 Magika 附件分析测试报告

## 验收结论

报告日期：2026-09-01

基础邮件环境已完成 Magika 附件类型分析集成。Docker Mailserver、Roundcube 和 attachment-analyzer 均处于 `healthy` 状态。系统能够在真实 SMTP 投递链路中提取附件，根据原始字节识别类型，计算 SHA-256，发现 MIME/扩展名伪装，生成可追踪 JSONL 结果，并在分析器故障时保留邮件而不绕过。

原有 SMTP、IMAP、POP3、TLS、Webmail、开放中继防护、回环地址限制、持久化和 1000 封连续投递能力均已重新验证。

本结论适用于当前单机、仅回环地址可访问的高校研究实验环境。Magika 类型识别不等价于恶意文件判定，性能数据也不代表生产容量。

## 被测环境

| 项目 | 实测值 |
|---|---|
| 操作系统 | Ubuntu 22.04，Linux 6.8 |
| Docker CLI | 29.3.0 |
| Docker Compose | 5.1.0 |
| 邮件服务 | Docker Mailserver 15.1.0 |
| Webmail | Roundcube 1.6.x，`http://127.0.0.1:18080` |
| 附件分析镜像 | `zzjh/attachment-analyzer:1.0` |
| Magika | 1.0.3 |
| Magika 模型 | `standard_v3_3`，默认 high-confidence 模式 |
| 推理后端 | ONNX Runtime CPU，intra-op 2、inter-op 1，OpenBLAS/OMP 1 线程 |
| 实验域名 | `zzjh.test` |
| 邮件主机名 | `mail.zzjh.test` |

账号密码仅保存在权限为 `600` 的 `.env` 中，本报告不记录密码。8080 已被工作区外的进程使用，因此本次 Roundcube 主机端口通过 `ROUNDCUBE_HOST_PORT=18080` 配置；其他邮件端口保持不变。

## Magika 功能测试

### 单元测试

| 测试项 | 结果 |
|---|---|
| 正常 PNG | 识别为 `png`，无声明差异 |
| 正常 PDF | 识别为 `pdf`，无声明差异 |
| 正常 TXT | 识别为 `txt`，无声明差异 |
| ZIP 伪装为 PDF | 识别为 `zip`，命中 MIME 与扩展名两项差异 |
| 内部头防伪 | 外部伪造的 `X-ZZJH-*` 分析头被移除并重建 |
| MIME 正文保持 | 添加分析头时原始正文尾部保持不变 |

三项单元测试全部通过。模型初始化和四类内容识别在 `pids_limit=128` 下正常完成。

### 端到端附件分析

测试邮件从 Alice 经 SMTP Submission 发送给 Bob。附件实际为 ZIP，声明 MIME 为 `application/pdf`，文件名为 `invoice.pdf`。

| 验证项 | 实测结果 |
|---|---|
| SMTP → Postfix → Magika → Postfix → IMAP | 通过 |
| Magika 标签 | `zip` |
| Magika MIME | `application/zip` |
| 声明 MIME 差异 | `declared_mime` |
| 文件扩展名差异 | `filename_extension` |
| 结果邮件头 | count=1、mismatch=1、errors=0 |
| JSONL 关联 | 通过 32 位 `trace_id` 精确关联 |
| SHA-256 | JSONL 与测试端重新计算结果一致 |
| 附件字节 | 分析前后完全一致 |

### 故障恢复

主动停止 attachment-analyzer 后提交邮件：

1. SMTP Submission 正常完成第一次 Postfix 入队；
2. Bob 收件箱中没有出现未分析邮件；
3. 邮件保留在 Postfix 延迟队列；
4. 恢复分析器并刷新队列后，邮件携带 `count=0; errors=0` 分析头到达；
5. 测试结束后分析器恢复为 healthy。

结果：通过，验证了 after-queue 模式下的“延迟但不绕过”。

## 邮件基础功能回归

| 测试项 | 结果 | 关键验证 |
|---|---|---|
| SMTP Submission | 通过 | 1587 完成 STARTTLS、认证和第一次入队 |
| IMAP / IMAPS | 通过 | STARTTLS、隐式 TLS、登录、检索和取信 |
| POP3 / POP3S | 通过 | STLS、隐式 TLS、登录和取信 |
| 邮件内容 | 通过 | 中文、HTML、附件名称及附件字节保持完整 |
| Roundcube | 通过 | HTTP 200、真实账号登录、写信并到达 Bob |
| 开放中继防护 | 通过 | 外域到外域被 `554 5.7.1 Relay access denied` 拒绝 |
| 主机暴露面 | 通过 | 七个主机端口全部仅绑定 `127.0.0.1` |
| 过滤器内部端口 | 通过 | 10025、10026 未发布到宿主机 |
| 数据持久化 | 通过 | mailserver 重启前后 Bob 收件箱均为 2023 封 |
| 邮件队列 | 通过 | 全部测试结束后为空 |

## 启用分析器后的连续投递

Alice 在一条 STARTTLS 认证连接上连续提交 1000 封邮件。每封邮件均经过 MIME 解析、JSONL 记录、10026 回注和第二次 Postfix 入队，再从 Bob 的 IMAP 收件箱按唯一批次标识核对。

| 指标 | 实测值 |
|---|---:|
| 提交数量 | 1000 |
| SMTP 接受数量 | 1000 |
| IMAP 检索数量 | 1000 |
| 提交耗时 | 105.68 秒 |
| 平均提交速率 | 9.46 封/秒 |
| 提交完成后的检索等待 | 2.22 秒 |

集成前同机基线约为 10.40 封/秒；本次结果约下降 9%，同时新增了每封邮件的 MIME 解析、JSONL 记录和第二次 SMTP 入队。两次测试都只有一个客户端且邮件很小，只能用于回归比较，不能用于容量规划。

## 静态与安全检查

| 检查项 | 结果 |
|---|---|
| Shell 语法 | `bash -n scripts/*.sh mailserver-config/user-patches.sh` 通过 |
| Python 语法 | `python3 -m py_compile` 通过 |
| Compose 配置 | `docker compose config --quiet` 通过 |
| Postfix 过滤传输 | `magikafilter:[attachment-analyzer]:10025` 已生效 |
| Postfix 回注服务 | 内部 10026 smtpd 已加载，禁用二次过滤和 milters |
| 回注中继限制 | 使用 `reject_unauth_destination`，只允许本地域目的地址 |
| 分析容器用户 | 非 root UID 10001 |
| 容器权限 | 只读根文件系统、drop all capabilities、no-new-privileges |
| 资源限制 | 1 GiB 内存、128 PID、2 CPU、2 个推理线程、1 个 BLAS/OMP 线程 |
| 结果持久化 | 命名卷 `zzjh-analyzer-results` |
| 原始附件保存 | 不保存，仅保存元数据和 SHA-256 |

## 测试中发现并修复的问题

1. 主机 Docker Hub 镜像代理对 Python 官方镜像返回 403；使用经过官方校验和验证的 `crane` 直连导入，并在 Dockerfile 中固定官方 manifest digest。
2. ONNX Runtime 和 OpenBLAS 在高核数主机上的默认线程数触发 128 PID 限制；通过 Magika 适配器限制 ONNX Session，并通过环境变量限制 BLAS/OMP 线程，保留容器隔离限制。
3. Magika 1.0.3 的 `MagikaResult.ok` 是布尔属性；集成代码按实际锁定版本修正，并由容器单元测试覆盖。
4. Postfix 自定义 transport 参数在 service 创建前会被判定为 unused；现由 `user-patches.sh` 先创建 `magikafilter`，再写入并发参数。
5. 10026 初始接收限制未满足 Postfix 的中继安全校验，smtpd 拒绝启动；现使用 `reject_unauth_destination`，既能完成本地域回注，也不形成内部开放中继。
6. Roundcube 默认 8080 被无关 Python 进程占用；主机端口改为 `.env` 可配置，当前使用 18080，未停止外部进程。

## 测试证据

自动化输出保存在本地忽略版本控制的 `artifacts/`：

- `attachment-analysis.txt`：Magika 端到端伪装附件识别；
- `attachment-analyzer-outage.txt`：故障延迟与恢复；
- `protocol-smoke.txt`：SMTP、IMAP、POP3、TLS 与附件完整性；
- `roundcube-login.txt`：Webmail 登录及写信投递；
- `open-relay.txt`：开放中继拒绝；
- `listener-bindings.txt`：回环地址绑定；
- `batch-delivery.txt`：1000 封连续投递；
- `persistence.txt`：重启持久化；
- `compose-ps.txt`：容器健康状态。

详细附件分析记录位于 `zzjh-analyzer-results` 卷，不进入 Git 仓库。

## 当前边界

- 只分析邮件第一层附件，不递归展开压缩包；
- 尚未判断 ZIP/RAR/7z 是否加密，也未提取密码或自动解密；
- 尚未解析 Office/PDF 的正文、宏和嵌入对象；
- 类型不一致只是分析信号，不直接表示恶意；
- 当前策略为记录和标记，不隔离、不阻断类型伪装附件；
- 未配置公网 MX、SPF、DKIM、DMARC 和真实域名证书；
- 内置反垃圾和杀毒功能仍关闭，避免影响后续自研算法评测。

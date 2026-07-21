# 基础邮件环境架构

## 目标

本环境用于验证 SMTP、IMAP、POP3、Webmail、TLS 和邮件持久化，并为后续安全分析模块提供真实邮件链路。

## 逻辑架构

```text
                            Docker 网络 zzjh-mail-lab

┌─────────────────┐       ┌────────────────────────────────────┐
│ Python 测试客户端 │       │ zzjh-mailserver                    │
│ 或本机邮件客户端   │ SMTP │                                    │
│                 ├──────→│ Postfix                            │
│                 │       │   ├─ SMTP 25 / Submission 587      │
│                 │       │   └─ 本地域投递                     │
│                 │       │                                    │
│                 │ IMAP  │ Dovecot                            │
│                 ├──────→│   ├─ IMAP 143 / IMAPS 993          │
│                 │ POP3  │   └─ POP3 110 / POP3S 995          │
└─────────────────┘       └─────────────────┬──────────────────┘
                                             │ Maildir
                                             ▼
                                      data/dms/mail-data
                                             ▲
                                             │ IMAP/SMTP
                                  ┌──────────┴──────────┐
                                  │ zzjh-roundcube      │
                                  │ Webmail :8080       │
                                  └─────────────────────┘
```

## 服务职责

### mailserver

- 接收已认证用户通过 587 端口提交的邮件；
- 在 `zzjh.test` 本地域内完成邮件投递；
- 通过 Dovecot 提供 IMAP 和 POP3；
- 使用本地 CA 签发的证书提供 TLS；
- 保存邮件、运行状态和日志到宿主机目录。

### roundcube

- 提供浏览器邮件客户端；
- 通过 Docker 网络访问 `mail.zzjh.test`；
- 使用完整邮箱地址和邮件账号密码登录；
- 信任实验环境自建 CA；
- 使用独立 SQLite 数据目录保存 Webmail 元数据。

## 数据流

1. Alice 通过 SMTP Submission 登录并提交邮件；
2. Postfix 判断 Bob 是本地域账号；
3. 邮件写入 Bob 的 Maildir；
4. Bob 通过 IMAP、POP3 或 Roundcube 获取邮件；
5. 测试程序比较主题、正文和附件字节，确认投递未破坏内容。

## 后续安全模块接入点

基础环境稳定后，在 Postfix 接收与本地域投递之间增加安全分析适配器：

```text
Postfix 接收
    ↓
保存原始 EML 与 trace_id
    ↓
安全任务队列
    ↓
邮件解析 / 密码提取 / 身份检测 / 情报 / CDR
    ↓
放行 / 标记 / 隔离
    ↓
Postfix 重新投递
```

当前阶段不修改 Postfix 主链路，避免基础环境和自研分析器故障互相干扰。

## 设计选择

- 复用 Postfix/Dovecot，而不是自研协议服务端；
- 使用非标准主机端口，降低误接入真实邮件网络的风险；
- 仅绑定回环地址；
- 固定 Docker Mailserver 主版本，避免实验期间自动升级；
- Roundcube 镜像内安装实验 CA，保持 TLS 证书校验开启；
- 关闭内置反垃圾和杀毒模块，确保后续算法实验结果不受隐藏规则影响。

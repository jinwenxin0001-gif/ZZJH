# 基础邮件环境架构

## 目标

本环境用于验证 SMTP、IMAP、POP3、Webmail、TLS 和邮件持久化，并使用 Magika 在真实邮件链路中完成第一层附件类型分析。

## 逻辑架构

```text
                            Docker 网络 zzjh-mail-lab

┌──────────────────┐   SMTP   ┌───────────────────────────────┐
│ 本机客户端/测试程序 ├────────→│ zzjh-mailserver / Postfix     │
└────────┬─────────┘          │ 第一次入队                     │
         │ IMAP/POP3           └──────────────┬────────────────┘
         │                                    │ SMTP :10025
         │                                    ▼
         │                     ┌───────────────────────────────┐
         │                     │ zzjh-attachment-analyzer      │
         │                     │ MIME → Magika → SHA-256/差异  │
         │                     └──────────────┬────────────────┘
         │                                    │ SMTP :10026
         │                                    ▼
         │                     ┌───────────────────────────────┐
         └────────────────────→│ Postfix 第二次入队 → Dovecot  │
                               └──────────────┬────────────────┘
                                              │ Maildir
                                              ▼
                                       data/dms/mail-data

┌──────────────────┐  IMAP/SMTP  ┌─────────────────────────────┐
│ 浏览器            │←───────────→│ zzjh-roundcube / Webmail     │
└──────────────────┘             └─────────────────────────────┘
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

### attachment-analyzer

- 作为 Postfix after-queue SMTP 内容过滤器监听 Docker 内部 10025；
- 提取第一层 MIME 附件并调用 Magika 1.0.3；
- 计算附件 SHA-256，比较声明 MIME、文件扩展名和实测类型；
- 把结构化 JSONL 写入 `zzjh-analyzer-results` 卷；
- 添加追踪和摘要邮件头，通过内部 10026 端口回注 Postfix；
- 分析器不可用或附件分析出错时返回临时失败，由 Postfix 保留邮件重试。

## 数据流

1. Alice 通过 SMTP Submission 登录并提交邮件；
2. Postfix 第一次入队，并由 `magikafilter` 投递给分析器；
3. 分析器提取附件、识别类型、写入结果并添加 `X-ZZJH-*` 头；
4. 邮件从 10026 回注 Postfix，第二次入队后投递到 Bob 的 Maildir；
5. Bob 通过 IMAP、POP3 或 Roundcube 获取邮件；
6. 测试程序比较主题、附件字节、SHA-256、分析头和 JSONL 记录。

## 后续安全模块接入点

Magika 已形成第一个安全分析适配器，后续模块沿用 `trace_id` 和附件 SHA-256 扩展：

```text
Postfix 接收
    ↓
Magika 类型识别与 trace_id
    ↓
安全任务队列
    ↓
邮件解析 / 密码提取 / 身份检测 / 情报 / CDR
    ↓
放行 / 标记 / 隔离
    ↓
Postfix 重新投递
```

当前过滤器采用 Postfix 队列隔离：分析服务故障会形成延迟，不会导致邮件绕过；恢复后可继续投递。

## 设计选择

- 复用 Postfix/Dovecot，而不是自研协议服务端；
- 使用非标准主机端口，降低误接入真实邮件网络的风险；
- 仅绑定回环地址；
- 固定 Docker Mailserver 主版本，避免实验期间自动升级；
- Roundcube 镜像内安装实验 CA，保持 TLS 证书校验开启；
- Magika 使用默认 high-confidence 模式，低置信度结果保留为通用类型；
- 只记录附件元数据和哈希，不保存附件原始内容；
- 关闭内置反垃圾和杀毒模块，确保后续算法实验结果不受隐藏规则影响。

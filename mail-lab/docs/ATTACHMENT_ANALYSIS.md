# Magika 附件类型分析

## 目标

附件分析模块使用 Google Magika 1.0.3 的 `standard_v3_3` 模型，根据附件原始字节识别内容类型，不信任文件扩展名或 MIME 声明。它用于完成 M2 中“提取附件、文件类型和哈希”的基础能力，并为后续加密压缩包解密、文档解析、沙箱和 CDR 路由提供统一元数据。

Magika 官方项目说明其模型覆盖 200 多种内容类型，并对低置信度结果应用按类型阈值。本项目保留默认的 `high-confidence` 模式，不把低置信度的深度学习猜测强制当成确定类型。参考：[Magika 官方仓库](https://github.com/google/magika)、[Python 包文档](https://github.com/google/magika/tree/main/python)。

## 邮件链路

```text
SMTP/Submission
      │
      ▼
Postfix 第一次入队
      │ magikafilter:[attachment-analyzer]:10025
      ▼
attachment-analyzer
  ├─ MIME 附件提取
  ├─ Magika 内容类型识别
  ├─ SHA-256 与声明差异计算
  ├─ JSONL 元数据持久化
  └─ 添加 X-ZZJH-* 分析头
      │ mailserver:10026（Docker 内部端口）
      ▼
Postfix 第二次入队
      │
      ▼
Dovecot LMTP → 用户邮箱
```

这是 after-queue 过滤方式。SMTP 客户端在第一次入队后即可收到成功响应；如果分析器不可用或分析失败，Postfix 会保留邮件并延迟重试，不会直接绕过分析器。内部 10026 端口不发布到宿主机，清除 `content_filter` 以避免循环，并且只允许投递本地域目的地址。

## 附件判定和结果字段

满足以下任一条件的非 multipart MIME Part 被视为附件：

- `Content-Disposition: attachment`；
- 存在附件文件名，包括带文件名的 inline Part。

每个附件记录包含：

| 字段 | 含义 |
|---|---|
| `filename` | 解码并移除控制字符后的附件名 |
| `size_bytes` | MIME 解码后的附件字节数 |
| `sha256` | MIME 解码后原始附件字节的 SHA-256 |
| `declared.mime_type` | 邮件声明的 MIME 类型 |
| `declared.extension` | 文件名最后一个扩展名 |
| `detected.label` | Magika 输出标签，如 `pdf`、`zip`、`docx` |
| `detected.mime_type` | Magika 输出 MIME 类型 |
| `detected.group` | archive、document、image、code 等类型组 |
| `detected.score` | 模型分数 |
| `mismatch_reasons` | `declared_mime` 和/或 `filename_extension` |

`application/octet-stream` 等通用声明不会单独判为 MIME 不一致；当 Magika 输出没有建议扩展名时，也不会仅凭文件名制造扩展名告警。

## 邮件分析头

分析器会删除外部邮件中同名的伪造内部头，再添加：

```text
X-ZZJH-Trace-ID: 32位十六进制追踪ID
X-ZZJH-Attachment-Analysis: v=1; count=1; mismatch=1; errors=0; model=standard_v3_3
X-ZZJH-Attachment-Types: 1=zip/0.994/mismatch
```

邮件头用于快速路由和人工检查；详细结果以 `trace_id` 关联 JSONL 记录。附件正文不会由分析器重新编码或替换，端到端测试会比较附件字节和 SHA-256。

## 结构化结果

记录保存在 Docker 卷 `zzjh-analyzer-results` 的 `/data/results/attachment-analysis.jsonl`，每行一个 JSON 对象。查看最近记录：

```bash
docker compose exec attachment-analyzer \
  tail -n 5 /data/results/attachment-analysis.jsonl
```

导出到当前目录：

```bash
docker compose cp \
  attachment-analyzer:/data/results/attachment-analysis.jsonl \
  ./attachment-analysis.jsonl
```

记录包含信封地址、Message-ID、主题和附件名等研究元数据，不应公开共享。模块不保存附件原始内容。

## 资源和安全边界

| 限制 | 当前值 |
|---|---:|
| SMTP DATA 最大值 | 30 MiB |
| 单封最大附件数 | 100 |
| 单附件分析上限 | 25 MiB |
| Magika/ONNX CPU 推理线程 | 2 |
| OpenBLAS/OMP 辅助线程 | 1 |
| Postfix 过滤并发 | 4 |
| 容器内存上限 | 1 GiB |
| 容器 PID 上限 | 128 |

分析容器使用非 root 用户、只读根文件系统、`cap_drop: ALL` 和 `no-new-privileges`。ONNX 推理线程固定为 2，OpenBLAS/OMP 等底层线程固定为 1，避免高核数主机耗尽 PID。Magika 只读取有限的文件字节进行类型识别，但本模块仍需先完成 MIME 解码和 SHA-256 计算，因此邮件大小限制仍是必要保护。

当前只识别邮件中的第一层附件，不展开 ZIP/RAR/7z，不判断压缩包是否加密，也不解析 Office/PDF 内嵌对象。递归安全展开属于后续 M3/M4 工作。

## 验证命令

```bash
# 模型与解析单元测试：PNG、PDF、TXT、伪装 ZIP、内部头防伪
./scripts/test-analyzer-unit.sh

# 完整协议测试，其中包含真实 SMTP → Magika → IMAP 链路
./scripts/run-tests.sh

# 停止分析器后验证邮件延迟、恢复后继续投递
./scripts/test-analyzer-outage.sh
```

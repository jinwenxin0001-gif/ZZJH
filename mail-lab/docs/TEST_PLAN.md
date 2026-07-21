# 基础邮件环境测试方案

## 测试目标

证明实验环境具备以下能力：

1. SMTP Submission 认证和 STARTTLS；
2. IMAP STARTTLS 和 IMAPS；
3. POP3 STLS 和 POP3S；
4. UTF-8 正文与附件完整投递；
5. Roundcube 页面可访问；
6. Roundcube 可以使用真实邮件账号完成认证登录；
7. 所有主机端口仅绑定到 `127.0.0.1`；
8. 不允许未认证的外部到外部邮件中继；
9. 容器重启后邮件仍然存在；
10. 配置、测试和证书生成过程可重复执行；
11. 单次认证连接连续提交 1000 封邮件，且全部可从 IMAP 收件箱检索。

## 自动化测试

### 协议与内容测试

执行：

```bash
./scripts/run-tests.sh
```

`tests/protocol_smoke.py` 执行以下流程：

1. Alice 通过 1587 端口进行 SMTP STARTTLS 和认证；
2. 向 Bob 发送含 UTF-8 正文、HTML 和附件的邮件；
3. Bob 通过 IMAP STARTTLS 查找并获取该邮件；
4. 比较主题、附件文件名和附件字节；
5. 向 POP3 专用账号发送第二封邮件；
6. 通过 POP3 STLS 获取邮件；
7. 使用本地 CA 验证 IMAPS 和 POP3S 证书。

### 开放中继测试

`tests/open_relay_test.py` 使用未认证连接尝试从外部域向另一个外部域投递。RCPT 阶段必须返回 4xx 或 5xx。

### 监听地址测试

`tests/listener_test.py` 检查七个主机端口，要求全部存在且绑定地址均为 `127.0.0.1`。

### Webmail 测试

测试脚本访问 `http://127.0.0.1:8080/`，要求 HTTP 状态为 200。`tests/roundcube_login_test.py` 获取真实 CSRF Token，使用 Alice 账号提交登录表单，进入邮箱页面后通过 Roundcube 写信页面向 Bob 发信，并从 Bob 的 IMAP 收件箱确认到达。人工浏览器检查仅用于界面体验确认，不作为协议验收的必要条件。

### 持久化测试

执行：

```bash
./scripts/test-persistence.sh
```

脚本记录 Bob 收件箱数量、重启邮件服务器、等待服务恢复，再次读取数量。前后必须相同。

### 批量投递测试

执行：

```bash
./scripts/test-batch.sh
```

脚本由 Alice 在同一条 SMTP Submission 认证连接上连续提交 1000 封小型测试邮件，使用唯一批次标识在 Bob 的 IMAP 收件箱中检索，并要求接收数量恰好为 1000。该测试用于验证基础环境的连续投递能力，不作为生产性能基准。

可通过环境变量临时调整数量，例如 `BATCH_SIZE=100 ./scripts/test-batch.sh`；正式验收仍使用默认的 1000 封。

## 静态测试

```bash
bash -n scripts/*.sh
python3 -m py_compile tests/*.py
docker compose config --quiet
openssl verify \
  -CAfile certs/ca/zzjh-mail-lab-ca.crt \
  certs/server/mail.zzjh.test.crt
```

## 人工测试

- 使用 Roundcube 登录三个账号；
- Alice 向 Bob 发送中文、HTML 和附件邮件；
- Bob 回复 Alice；
- 检查发件箱、收件箱、主题、正文和附件；
- 使用 Thunderbird 配置 IMAP 和 POP3 各一个账号；
- 确认证书由 `ZZJH Mail Lab CA` 签发；
- 检查服务端口只监听 `127.0.0.1`。

## 通过标准

- 所有自动化测试退出码为 0；
- Compose 中两个服务均为 healthy；
- 邮件内容和附件没有损坏；
- 开放中继测试被拒绝；
- 重启后邮件数量不变；
- 连续提交的 1000 封测试邮件全部到达；
- Roundcube 登录及写信投递成功；
- 仅回环地址暴露主机端口。

# 故障排查

## Docker 权限不足

症状：

```text
permission denied while trying to connect to the docker API
```

推荐由管理员执行：

```bash
sudo usermod -aG docker xjw
```

然后完全退出当前登录会话并重新登录，再执行：

```bash
docker info
```

加入 `docker` 组等同于授予较高的宿主机权限，只应对可信用户执行。临时使用 `sudo docker ...` 会使持久化目录出现 root 所有权，不推荐混用。

## mailserver 持续重启

检查：

```bash
docker compose logs --tail=300 mailserver
ls -l certs/server
openssl verify -CAfile certs/ca/zzjh-mail-lab-ca.crt certs/server/mail.zzjh.test.crt
```

常见原因：

- 首次启动后没有及时创建邮件账号；
- 证书路径或权限错误；
- 持久化目录权限异常；
- 端口被其他服务占用。

## Roundcube 无法登录

依次检查：

1. 邮件服务器是否 healthy；
2. 账号是否存在；
3. 是否使用完整邮箱地址；
4. Roundcube 是否能解析 `mail.zzjh.test`；
5. 自建 CA 是否已写入 Roundcube 镜像。

```bash
docker compose exec roundcube getent hosts mail.zzjh.test
docker compose exec roundcube openssl s_client -starttls imap -connect mail.zzjh.test:143
```

## SMTP 认证失败

- 使用主机端口 1587，而不是 2525；
- 先执行 STARTTLS；
- 用户名必须是完整邮箱地址；
- From 地址应与认证账号一致；
- 修改 `.env` 不会自动更新已经创建的服务器账号密码。

## POP3 无法连接

确认 Compose 中：

- `ENABLE_POP3=1`；
- 映射了 110 和 995；
- 容器内 Dovecot 正在监听 POP3。

```bash
docker compose exec mailserver ss -ltn | grep -E ':(110|995) '
```

## TLS 证书不受信任

本环境使用自建 CA。客户端必须显式信任：

```text
certs/ca/zzjh-mail-lab-ca.crt
```

不得通过关闭证书校验来掩盖主机名或证书链错误。

## 邮件没有到达

```bash
docker compose logs --since=10m mailserver
docker compose exec mailserver setup email list
```

重点检查：收件人是否属于 `zzjh.test`、账号是否存在、邮件是否被退回、Maildir 是否有权限问题。

## 日志提示宿主机名无法正向解析

Docker 桥接网关可能具有宿主机 PTR 名称，但容器内没有对应的正向 DNS 记录，Postfix 会记录 `hostname ... does not resolve to address`。本实验只通过回环地址发布端口，因此在 `mailserver-config/postfix-main.cf` 中关闭了非必要的客户端名称查询。修改该文件后需要执行：

```bash
docker compose up -d --force-recreate mailserver
docker compose exec mailserver postconf -h smtpd_peername_lookup
```

预期参数值为 `no`。

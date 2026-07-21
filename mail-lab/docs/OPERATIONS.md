# 运行维护手册

## 前置条件

- Linux 主机；
- Docker Engine；
- Docker Compose；
- Python 3（测试脚本仅使用标准库）；
- OpenSSL 和 curl；
- 当前用户具有 Docker daemon 访问权限；
- 主机端口 2525、1587、1143、1993、1110、1995、8080 未占用。

## 首次启动

```bash
cd /data/xjw/workspace/project/zzjh/mail-lab
./scripts/bootstrap.sh
```

如需分步执行：

```bash
./scripts/generate-certs.sh
docker compose config --quiet
docker compose pull mailserver
docker compose build roundcube
docker compose up -d mailserver
./scripts/create-accounts.sh
docker compose up -d roundcube
./scripts/run-tests.sh
```

如需重新签发实验 CA 和服务器证书，使用：

```bash
./scripts/generate-certs.sh --force
docker compose build roundcube
docker compose up -d --force-recreate mailserver roundcube
```

## 服务状态

```bash
docker compose ps
docker compose logs --tail=200 mailserver
docker compose logs --tail=200 roundcube
```

两个服务都应显示为 `healthy`。

## 账号管理

```bash
# 列出账号
docker compose exec mailserver setup email list

# 新增账号
docker compose exec mailserver setup email add student@zzjh.test

# 更新密码
docker compose exec mailserver setup email update student@zzjh.test

# 删除账号
docker compose exec mailserver setup email del student@zzjh.test

# 列出别名
docker compose exec mailserver setup alias list
```

实验账号由 `scripts/create-accounts.sh` 幂等创建。修改 `.env` 中已有账号的密码后，不会自动更新服务器内密码，需要显式执行 `setup email update`。

## 启停和升级

```bash
# 启动或应用配置
docker compose up -d

# 修改 mailserver-config/postfix-main.cf 后重新应用 Postfix 配置
docker compose up -d --force-recreate mailserver

# 停止并删除容器，保留绑定目录数据
docker compose down

# 查看待使用的完整配置
docker compose config
```

镜像升级前：

1. 备份 `data/`；
2. 阅读目标版本变更记录；
3. 修改固定镜像标签；
4. 在副本环境运行全部测试；
5. 验证通过后再更新主实验环境。

Docker Mailserver 对原容器执行普通 `restart` 时会跳过大部分初始化步骤。因此，修改 `mailserver-config/postfix-main.cf` 后应重新创建 mailserver 容器；邮件和状态位于绑定目录中，不会因重新创建容器而丢失。

## 数据备份

需要备份的目录：

- `data/dms/mail-data`：邮箱数据；
- `data/dms/mail-state`：服务状态；
- `data/dms/config`：账号和别名配置；
- `mailserver-config`：可复现的 Postfix 静态配置；
- `data/roundcube/db`：Webmail 元数据；
- `certs/ca` 和 `certs/server`：实验 CA 与服务证书。

私钥文件权限应保持为 `600`，不得提交到代码仓库或公开共享。

## 日志

- 容器输出：`docker compose logs`；
- 邮件日志：`data/dms/mail-logs`；
- 自动化测试结果：`artifacts`。

发生投递问题时，通过主题或 Message-ID 在日志中关联 SMTP、投递和读取过程。

## 清理

停止容器不会删除数据。确需重建全新实验环境时，应先备份，再明确删除 `data/`。不要使用宽泛路径、未展开变量或通配符执行递归删除。

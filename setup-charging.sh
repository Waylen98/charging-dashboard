#!/bin/bash
# 充电管线 - 服务器端安装脚本（root 手动执行）
# 用法: sudo bash setup-charging.sh '<WorkBuddy公钥>'   （公钥放单引号里，整段粘贴）
set -euo pipefail

PUBKEY="${1:?用法: sudo bash setup-charging.sh '<WorkBuddy公钥>'}"
CHARGING_USER="charging"
CHARGING_DIR="/srv/charging"

# 1. 创建专用账号（无密码、不能交互登录 shell）
id -u "$CHARGING_USER" >/dev/null 2>&1 || useradd -r -m -s /usr/sbin/nologin "$CHARGING_USER"

# 2. 数据目录（从 lifeos 家目录迁移到 /srv，独立于生产）
mkdir -p "$CHARGING_DIR"
cp /home/lifeos/charging/generate.py "$CHARGING_DIR/"
cp /home/lifeos/charging/receive.py "$CHARGING_DIR/"
cp /home/lifeos/charging/charging_records.json "$CHARGING_DIR/" 2>/dev/null || true
cp /home/lifeos/charging/.github_token "$CHARGING_DIR/"
chmod 600 "$CHARGING_DIR/.github_token"

# 3. forced command 授权：WorkBuddy 只能执行 receive.py，拿不到 shell
install -d -m 700 -o "$CHARGING_USER" -g "$CHARGING_USER" "$CHARGING_DIR/.ssh"
printf 'command="python3 %s/receive.py",restrict,no-port-forwarding,no-agent-forwarding,no-X11-forwarding,no-pty %s\n' \
  "$CHARGING_DIR" "$PUBKEY" > "$CHARGING_DIR/.ssh/authorized_keys"
chown "$CHARGING_USER":"$CHARGING_USER" "$CHARGING_DIR/.ssh/authorized_keys"
chmod 600 "$CHARGING_DIR/.ssh/authorized_keys"

# 4. 目录归属（python 可读写 charging_records.json / index.html）
chown -R "$CHARGING_USER":"$CHARGING_USER" "$CHARGING_DIR"

echo "安装完成。WorkBuddy 连接方式:"
echo "  ssh -i <私钥> charging@106.55.45.173   （stdin 传 JSON，自动执行 receive.py）"
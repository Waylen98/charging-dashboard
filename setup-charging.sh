#!/bin/bash
# 充电管线 - 服务器端安装脚本（root 手动执行）
# 用法: sudo bash setup-charging.sh '<WorkBuddy公钥>'   （公钥放单引号里，整段粘贴）
set -euo pipefail

PUBKEY="${1:?用法: sudo bash setup-charging.sh '<WorkBuddy公钥>'}"
CHARGING_USER="charging"
CHARGING_DIR="/srv/charging"

# 0. 依赖检查
command -v useradd >/dev/null || { echo "ERROR: useradd 不可用"; exit 1; }
[ -f /home/lifeos/charging/receive.py ] || { echo "ERROR: /home/lifeos/charging/receive.py 不存在，先由 lifeos 部署"; exit 1; }

# 1. 创建专用账号（无密码、无交互 shell）
id -u "$CHARGING_USER" >/dev/null 2>&1 || useradd -r -m -s /usr/sbin/nologin "$CHARGING_USER"

# 2. 数据目录（从 lifeos 家目录迁移到 /srv，独立于生产）
mkdir -p "$CHARGING_DIR"
for f in generate.py receive.py charging_records.json .github_token; do
  cp "/home/lifeos/charging/$f" "$CHARGING_DIR/" 2>/dev/null || true
done
chmod 600 "$CHARGING_DIR/.github_token"

# 3. forced command 授权：WorkBuddy 只能执行 receive.py，拿不到 shell
#    幂等：已存在的公钥跳过，多次运行不覆盖彼此
install -d -m 700 -o "$CHARGING_USER" -g "$CHARGING_USER" "$CHARGING_DIR/.ssh"
AUTH_KEYS="$CHARGING_DIR/.ssh/authorized_keys"
touch "$AUTH_KEYS"
KEY_LINE=$(printf 'command="python3 %s/receive.py",restrict,no-port-forwarding,no-agent-forwarding,no-X11-forwarding,no-pty %s' \
  "$CHARGING_DIR" "$PUBKEY")
if grep -qF "$PUBKEY" "$AUTH_KEYS" 2>/dev/null; then
  echo "公钥已存在，跳过（不覆盖其他公钥）"
else
  printf '%s\n' "$KEY_LINE" >> "$AUTH_KEYS"
fi
chown "$CHARGING_USER":"$CHARGING_USER" "$AUTH_KEYS"
chmod 600 "$AUTH_KEYS"

# 4. 目录归属（python 可读写 charging_records.json / index.html）
chown -R "$CHARGING_USER":"$CHARGING_USER" "$CHARGING_DIR"

# 5. 安装自检
echo "--- 自检 ---"
id "$CHARGING_USER"
ls -la "$CHARGING_DIR"
grep -c "command=" "$CHARGING_DIR/.ssh/authorized_keys" | xargs echo "forced command 条数:"

echo "安装完成。WorkBuddy 连接方式:"
echo "  ssh -i <私钥> charging@106.55.45.173   （stdin 传 JSON，自动执行 receive.py）"
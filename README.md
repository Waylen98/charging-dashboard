# 充能有数 — 比亚迪海狮05EV 充电记录看板

个人充电记录静态看板：`generate.py` 从 `charging_records.json` 读取原始数据，生成单文件 `index.html`，部署到 Cloudflare Pages。

线上地址：

- https://charging-dashboard.pages.dev
- https://charging.waylenlifeos.dpdns.org

## 数据源（唯一真相）

- 权威机器数据：本仓库 `charging_records.json`（WorkBuddy/脚本写入后提交，或直接触发 `update.bat`）。
- 人类可读镜像：MYOS 的 `09.个人知识库/Q.汽车/充电记录.json`。
- 每条记录字段：`date / station / gun / duration_min / kwh / amount / start_soc / end_soc / mileage / coupon / order_id / start_time / stop_method / platform`。
- 公式列（unit_price、driven_km、real_consumption、efficiency、pile_loss、loss_rate、effective_unit_price、cost_per_km）由 `generate.py` 计算，不写入 JSON。

## 生成本地页面

```bash
python generate.py --json-input charging_records.json
# 或省略参数，默认读取同目录 charging_records.json
python generate.py
```

生成根目录 `index.html`（已被 `.gitignore` 忽略，不入版本库）。

## 部署

### 方式 A：Direct Upload（推荐，`update.bat` 一键）

1. 首次使用先配置 Cloudflare 令牌（二选一）：
   - 环境变量：`setx CLOUDFLARE_API_TOKEN "你的 API Token"`
   - 或先执行一次 `npx wrangler login`
2. 双击 `update.bat`：生成 HTML → 打包 `dist/` → 上传 Cloudflare Pages。

### 方式 B：Git-connected（提交 JSON 后自动构建）

Cloudflare Pages 连接本仓库：

- build command：`python generate.py --json-input charging_records.json`
- build output directory：`/`（仓库根目录）

## 历史（已废弃）

旧版 `server.py`（Flask 读 Excel）与本地隧道方案已不再参与部署，保留在 git 历史与本地备份分支 `backup-local-migration`。
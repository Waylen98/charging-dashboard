# 充能有数 — 比亚迪海狮05EV 充电记录看板

个人充电记录静态看板：`generate.py` 从 `charging_records.json` 读取原始数据，生成单文件 `index.html`，部署到 Cloudflare Pages。

线上地址：

- https://charging-dashboard.pages.dev
- https://charging.waylenlifeos.dpdns.org

## 数据源（唯一真相）

- 权威机器数据：本仓库 `charging_records.json`（WorkBuddy/脚本写入后提交，或直接触发 `update.bat`）。
- 人类可读镜像：MYOS 的 `09.个人知识库/Q.汽车/充电记录.json`。
- 每条记录字段：`date / station / gun / duration_min / kwh / amount / start_soc / end_soc / mileage / coupon / order_id / start_time / stop_method / platform`。
- 页面按实际支付金额与桩端充电量计算加权平均电价，不把衍生统计写回 JSON。

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

## 2.0 页面与统计口径

- 浅色充电账本：默认展示最近有记录的月份，可切换全部记录或指定月份。
- 首屏保留实际支付金额、加权平均实付电价和桩端充电量；月度图支持花费／电价切换及点击月份。
- 最近充电、按次数排列的常去站点、历史搜索／站点筛选／排序、分页和 CSV 导出。
- 手机将历史表格转换为紧凑记录卡片；无外部字体、图表库或网络依赖。
- 测试记录由明确的 `is_test: true`、`record_type: test`、连通性自测标记或独立 TEST 标记识别，只从展示与统计中排除，原始 JSON 不变。
- 平均电价 = 实付总金额 ÷ 总充电量；优惠单列，不再次加回实付。
- 不从 SOC 差额推断电池衰减，不做“充电效率”排名；不把单次补电直接当作此前里程的行驶电耗。
- 少量已确认站名在 `generate.py` 的 `ALIASES` 中合并，原始站名仍保留在导出里。

```bash
python -m unittest -v
python generate.py --json-input charging_records.json
```

`dashboard.html`、`dashboard.css`、`dashboard.js` 在生成时内联到 `index.html`。服务器 `/srv/charging` 镜像需要同步这三个文件与 `generate.py`，原有 `receive.py` 无需修改。上线后新增记录仍通过现有 Git 提交触发 Pages 构建。

## 历史（已废弃）

旧版 `server.py`（Flask 读 Excel）与本地隧道方案已不再参与部署，保留在 git 历史与本地备份分支 `backup-local-migration`。

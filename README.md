# 充能有数 · 我的充电账本

动态充电账本，保留浅色的花费、电价和记录概览，新增手动补录。

- 浏览：https://charging.waylenlifeos.dpdns.org/
- 录入：https://charging.waylenlifeos.dpdns.org/admin/
- Pages 旧入口自动转到动态站点。

## 使用

页面打开时读取服务器数据，每 10 秒检查变化，回到页面或恢复网络时立即检查。手动保存后可立即查看对应月份，不用等待 Git 提交或 Pages 构建。

新增记录通过 Cloudflare Access 验证，仅允许本人。必填日期、站点、充电量和优惠后的实付金额；SOC、时长、优惠、里程、平台、订单号选填。未保存的草稿暂存在当前浏览器；相同请求重试不会重复记账，相同订单号或日期／电量／金额会提示核对。

## 数据与兼容

- 在线权威数据：服务器 /srv/charging/charging_records.json。
- 网页和 SSH 上传共用 record_store.py，采用进程锁、原子写入和写前备份。
- 原有 SSH forced command 仍是 /srv/charging/receive.py，转到 current/receive.py；后续上传订单信息可补全手动记录。
- github_sync.py 每 30 秒备份到本仓库并导入仓库新增条目。GitHub 暂时不可用不影响网页保存；旧快照不会覆盖服务器已有记录。
- GitHub JSON 是备份／新增导入渠道，不支持通过修改旧快照删除或覆盖服务器记录。
- MYOS 的 09.个人知识库/Q.汽车/充电记录.json 为原有可读镜像；网页录入目前不直接回写本地知识库。
- 写前备份在 backups/records/。内部请求标识不会进入公开接口或 GitHub 备份。
- GitHub 令牌只保存在服务器数据目录 .github_token（权限 600），不进入代码或浏览器。

## 部署

Python 3.11+，依赖见 requirements.txt。监听 127.0.0.1:43140，经既有 Cloudflare Tunnel 提供 HTTPS。

1. 上传代码到 /srv/charging/releases/<version>，保留数据目录。
2. 独立 venv 从 PyPI HTTPS 安装依赖，运行测试。
3. 创建 charging.env（参考 charging.env.example），填入 Access 团队、应用 AUD、本人邮箱，权限 600。
4. Access 保护 charging.waylenlifeos.dpdns.org/admin 及子路径，关联 Only Waylen 规则。后端另行验证 RS256 签名、issuer、AUD、有效期、邮箱。
5. current 指向发布目录，安装 charging-journal.service 并启动；隧道指向 localhost:43140。
6. 原接收脚本入口转到 current/receive.py，保持 SSH 上传兼容。

上线前备份：/srv/charging/backups/20261001-dynamic/。回滚恢复 receive.py 和前一版本指向，保留 JSON 数据。

## 本地测试

```sh
python -m unittest -v
node --check dashboard.js
node --check admin.js
```

动态预览使用独立目录，放置 .preview-mode 标识：

```sh
python server.py --preview --data-dir ./preview-data --port 43134
```

预览只监听本机，跳过 Access，不同步 GitHub；正式模式要求登录配置。

generate.py 仍可生成单文件 index.html 离线快照。Pages 兼容入口会跳转动态域名。旧 update.bat、deploy.py 只用于 Pages，不能发布动态服务。

## 页面与统计口径

- 默认最近有记录的月份，可切换全部或指定月份；同步时保留筛选。
- 实际支付金额、加权平均实付电价、桩端充电量；趋势支持花费／电价切换及点击月份。
- 最近充电、常去站点、历史搜索／筛选／排序、分页、CSV 导出；手机使用记录卡片。
- 明确 is_test: true、record_type: test、连通性自测或独立 TEST 标记仅从展示统计中排除，原始记录保留。
- 平均电价 = 实付总金额 ÷ 总充电量；优惠单列，不加回实付。
- 不用 SOC 差额推断电池衰减，不做充电效率排名，不把单次补电当作行驶电耗。
- 少量已确认站名通过 generate.py 的 ALIASES 合并，原始名称保留在导出中。

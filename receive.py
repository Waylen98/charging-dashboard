#!/usr/bin/env python3
"""
充电记录接收脚本 —— 部署在云服务器上，通过 SSH forced command 调用。

用法（stdin 传入一条 JSON 记录）：
    echo '{"date":"2026-09-10","station":"...","kwh":40.5,"amount":32.4,...}' | python3 receive.py

流程：
  1. 从 GitHub Contents API 拉取当前 charging_records.json（以远端为准，防止覆盖他处更新）
  2. 追加/更新该记录（按 order_id 或 日期+电量+金额 去重），按日期排序
  3. 本地重新生成 index.html（镜像备份）
  4. 通过 Contents API 提交到 main -> Cloudflare 自动构建上线

无第三方依赖，仅 Python 标准库。令牌从同目录 .github_token 读取（chmod 600）。
"""
import base64
import json
import re
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

BASE = Path(__file__).resolve().parent
DATA_FILE = BASE / "charging_records.json"
TOKEN_FILE = BASE / ".github_token"
API_URL = "https://api.github.com/repos/Waylen98/charging-dashboard/contents/charging_records.json"
BRANCH = "main"

# 字段规范：按此顺序输出，数字不加引号
FIELD_ORDER = ["date", "station", "gun", "duration_min", "kwh", "amount",
               "start_soc", "end_soc", "mileage", "coupon",
               "order_id", "start_time", "stop_method", "platform"]
REQUIRED = ("date", "station", "kwh", "amount")
NUMERIC = {"duration_min", "kwh", "amount", "start_soc", "end_soc", "mileage", "coupon"}


def die(msg):
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(1)


def gh_api(method, payload=None):
    token = TOKEN_FILE.read_text(encoding="utf-8").strip()
    req = urllib.request.Request(API_URL, method=method)
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Accept", "application/vnd.github+json")
    data = None
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, data=data, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")[:300]
        die(f"GitHub API {e.code}: {body}")


def normalize(raw):
    rec = {k: raw[k] for k in FIELD_ORDER if raw.get(k) not in (None, "")}
    missing = [k for k in REQUIRED if k not in rec]
    if missing:
        die(f"缺少必填字段: {', '.join(missing)}")
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(rec["date"])):
        die(f"日期格式错误: {rec['date']}（应为 YYYY-MM-DD）")
    for k in NUMERIC:
        if k in rec:
            try:
                v = float(rec[k])
                rec[k] = int(v) if v == int(v) else v
            except (TypeError, ValueError):
                die(f"字段 {k} 不是数字: {rec[k]}")
    return rec


def is_same_record(a, b):
    if a.get("order_id") and b.get("order_id"):
        return a["order_id"] == b["order_id"]
    return (a.get("date"), a.get("kwh"), a.get("amount")) == (b.get("date"), b.get("kwh"), b.get("amount"))


def main():
    try:
        raw = json.load(sys.stdin)
    except json.JSONDecodeError as e:
        die(f"stdin 不是合法 JSON: {e}")
    if not isinstance(raw, dict):
        die("stdin 应为单条记录对象，不是数组")
    rec = normalize(raw)

    # 1. 以远端为基准
    cur = gh_api("GET")
    records = json.loads(base64.b64decode(cur["content"]).decode("utf-8"))

    # 2. 去重追加 + 排序
    action = "added"
    kept = []
    for r in records:
        if is_same_record(r, rec):
            action = "updated"
            continue
        kept.append(r)
    kept.append(rec)
    kept.sort(key=lambda r: str(r.get("date", "")))

    new_json = json.dumps(kept, ensure_ascii=False, indent=2) + "\n"

    # 3. 本地镜像：数据 + 生成的页面
    DATA_FILE.write_text(new_json, encoding="utf-8")
    gen = subprocess.run(
        [sys.executable, str(BASE / "generate.py"), "--json-input", str(DATA_FILE)],
        cwd=BASE, capture_output=True, text=True)
    if gen.returncode != 0:
        die(f"generate.py 失败: {gen.stderr[:300]}")

    # 4. 提交到 GitHub（内容有变化才提交）
    new_b64 = base64.b64encode(new_json.encode("utf-8")).decode("ascii")
    if new_b64 == cur["content"].replace("\n", ""):
        print(json.dumps({"status": "ok", "action": "no-change", "date": rec["date"],
                          "records": len(kept)}, ensure_ascii=False))
        return
    res = gh_api("PUT", {
        "message": f"chore: {action} charging record {rec['date']} {rec.get('station', '')}".strip(),
        "content": new_b64,
        "sha": cur["sha"],
        "branch": BRANCH,
    })
    print(json.dumps({"status": "ok", "action": action, "date": rec["date"],
                      "commit": res.get("commit", {}).get("sha", "?"),
                      "records": len(kept),
                      "live": "https://charging-dashboard.pages.dev"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
"""Build the charging journal. Raw records remain the only source of truth."""
import argparse
import hashlib
import json
import math
import re
from datetime import date
from pathlib import Path

BASE = Path(__file__).resolve().parent
DATA_PATH = BASE / "charging_records.json"
OUTPUT_PATH = BASE / "index.html"
VERSION = "3.0.0"
ALIASES = {
    "莲城充电-体育中心二期": "莲城充电·体育中心二期",
    "莲城充电-体育中心二期充电站": "莲城充电·体育中心二期",
    "风景园林二队超充站": "莲城充电·风景园林二队",
    "莲城充电-风景园林二队超充站": "莲城充电·风景园林二队",
}


def number(value):
    if value is None or value == "" or isinstance(value, bool):
        return None
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except (ValueError, TypeError):
        return None


def is_test_record(record):
    station = str(record.get("station", ""))
    return (record.get("is_test") is True or record.get("record_type") == "test"
            or "连通性自测" in station
            or re.search(r"(?:^|[-_\s])TEST(?:[-_\s]|$)", station, re.I) is not None)


def load_records(path):
    raw = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    if not isinstance(raw, list):
        raise ValueError("charging_records.json must contain an array")
    records, excluded = [], {"test": 0, "invalid": 0}
    for item in raw:
        if not isinstance(item, dict):
            excluded["invalid"] += 1
            continue
        if is_test_record(item):
            excluded["test"] += 1
            continue
        value = str(item.get("date", ""))
        try:
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
                raise ValueError("Invalid date")
            date.fromisoformat(value)
        except ValueError:
            excluded["invalid"] += 1
            continue
        kwh, amount = number(item.get("kwh")), number(item.get("amount"))
        if kwh is None or kwh <= 0 or amount is None or amount < 0:
            excluded["invalid"] += 1
            continue
        original = str(item.get("station", "")).strip()
        station = ALIASES.get(original, original) if original not in ("", "-") else "未记录站点"
        start, end = number(item.get("start_soc")), number(item.get("end_soc"))
        if start is not None and not 0 <= start <= 100:
            start = None
        if end is not None and not 0 <= end <= 100:
            end = None
        duration = number(item.get("duration_min"))
        mileage = number(item.get("mileage"))
        coupon = number(item.get("coupon"))
        records.append({
            "date": value, "station": station, "original_station": original,
            "kwh": kwh, "amount": amount, "coupon": max(coupon or 0, 0),
            "unit_price": amount / kwh, "start_soc": start, "end_soc": end,
            "duration_min": duration if duration is not None and duration > 0 else None,
            "mileage": mileage if mileage is not None and mileage >= 0 else None,
            "platform": str(item.get("platform", "")).strip(),
        })
    records.sort(key=lambda r: r["date"])
    return records, excluded


def read_json(path):
    """Compatibility entry point for existing tools importing the generator."""
    return load_records(path)[0]


def compute_summary(records):
    kwh = sum(r["kwh"] for r in records)
    amount = sum(r["amount"] for r in records)
    return {"total_charges": len(records), "total_kwh": kwh, "total_amount": amount,
            "total_coupon": sum(r["coupon"] for r in records),
            "avg_price": amount / kwh if kwh else None,
            "first_date": records[0]["date"] if records else None,
            "latest_date": records[-1]["date"] if records else None}


def safe_json(data):
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"), allow_nan=False).replace("<", "\\u003c").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")


def render(records, summary=None, excluded=None):
    public_data = {"version": VERSION, "records": records,
                   "excluded": excluded or {"test": 0, "invalid": 0}}
    public_data["revision"] = hashlib.sha256(safe_json(public_data).encode()).hexdigest()[:12]
    template = (BASE / "dashboard.html").read_text(encoding="utf-8")
    return (template.replace("<!-- INLINE_STYLE -->", "<style>" + (BASE / "dashboard.css").read_text(encoding="utf-8") + "</style>")
            .replace("<!-- INLINE_DATA -->", '<script type="application/json" id="charging-data">' + safe_json(public_data) + '</script>')
            .replace("<!-- INLINE_APP -->", "<script>" + (BASE / "dashboard.js").read_text(encoding="utf-8") + "</script>"))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build the charging journal from JSON.")
    parser.add_argument("--json-input", default=str(DATA_PATH))
    parser.add_argument("--output", default=str(OUTPUT_PATH))
    args = parser.parse_args()
    records, excluded = load_records(args.json_input)
    page = render(records, excluded=excluded)
    Path(args.output).write_text(page, encoding="utf-8")
    print(f"Generated charging journal v{VERSION}: {len(records)} records; excluded {excluded}; {len(page.encode())} bytes")

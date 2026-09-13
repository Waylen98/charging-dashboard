"""
Static site generator for charging dashboard.
Reads raw charging records from a JSON file and renders a self-contained index.html.
Computed fields (unit_price, efficiency, pile_loss, etc.) are derived here, not stored in JSON.
"""
import json
from datetime import datetime
from pathlib import Path

DATA_PATH = Path(__file__).parent / "charging_records.json"
OUTPUT_PATH = Path(__file__).parent / "index.html"
BATTERY_CAPACITY = 60.9


def read_json(path):
    """Read records from a JSON file. Each record is a flat dict with raw charging data.
    Computed fields (driven_km, efficiency, etc.) are calculated here, same as read_excel."""
    with open(path, "r", encoding="utf-8") as f:
        raw_records = json.load(f)

    rows = []
    prev_mileage = None

    for r in raw_records:
        date_str = r.get("date", "")
        station = r.get("station", "")
        gun = r.get("gun", "")
        duration_min = r.get("duration_min")
        kwh = float(r["kwh"]) if r.get("kwh") else 0
        amount = float(r["amount"]) if r.get("amount") else 0
        unit_price = round(amount / kwh, 2) if kwh > 0 else 0
        start_soc = float(r["start_soc"]) if r.get("start_soc") not in (None, "") else None
        end_soc = float(r["end_soc"]) if r.get("end_soc") not in (None, "") else None
        mileage = float(r["mileage"]) if r.get("mileage") not in (None, "") else None
        coupon = float(r.get("coupon", 0)) if r.get("coupon") not in (None, "") else 0

        driven_km = round(mileage - prev_mileage, 1) if mileage and prev_mileage else None
        real_consumption = round(kwh / driven_km * 100, 2) if driven_km and driven_km > 0 and kwh > 0 else None
        battery_calc = round(BATTERY_CAPACITY * (end_soc - start_soc) / 100, 2) if start_soc is not None and end_soc is not None else None
        pile_loss = round(kwh - battery_calc, 2) if battery_calc is not None and battery_calc > 0 and kwh > 0 else None
        loss_rate = round(abs(pile_loss) / kwh * 100, 1) if pile_loss is not None and kwh > 0 else None
        soc_change = end_soc - start_soc if start_soc is not None and end_soc is not None else None
        efficiency = round(kwh / (soc_change / 100 * BATTERY_CAPACITY), 2) if soc_change and soc_change > 0 and kwh > 0 else None
        cost_per_km = round(amount / driven_km, 3) if driven_km and driven_km > 0 and amount > 0 else None
        effective_unit_price = round((amount + coupon) / kwh, 2) if kwh > 0 else 0

        rows.append({
            "date": date_str, "station": station, "gun": gun,
            "duration_min": duration_min, "kwh": kwh, "amount": amount,
            "unit_price": unit_price, "start_soc": start_soc, "end_soc": end_soc,
            "mileage": mileage, "driven_km": driven_km, "real_consumption": real_consumption,
            "battery_calc_kwh": battery_calc, "pile_loss": pile_loss, "loss_rate": loss_rate,
            "order_id": r.get("order_id", ""), "start_time": r.get("start_time", ""),
            "stop_method": r.get("stop_method", ""), "platform": r.get("platform", ""),
            "coupon": coupon, "effective_unit_price": effective_unit_price,
            "efficiency": efficiency, "cost_per_km": cost_per_km,
        })
        prev_mileage = mileage

    return rows


def compute_summary(records):
    total = len(records)
    total_kwh = round(sum(r["kwh"] for r in records), 2)
    total_amount = round(sum(r["amount"] for r in records), 2)
    total_coupon = round(sum(r["coupon"] for r in records), 2)
    avg_price = round(total_amount / total_kwh, 2) if total_kwh > 0 else 0
    avg_per_charge = round(total_amount / total, 2) if total > 0 else 0

    total_minutes = sum(r["duration_min"] or 0 for r in records)
    total_hours = round(total_minutes / 60, 1)
    avg_duration_hours = round(total_hours / total, 1) if total > 0 else 0
    hours_int = int(total_hours)
    mins_int = int((total_hours - hours_int) * 60)

    dates_with_data = []
    for r in records:
        if r["date"]:
            try:
                dates_with_data.append(datetime.strptime(r["date"], "%Y-%m-%d"))
            except:
                pass
    avg_interval_days = None
    total_days = None
    if len(dates_with_data) >= 2:
        dates_with_data.sort()
        intervals = [ (dates_with_data[i]-dates_with_data[i-1]).days for i in range(1, len(dates_with_data)) ]
        avg_interval_days = round(sum(intervals)/len(intervals), 1)
        total_days = (dates_with_data[-1] - dates_with_data[0]).days + 1

    soc_records = [r for r in records if r["start_soc"] is not None and r["end_soc"] is not None]
    total_battery_kwh = round(sum(r["battery_calc_kwh"] or 0 for r in soc_records), 2)
    total_pile_kwh = round(sum(r["kwh"] for r in soc_records), 2)
    total_pile_loss = round(total_pile_kwh - total_battery_kwh, 2)
    avg_loss_rate = round(abs(total_pile_loss) / total_pile_kwh * 100, 1) if total_pile_kwh > 0 else 0

    mile_records = [r for r in records if r["driven_km"] and r["driven_km"] > 0]
    total_driven = round(sum(r["driven_km"] for r in mile_records), 1)
    avg_consumption = None
    if mile_records:
        total_kwh_m = sum(r["kwh"] for r in mile_records)
        avg_consumption = round(total_kwh_m / total_driven * 100, 2) if total_driven > 0 else None

    km_per_kwh = round(total_driven / total_kwh, 2) if total_driven > 0 and total_kwh > 0 else None
    cost_per_100km = round(total_amount / total_driven * 100, 2) if total_driven > 0 and total_amount > 0 else None

    # SOC drift: cumulative pile_loss over time
    soc_drift = []
    cum_loss = 0
    for r in records:
        if r["start_soc"] is not None and r["end_soc"] is not None and r["battery_calc_kwh"] and r["battery_calc_kwh"] > 0:
            cum_loss += r["pile_loss"] or 0
            soc_drift.append({
                "date": r["date"],
                "pile_loss": round(r["pile_loss"], 2),
                "cumulative_loss": round(cum_loss, 2),
                "loss_rate": r["loss_rate"],
            })

    # Charging efficiency stats
    eff_records = [r for r in records if r["efficiency"] is not None]
    avg_efficiency = round(sum(r["efficiency"] for r in eff_records) / len(eff_records), 3) if eff_records else None
    best_efficiency = max(eff_records, key=lambda r: r["efficiency"]) if eff_records else None
    worst_efficiency = min(eff_records, key=lambda r: r["efficiency"]) if eff_records else None

    # Efficiency ranking for display
    efficiency_ranking = sorted(
        [{"date": r["date"], "station": r["station"], "efficiency": r["efficiency"],
          "kwh": r["kwh"], "soc_change": (r["end_soc"]-r["start_soc"]) if r["start_soc"] is not None else None}
         for r in eff_records],
        key=lambda x: x["efficiency"], reverse=True
    )

    # Build efficiency trend data for chart
    efficiency_trend = [{"date": r["date"], "efficiency": r["efficiency"]} for r in records if r["efficiency"] is not None]

    # Cost per km trend
    cost_per_km_trend = [{"date": r["date"], "cost_per_km": r["cost_per_km"]} for r in records if r["cost_per_km"] is not None]

    # Real consumption trend (kWh/100km, excludes electricity price influence)
    consumption_trend = [{"date": r["date"], "consumption": r["real_consumption"]} for r in records if r["real_consumption"] is not None]

    latest = records[-1] if records else None
    total_mileage = latest["mileage"] if latest and latest["mileage"] else None

    spend_trend = [{"date": r["date"], "amount": r["amount"]} for r in records if r["date"] and r["amount"]]
    charge_calendar = {r["date"]: 1 for r in records if r["date"]}

    first_date = dates_with_data[0].strftime("%Y-%m-%d") if dates_with_data else ""

    return {
        "total_charges": total,
        "total_kwh": total_kwh,
        "total_amount": total_amount,
        "total_coupon": total_coupon,
        "avg_price": avg_price,
        "avg_per_charge": avg_per_charge,
        "total_hours": total_hours,
        "total_hours_int": hours_int,
        "total_mins_int": mins_int,
        "avg_duration_hours": avg_duration_hours,
        "avg_interval_days": avg_interval_days,
        "total_days": total_days,
        "total_driven": total_driven,
        "total_mileage": total_mileage,
        "avg_consumption": avg_consumption,
        "cost_per_100km": cost_per_100km,
        "km_per_kwh": km_per_kwh,
        "total_pile_loss": total_pile_loss,
        "avg_loss_rate": avg_loss_rate,
        "soc_record_count": len(soc_records),
        "soc_drift": soc_drift,
        "avg_efficiency": avg_efficiency,
        "best_efficiency": best_efficiency,
        "worst_efficiency": worst_efficiency,
        "efficiency_ranking": efficiency_ranking,
        "efficiency_trend": efficiency_trend,
        "cost_per_km_trend": cost_per_km_trend,
        "consumption_trend": consumption_trend,
        "latest": latest,
        "battery_capacity": BATTERY_CAPACITY,
        "vehicle": "比亚迪海狮05EV",
        "spend_trend": spend_trend,
        "charge_calendar": charge_calendar,
        "first_date": first_date,
    }


def render(records, summary):
    """Render static HTML with embedded JSON data"""
    recs_json = json.dumps(list(reversed(records)), ensure_ascii=False, default=str)
    summary_json = json.dumps(summary, ensure_ascii=False, default=str)

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
<title>充能有数 - 海狮05EV</title>
<style>
*,*::before,*::after{{box-sizing:border-box;margin:0;padding:0}}
:root{{--bg:#f0f4f3;--card:#fff;--primary:#0d9488;--primary-light:#e6f7f5;--primary-dark:#0f766e;--text:#1e293b;--text2:#64748b;--text3:#94a3b8;--border:#e8edec;--green:#0d9488;--orange:#f59e0b;--red:#ef4444;--blue:#3b82f6;--purple:#8b5cf6;--coupon-bg:#fef3c7;--coupon-text:#b45309}}
body{{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif;background:var(--bg);color:var(--text);line-height:1.5;min-height:100vh;padding-bottom:24px;-webkit-font-smoothing:antialiased}}
.top-nav{{background:var(--bg);padding:12px 16px 0;display:flex;align-items:center;gap:10px}}
.avatar{{width:36px;height:36px;border-radius:50%;background:linear-gradient(135deg,var(--primary),var(--primary-dark));display:flex;align-items:center;justify-content:center;color:#fff;font-size:16px;font-weight:600}}
.greeting{{font-size:17px;font-weight:600}}.name{{font-size:12px;color:var(--text2)}}
.hero{{margin:10px 12px 0;background:linear-gradient(135deg,#0d9488 0%,#0891b2 100%);border-radius:16px;padding:22px 20px;color:#fff}}
.hero .label{{font-size:12px;opacity:0.85;font-weight:400}}
.hero .amount{{font-size:38px;font-weight:700;margin:4px 0 8px;line-height:1.1}}
.hero .meta{{display:flex;gap:20px;font-size:12px;opacity:0.8;flex-wrap:wrap}}
.updated{{text-align:center;padding:6px 16px 0;font-size:11px;color:var(--text3)}}
.section-title{{padding:16px 16px 6px;font-size:13px;font-weight:600;display:flex;align-items:center;gap:6px}}
.insight-grid{{display:grid;grid-template-columns:1fr 1fr 1fr;gap:1px;margin:0 12px;background:var(--border);border-radius:12px;overflow:hidden}}
.insight-item{{background:var(--card);padding:14px 10px;text-align:center}}
.insight-item .val{{font-size:18px;font-weight:700;line-height:1.3}}
.insight-item .val .unit{{font-size:12px;font-weight:400;color:var(--text2)}}
.insight-item .lbl{{font-size:10px;color:var(--text3);margin-top:2px}}
.val.green{{color:var(--green)}}.val.orange{{color:var(--orange)}}.val.red{{color:var(--red)}}.val.purple{{color:var(--purple)}}.val.muted{{color:var(--text3)}}
.trend-section{{margin:0 12px;background:var(--card);border-radius:12px;padding:14px;margin-top:10px}}
.trend-header{{display:flex;justify-content:space-between;align-items:center;margin-bottom:8px}}
.trend-header .title{{font-size:12px;font-weight:600;color:var(--text2)}}
.trend-header .unit{{font-size:10px;color:var(--text3)}}
.trend-chart{{width:100%;height:160px}} .trend-chart svg{{width:100%;height:100%}}
.trend-chart-sm{{width:100%;height:120px}} .trend-chart-sm svg{{width:100%;height:100%}}
.cal-section{{margin:0 12px;background:var(--card);border-radius:12px;padding:14px;margin-top:10px}}
.cal-header{{display:flex;justify-content:space-between;align-items:center;margin-bottom:10px}}
.cal-header .title{{font-size:12px;font-weight:600;color:var(--text)}}
.cal-nav{{display:flex;align-items:center;gap:14px}}
.cal-nav .month{{font-size:13px;font-weight:600;min-width:40px;text-align:center}}
.cal-nav .arrow{{font-size:16px;color:var(--primary);cursor:pointer;user-select:none;padding:0 4px}}
.cal-grid{{display:grid;grid-template-columns:repeat(7,1fr);text-align:center;gap:3px}}
.cal-grid .day-header{{font-size:10px;color:var(--text3);padding:4px 0;font-weight:500}}
.cal-grid .day{{font-size:12px;padding:6px 0;border-radius:6px}}.cal-grid .day.charged{{background:var(--primary);color:#fff;font-weight:600}}
.cal-grid .day.empty{{color:#cbd5e1}}.cal-grid .day.weekend{{color:var(--red)}}.cal-grid .day.weekend.charged{{color:#fff}}
.latest-card{{margin:0 12px;background:var(--card);border-radius:12px;padding:14px}}
.latest-card .station{{font-size:14px;font-weight:600;margin-bottom:6px}}
.latest-card .stats{{display:flex;gap:14px;flex-wrap:wrap;font-size:12px;color:var(--text2)}}
.latest-card .stats b{{color:var(--text)}}
.coupon-badge{{display:inline-block;background:var(--coupon-bg);color:var(--coupon-text);padding:2px 8px;border-radius:10px;font-size:10px;font-weight:600;vertical-align:middle}}
.save-total{{background:linear-gradient(135deg,#fef3c7,#fffbeb);border:1px solid #fde68a;border-radius:10px;padding:10px 14px;margin:8px 12px 0;font-size:12px;display:flex;align-items:center;gap:8px}}
.save-total .save-icon{{font-size:18px}}.save-total .save-amount{{font-weight:700;color:var(--coupon-text);font-size:16px}}
.ranking-item{{display:flex;align-items:center;gap:8px;padding:6px 12px;border-bottom:1px solid var(--border);font-size:11px}}
.ranking-item:last-child{{border-bottom:none}}
.ranking-item .rank{{font-size:16px;font-weight:700;min-width:24px;text-align:center}}
.ranking-item .rank.gold{{color:var(--orange)}}.ranking-item .rank.silver{{color:var(--text3)}}.ranking-item .rank.bronze{{color:#d97706}}
.ranking-item .info{{flex:1;min-width:0}}
.ranking-item .info .eff{{font-weight:600;font-size:13px}}
.ranking-item .info .sub{{font-size:10px;color:var(--text3);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
.table-section{{margin:0 12px}}
.table-wrap{{background:var(--card);border-radius:12px;overflow:hidden;margin-top:10px}}
table{{width:100%;border-collapse:collapse;font-size:12px}}
thead{{background:#f8faf9}}
th{{padding:10px 8px;text-align:left;font-weight:600;font-size:11px;color:var(--text2);border-bottom:1px solid var(--border)}}
td{{padding:10px 8px;border-bottom:1px solid var(--border)}}
tr:last-child td{{border-bottom:none}} td.amount{{color:var(--red);font-weight:600}} td.kwh{{font-weight:600}}
.tag{{display:inline-block;padding:2px 6px;border-radius:4px;font-size:10px;font-weight:600}}
.tag-ok{{background:#dcfce7;color:#15803d}}.tag-hi{{background:#fef3c7;color:#b45309}}.tag-neg{{background:#fee2e2;color:#b91c1c}}
.scroll-hint{{text-align:center;font-size:10px;color:var(--text3);padding:4px 0}}
</style>
</head>
<body>

<div class="top-nav">
  <div class="avatar">W</div>
  <div><div class="greeting">充能有数</div><div class="name">{summary["vehicle"]}</div></div>
</div>

<div class="hero">
  <div class="label">累计充电支出</div>
  <div class="amount">¥{summary["total_amount"]:.2f}</div>
  <div class="meta">
    <span>已记录 {summary["total_days"] or "-"}天</span>
    {f'<span>{summary["total_mileage"]:.0f}km 总里程</span>' if summary["total_mileage"] else ''}
    {f'<span>优惠券 ¥{summary["total_coupon"]:.0f}</span>' if summary["total_coupon"] > 0 else ''}
  </div>
</div>
<div class="updated">* 从 {summary["first_date"]} 开始记录，累计 {summary["total_charges"]} 次充电</div>

{f'''<div class="save-total"><span class="save-icon">🎫</span><span>累计优惠券节省 <span class="save-amount">¥{summary["total_coupon"]:.0f}</span>，实际总支出 ¥{summary["total_amount"]:.2f}</span></div>''' if summary["total_coupon"] > 0 else ''}

<div class="section-title">📊 数据洞察</div>
<div class="insight-grid">
  <div class="insight-item"><div class="val">{summary["total_kwh"]:.1f}<span class="unit">kWh</span></div><div class="lbl">累计电量</div></div>
  <div class="insight-item"><div class="val">{summary["total_charges"]}<span class="unit">次</span></div><div class="lbl">累计充电</div></div>
  <div class="insight-item"><div class="val">¥{summary["avg_price"]:.2f}<span class="unit">/度</span></div><div class="lbl">平均单价</div></div>
  <div class="insight-item"><div class="val">¥{summary["avg_per_charge"]:.2f}<span class="unit">/次</span></div><div class="lbl">次均花费</div></div>
  <div class="insight-item"><div class="val">{f'¥{summary["cost_per_100km"]:.2f}<span class="unit">/百km</span>' if summary["cost_per_100km"] else '<span class="unit muted">--</span>'}</div><div class="lbl">百公里花费</div></div>
  <div class="insight-item"><div class="val {_consume_class(summary)}">{f'{summary["avg_consumption"]:.1f}<span class="unit">kWh</span>' if summary["avg_consumption"] else '<span class="unit muted">--</span>'}</div><div class="lbl">百公里电耗</div></div>
  <div class="insight-item"><div class="val">{f'{summary["total_hours_int"]}h{summary["total_mins_int"]}min<span class="unit"></span>' if summary["total_hours"] > 0 else '<span class="unit muted">--</span>'}</div><div class="lbl">总充电时长</div></div>
  <div class="insight-item"><div class="val">{f'{summary["km_per_kwh"]:.1f}<span class="unit">km/kWh</span>' if summary["km_per_kwh"] else '<span class="unit muted">--</span>'}</div><div class="lbl">每度电驱动</div></div>
  <div class="insight-item"><div class="val">{f'{summary["avg_interval_days"]:.1f}<span class="unit">天</span>' if summary["avg_interval_days"] else '<span class="unit muted">--</span>'}</div><div class="lbl">平均间隔</div></div>
</div>

<div class="insight-grid" style="margin-top:1px">
  <div class="insight-item"><div class="val">{f'{summary["avg_duration_hours"]:.1f}<span class="unit">h/次</span>' if summary["avg_duration_hours"] > 0 else '<span class="unit muted">--</span>'}</div><div class="lbl">次均时长</div></div>
  <div class="insight-item"><div class="val">{f'<span class="orange">{abs(summary["total_pile_loss"]):.1f}<span class="unit">kWh</span></span>' if summary["total_pile_loss"] is not None else '<span class="unit muted">--</span>'}</div><div class="lbl">累计桩偏差</div></div>
  <div class="insight-item"><div class="val"><span class="{_loss_class(summary)}">{f'{summary["avg_loss_rate"]:.1f}<span class="unit">%</span>' if summary["avg_loss_rate"] else '<span class="unit muted">--</span>'}</span></div><div class="lbl">平均偏差率</div></div>
</div>

{f'''<div class="insight-grid" style="margin-top:1px">
  <div class="insight-item"><div class="val"><span class="{_eff_class(summary)}">{f'{summary["avg_efficiency"]:.2f}<span class="unit">x</span>' if summary["avg_efficiency"] else '<span class="unit muted">--</span>'}</span></div><div class="lbl">平均充电效率</div></div>
  <div class="insight-item"><div class="val"><span class="green">{f'{summary["best_efficiency"]["efficiency"]:.2f}<span class="unit">x</span>' if summary["best_efficiency"] else '<span class="unit muted">--</span>'}</span></div><div class="lbl">最佳效率</div></div>
  <div class="insight-item"><div class="val"><span class="red">{f'{summary["worst_efficiency"]["efficiency"]:.2f}<span class="unit">x</span>' if summary["worst_efficiency"] else '<span class="unit muted">--</span>'}</span></div><div class="lbl">最差效率</div></div>
</div>''' if summary["avg_efficiency"] else ''}

<div class="trend-section">
  <div class="trend-header"><span class="title">💰 花费趋势</span><span class="unit">元/次</span></div>
  <div class="trend-chart" id="trendChart"></div>
</div>

{f'''<div class="trend-section">
  <div class="trend-header"><span class="title">🔋 SOC 累计偏差 (桩损耗累加)</span><span class="unit">kWh</span></div>
  <div class="trend-chart-sm" id="driftChart"></div>
  <div style="font-size:10px;color:var(--text3);margin-top:6px">累计偏差{"+" if summary["total_pile_loss"]>0 else ""}{summary["total_pile_loss"]}kWh · 趋势上升=电池可能在衰减 · 平稳=正常波动</div>
</div>''' if summary["soc_drift"] and len(summary["soc_drift"]) >= 2 else ''}

{f'''<div class="trend-section">
  <div class="trend-header"><span class="title">⚡ 充电效率趋势 (实际/理论)</span><span class="unit">&gt;1=桩多充了 &lt;1=桩少充了</span></div>
  <div class="trend-chart-sm" id="effChart"></div>
</div>''' if summary["efficiency_trend"] and len(summary["efficiency_trend"]) >= 2 else ''}

{f'''<div class="trend-section">
  <div class="trend-header"><span class="title">📉 每公里成本</span><span class="unit">元/km</span></div>
  <div class="trend-chart-sm" id="costKmChart"></div>
</div>''' if summary["cost_per_km_trend"] and len(summary["cost_per_km_trend"]) >= 2 else ''}

{f'''<div class="trend-section">
  <div class="trend-header"><span class="title">⚡ 百公里电耗趋势</span><span class="unit">kWh/百km · 排除电价影响</span></div>
  <div class="trend-chart-sm" id="consChart"></div>
</div>''' if summary["consumption_trend"] and len(summary["consumption_trend"]) >= 2 else ''}

<div class="cal-section">
  <div class="cal-header">
    <span class="title">📅 充电日历</span>
    <div class="cal-nav">
      <span class="arrow" id="calPrev">&lt;</span>
      <span class="month" id="calMonth"></span>
      <span class="arrow" id="calNext">&gt;</span>
    </div>
  </div>
  <div class="cal-grid" id="calGrid"></div>
</div>

{f'''<div class="section-title">🏆 充电效率排行</div>
<div class="table-section">
  <div class="table-wrap" style="margin-top:0">
    {_render_ranking(summary["efficiency_ranking"])}
  </div>
</div>''' if summary["efficiency_ranking"] and len(summary["efficiency_ranking"]) >= 2 else ''}

{f'''<div class="section-title">最近充电</div>
<div class="latest-card">
  <div class="station">{summary["latest"]["date"]} - {summary["latest"]["station"]}{f' <span class="coupon-badge">🎫 -¥{summary["latest"]["coupon"]:.0f}</span>' if summary["latest"]["coupon"] > 0 else ''}</div>
  <div class="stats">
    <span>电量 <b>{summary["latest"]["kwh"]} kWh</b></span>
    <span>金额 <b>¥{summary["latest"]["amount"]:.2f}</b></span>
    <span>单价 ¥{summary["latest"]["unit_price"]:.2f}/度</span>
    {f'<span>SOC {summary["latest"]["start_soc"]:.0f}% → {summary["latest"]["end_soc"]:.0f}%</span>' if summary["latest"]["start_soc"] is not None and summary["latest"]["end_soc"] is not None else ''}
    {f'<span>效率 <b>{summary["latest"]["efficiency"]:.2f}x</b></span>' if summary["latest"]["efficiency"] else ''}
  </div>
</div>''' if summary["latest"] else ''}

<div class="section-title">📋 充电历史</div>
<div class="table-section">
  <div class="table-wrap" style="overflow-x:auto">
    <table>
      <thead><tr><th>日期</th><th>充电站</th><th>电量</th><th>金额</th><th>单价</th><th>SOC</th><th>效率</th><th>损耗</th><th></th></tr></thead>
      <tbody>
        {_render_rows(records)}
      </tbody>
    </table>
  </div>
  <div class="scroll-hint">← 左右滑动查看 →</div>
</div>

<script>
var DATA = {recs_json};
var SUMMARY = {summary_json};
</script>
<script>
(function(){{
  var d=DATA,s=SUMMARY;

  // Calendar
  var charged=s.charge_calendar||{{}};
  var now=new Date();
  var calYear=now.getFullYear(),calMonth=now.getMonth();
  function renderCal(){{
    var fd=new Date(calYear,calMonth,1),ld=new Date(calYear,calMonth+1,0);
    var sd=fd.getDay(),dim=ld.getDate();
    document.getElementById('calMonth').textContent=(calMonth+1)+'月';
    var h='<div class="day-header">日</div><div class="day-header">一</div><div class="day-header">二</div><div class="day-header">三</div><div class="day-header">四</div><div class="day-header">五</div><div class="day-header">六</div>';
    for(var i=0;i<sd;i++) h+='<div class="day empty"></div>';
    for(var d=1;d<=dim;d++){{
      var ds=calYear+'-'+String(calMonth+1).padStart(2,'0')+'-'+String(d).padStart(2,'0');
      var isC=charged[ds],dow=(sd+d-1)%7;
      var cls='day'+(isC?' charged':(dow===0||dow===6?' weekend':''));
      h+='<div class="'+cls+'">'+d+'</div>';
    }}
    document.getElementById('calGrid').innerHTML=h;
  }}
  document.getElementById('calPrev').onclick=function(){{calMonth--;if(calMonth<0){{calMonth=11;calYear--}}renderCal()}};
  document.getElementById('calNext').onclick=function(){{calMonth++;if(calMonth>11){{calMonth=0;calYear++}}renderCal()}};
  renderCal();

  // Trend draw helper
  function drawTrend(containerId, data, valueKey, color, unit, height, yDecimals) {{
    var el = document.getElementById(containerId);
    if (!el || !data || !data.length) return;
    var svgNS='http://www.w3.org/2000/svg';
    var svg=document.createElementNS(svgNS,'svg');
    svg.setAttribute('viewBox','0 0 360 '+height);
    svg.setAttribute('preserveAspectRatio','xMidYMid meet');
    svg.style.width='100%';svg.style.height='100%';
    var pad={{top:6,right:10,bottom:18,left:50}},w=360,h=height;
    var cw=w-pad.left-pad.right,ch=h-pad.top-pad.bottom;
    var vals=data.map(function(r){{return r[valueKey]}});
    var max=Math.max.apply(null,vals),min=Math.min.apply(null,vals);
    var rng=(max-min)||1;

    // Zero line for drift chart
    var zeroY = null;
    if (min < 0 && max > 0) {{
      zeroY = pad.top + ch * (max / rng);
      var zl=document.createElementNS(svgNS,'line');
      zl.setAttribute('x1',pad.left);zl.setAttribute('x2',w-pad.right);
      zl.setAttribute('y1',zeroY);zl.setAttribute('y2',zeroY);
      zl.setAttribute('stroke','#e2e8f0');zl.setAttribute('stroke-width','1');
      zl.setAttribute('stroke-dasharray','4,3');
      svg.appendChild(zl);
    }}

    for(var i=0;i<=4;i++){{
      var val=min+rng*i/4;
      var y=pad.top+ch-(ch*i/4);
      var t=document.createElementNS(svgNS,'text');
      t.setAttribute('x',pad.left-6);t.setAttribute('y',y+3);
      t.setAttribute('text-anchor','end');t.setAttribute('fill','#94a3b8');
      t.setAttribute('font-size','9');t.textContent=val.toFixed(yDecimals||0);
      svg.appendChild(t);
    }}

    data.forEach(function(d,i){{
      if(i%Math.max(Math.floor(data.length/6),1)===0 || i===data.length-1){{
        var x=pad.left+(cw*i/Math.max(data.length-1,1));
        var t=document.createElementNS(svgNS,'text');
        t.setAttribute('x',x);t.setAttribute('y',h-4);
        t.setAttribute('text-anchor','middle');t.setAttribute('fill','#94a3b8');
        t.setAttribute('font-size','8');t.textContent=d.date.slice(5);
        svg.appendChild(t);
      }}
    }});

    var areaPts='',linePts='';
    data.forEach(function(d,i){{
      var x=pad.left+(cw*i/Math.max(data.length-1,1));
      var y=pad.top+ch-(ch*(d[valueKey]-min)/rng);
      areaPts+=(i===0?'M':'L')+x.toFixed(1)+','+y.toFixed(1)+' ';
      linePts+=(i===0?'M':'L')+x.toFixed(1)+','+y.toFixed(1)+' ';
    }});
    areaPts+='L'+(pad.left+cw).toFixed(1)+','+(pad.top+ch).toFixed(1)+' L'+pad.left+','+(pad.top+ch).toFixed(1)+' Z';

    var defs=document.createElementNS(svgNS,'defs');
    var grad=document.createElementNS(svgNS,'linearGradient');
    grad.setAttribute('id',containerId+'g');grad.setAttribute('x1','0');grad.setAttribute('y1','0');grad.setAttribute('x2','0');grad.setAttribute('y2','1');
    var s1=document.createElementNS(svgNS,'stop');s1.setAttribute('offset','0%');s1.setAttribute('stop-color',color);s1.setAttribute('stop-opacity','0.2');
    var s2=document.createElementNS(svgNS,'stop');s2.setAttribute('offset','100%');s2.setAttribute('stop-color',color);s2.setAttribute('stop-opacity','0.02');
    grad.appendChild(s1);grad.appendChild(s2);defs.appendChild(grad);svg.appendChild(defs);

    var area=document.createElementNS(svgNS,'path');area.setAttribute('d',areaPts);area.setAttribute('fill','url(#'+containerId+'g)');svg.appendChild(area);
    var path=document.createElementNS(svgNS,'path');path.setAttribute('d',linePts);path.setAttribute('fill','none');path.setAttribute('stroke',color);path.setAttribute('stroke-width','1.8');path.setAttribute('stroke-linecap','round');svg.appendChild(path);

    data.forEach(function(d,i){{
      var x=pad.left+(cw*i/Math.max(data.length-1,1));
      var y=pad.top+ch-(ch*(d[valueKey]-min)/rng);
      var c=document.createElementNS(svgNS,'circle');
      c.setAttribute('cx',x.toFixed(1));c.setAttribute('cy',y.toFixed(1));
      c.setAttribute('r','2.5');c.setAttribute('fill','#fff');
      c.setAttribute('stroke',color);c.setAttribute('stroke-width','1.5');
      svg.appendChild(c);
    }});
    el.appendChild(svg);
  }}

  // Spend trend
  var spendData=s.spend_trend||[];
  if(spendData.length) drawTrend('trendChart', spendData, 'amount', '#0d9488', 'Y', 140, 1);

  // SOC drift
  var driftData=s.soc_drift||[];
  if(driftData.length>=2) drawTrend('driftChart', driftData, 'cumulative_loss', '#8b5cf6', 'kWh', 110, 1);

  // Efficiency trend
  var effData=s.efficiency_trend||[];
  if(effData.length>=2) drawTrend('effChart', effData, 'efficiency', '#0ea5e9', 'x', 110, 2);

  // Cost per km trend
  var ckmData=s.cost_per_km_trend||[];
  if(ckmData.length>=2) drawTrend('costKmChart', ckmData, 'cost_per_km', '#f59e0b', 'Y', 110, 2);

  // Real consumption trend (kWh/100km)
  var consData=s.consumption_trend||[];
  if(consData.length>=2) drawTrend('consChart', consData, 'consumption', '#0ea5e9', 'kWh', 110, 1);

}})();
</script>
</body>
</html>"""
    return html


def _render_rows(records):
    html = ""
    for r in reversed(records):
        soc = f"{r['start_soc']:.0f}%→{r['end_soc']:.0f}%" if r["start_soc"] is not None and r["end_soc"] is not None else "-"
        eff = f"{r['efficiency']:.2f}x" if r["efficiency"] is not None else "-"
        loss_tag = "-"
        if r["loss_rate"] is not None:
            cls = "tag-ok" if r["pile_loss"] > 0 and r["loss_rate"] < 10 else ("tag-neg" if r["pile_loss"] < 0 else "tag-hi")
            loss_tag = f'<span class="tag {cls}">{r["loss_rate"]:.1f}%</span>'
        coupon_badge = f' <span class="coupon-badge">🎫¥{r["coupon"]:.0f}</span>' if r["coupon"] > 0 else ""
        html += f"""<tr>
          <td>{r["date"]}</td>
          <td style="max-width:100px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">{r["station"]}</td>
          <td class="kwh">{r["kwh"]}</td>
          <td class="amount">¥{r["amount"]:.2f}{coupon_badge}</td>
          <td>¥{r["unit_price"]:.2f}</td>
          <td>{soc}</td>
          <td>{eff}</td>
          <td>{loss_tag}</td>
          <td>{f'<span style="font-size:10px;color:var(--text3)">¥{r["effective_unit_price"]:.2f}</span>' if r["coupon"] > 0 else ''}</td>
        </tr>"""
    return html


def _render_ranking(ranking):
    medals = {0: ("🥇", "gold"), 1: ("🥈", "silver"), 2: ("🥉", "bronze")}
    html = ""
    for i, r in enumerate(ranking):
        medal, cls = medals.get(i, (str(i+1), ""))
        soc_change = f"{r['soc_change']:.0f}% SOC" if r['soc_change'] else ""
        eff_cls = "green" if r["efficiency"] > 0.95 else ("orange" if r["efficiency"] > 0.9 else "red")
        html += f"""<div class="ranking-item">
          <div class="rank {cls}">{medal}</div>
          <div class="info">
            <div class="eff"><span class="{eff_cls}">{r["efficiency"]:.2f}x</span></div>
            <div class="sub">{r["date"]} · {r["station"]} · {r["kwh"]}kWh · {soc_change}</div>
          </div>
        </div>"""
    return html


def _consume_class(summary):
    if summary.get("avg_consumption"):
        if summary["avg_consumption"] < 13: return "green"
        if summary["avg_consumption"] < 16: return "orange"
        return "red"
    return "muted"


def _loss_class(summary):
    if summary.get("avg_loss_rate"):
        if summary["avg_loss_rate"] < 5: return "green"
        if summary["avg_loss_rate"] < 10: return "orange"
        return "red"
    return "muted"


def _eff_class(summary):
    if summary.get("avg_efficiency"):
        if summary["avg_efficiency"] > 0.95: return "green"
        if summary["avg_efficiency"] > 0.9: return "orange"
        return "red"
    return "muted"


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Render charging dashboard from JSON records.")
    parser.add_argument("--json-input", default=str(DATA_PATH),
                        help="Path to JSON file with raw charging records (default: ./charging_records.json)")
    args = parser.parse_args()

    print(f"Reading JSON: {args.json_input}...")
    records = read_json(args.json_input)
    summary = compute_summary(records)
    print(f"  {len(records)} records")

    print("Generating HTML...")
    html = render(records, summary)
    OUTPUT_PATH.write_text(html, encoding="utf-8")
    print(f"  Written: {OUTPUT_PATH} ({len(html):,} bytes)")
    print("Done.")

"""
Static site generator for charging dashboard.
Reads Excel → generates self-contained index.html (no server needed)
"""
import json
import sys
from datetime import datetime
from pathlib import Path

import openpyxl

EXCEL_PATH = r"D:\OneDrive\obsidian\MYOS\09.个人知识库\Q.汽车\充电记录.xlsx"
OUTPUT_PATH = Path(__file__).parent / "index.html"
BATTERY_CAPACITY = 60.9


def read_excel():
    wb = openpyxl.load_workbook(EXCEL_PATH, data_only=False)
    ws = wb.active
    rows = []
    prev_mileage = None

    for i, row in enumerate(ws.iter_rows(min_row=2, values_only=True), 2):
        if not row[0]:
            continue
        date_val = row[0]
        date_str = date_val.strftime("%Y-%m-%d") if isinstance(date_val, datetime) else str(date_val) if date_val else None
        station = str(row[1]) if row[1] else ""
        gun = str(row[2]) if row[2] else ""
        duration_min = row[3]
        kwh = float(row[4]) if row[4] else 0
        amount = float(row[5]) if row[5] else 0
        unit_price = round(amount / kwh, 2) if kwh > 0 else 0
        start_soc = float(row[7]) if row[7] and str(row[7]).strip() else None
        end_soc = float(row[8]) if row[8] and str(row[8]).strip() else None
        mileage = float(row[9]) if row[9] else None

        driven_km = round(mileage - prev_mileage, 1) if mileage and prev_mileage else None
        real_consumption = round(kwh / driven_km * 100, 2) if driven_km and driven_km > 0 and kwh > 0 else None

        battery_calc = round(BATTERY_CAPACITY * (end_soc - start_soc) / 100, 2) if start_soc is not None and end_soc is not None else None
        pile_loss = round(kwh - battery_calc, 2) if battery_calc is not None and battery_calc > 0 and kwh > 0 else None
        loss_rate = round(abs(pile_loss) / kwh * 100, 1) if pile_loss is not None and kwh > 0 else None

        order_id = str(row[16]) if len(row) > 16 and row[16] else ""
        start_time = str(row[17]) if len(row) > 17 and row[17] else ""
        stop_method = str(row[21]) if len(row) > 21 and row[21] else ""
        platform = str(row[22]) if len(row) > 22 and row[22] else ""

        rows.append({
            "date": date_str, "station": station, "gun": gun,
            "duration_min": duration_min, "kwh": kwh, "amount": amount,
            "unit_price": unit_price, "start_soc": start_soc, "end_soc": end_soc,
            "mileage": mileage, "driven_km": driven_km, "real_consumption": real_consumption,
            "battery_calc_kwh": battery_calc, "pile_loss": pile_loss, "loss_rate": loss_rate,
            "order_id": order_id, "start_time": start_time, "stop_method": stop_method,
            "platform": platform,
        })
        prev_mileage = mileage

    wb.close()
    return rows


def compute_summary(records):
    total = len(records)
    total_kwh = round(sum(r["kwh"] for r in records), 2)
    total_amount = round(sum(r["amount"] for r in records), 2)
    avg_price = round(total_amount / total_kwh, 2) if total_kwh > 0 else 0
    avg_per_charge = round(total_amount / total, 2) if total > 0 else 0

    total_minutes = sum(r["duration_min"] or 0 for r in records)
    total_hours = round(total_minutes / 60, 1)
    avg_duration_hours = round(total_hours / total, 1) if total > 0 else 0
    # total_hours_int for display: format as "Xh Ym"
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

    latest = records[-1] if records else None
    total_mileage = latest["mileage"] if latest and latest["mileage"] else None

    spend_trend = [{"date": r["date"], "amount": r["amount"]} for r in records if r["date"] and r["amount"]]
    charge_calendar = {r["date"]: 1 for r in records if r["date"]}

    # Generate date for "记录天数"
    first_date = dates_with_data[0].strftime("%Y-%m-%d") if dates_with_data else ""

    return {
        "total_charges": total,
        "total_kwh": total_kwh,
        "total_amount": total_amount,
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

    recent_5 = list(reversed(records))[:5]

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
<title>充能有数 - 海狮05EV</title>
<style>
*,*::before,*::after{{box-sizing:border-box;margin:0;padding:0}}
:root{{--bg:#f0f4f3;--card:#fff;--primary:#0d9488;--primary-light:#e6f7f5;--primary-dark:#0f766e;--text:#1e293b;--text2:#64748b;--text3:#94a3b8;--border:#e8edec;--green:#0d9488;--orange:#f59e0b;--red:#ef4444;--blue:#3b82f6}}
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
.val.green{{color:var(--green)}}.val.orange{{color:var(--orange)}}.val.red{{color:var(--red)}}.val.muted{{color:var(--text3)}}
.trend-section{{margin:0 12px;background:var(--card);border-radius:12px;padding:14px;margin-top:10px}}
.trend-header{{display:flex;justify-content:space-between;align-items:center;margin-bottom:8px}}
.trend-header .title{{font-size:12px;font-weight:600;color:var(--text2)}}
.trend-header .unit{{font-size:10px;color:var(--text3)}}
.trend-chart{{width:100%;height:160px}} .trend-chart svg{{width:100%;height:100%}}
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
  </div>
</div>
<div class="updated">* 从 {summary["first_date"]} 开始记录，累计 {summary["total_charges"]} 次充电</div>

<div class="section-title">数据洞察</div>
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

<div class="trend-section">
  <div class="trend-header"><span class="title">花费趋势</span><span class="unit">元/次</span></div>
  <div class="trend-chart" id="trendChart"></div>
</div>

<div class="cal-section">
  <div class="cal-header">
    <span class="title">充电日历</span>
    <div class="cal-nav">
      <span class="arrow" id="calPrev">&lt;</span>
      <span class="month" id="calMonth"></span>
      <span class="arrow" id="calNext">&gt;</span>
    </div>
  </div>
  <div class="cal-grid" id="calGrid"></div>
</div>

{f'''<div class="section-title">最近充电</div>
<div class="latest-card">
  <div class="station">{summary["latest"]["date"]} - {summary["latest"]["station"]}</div>
  <div class="stats">
    <span>电量 <b>{summary["latest"]["kwh"]} kWh</b></span>
    <span>金额 <b>¥{summary["latest"]["amount"]:.2f}</b></span>
    <span>单价 ¥{summary["latest"]["unit_price"]:.2f}/度</span>
    {f'<span>SOC {summary["latest"]["start_soc"]:.0f}% → {summary["latest"]["end_soc"]:.0f}%</span>' if summary["latest"]["start_soc"] is not None and summary["latest"]["end_soc"] is not None else ''}
  </div>
</div>''' if summary["latest"] else ''}

<div class="section-title">充电历史</div>
<div class="table-section">
  <div class="table-wrap" style="overflow-x:auto">
    <table>
      <thead><tr><th>日期</th><th>充电站</th><th>电量</th><th>金额</th><th>单价</th><th>SOC</th><th>损耗</th></tr></thead>
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

  // Trend
  var data=s.spend_trend||[];
  if(data.length){{
    var svgNS='http://www.w3.org/2000/svg';
    var svg=document.createElementNS(svgNS,'svg');
    svg.setAttribute('viewBox','0 0 360 140');
    svg.setAttribute('preserveAspectRatio','xMidYMid meet');
    svg.style.width='100%';svg.style.height='100%';
    var pad={{top:8,right:10,bottom:20,left:48}},w=360,h=140;
    var cw=w-pad.left-pad.right,ch=h-pad.top-pad.bottom;
    var amts=data.map(function(r){{return r.amount}});
    var max=Math.max.apply(null,amts),min=Math.min.apply(null,amts);
    var rng=max-min||1;
    for(var i=0;i<=4;i++){{
      var val=Math.round((min+rng*i/4)*10)/10;
      var y=pad.top+ch-(ch*i/4);
      var t=document.createElementNS(svgNS,'text');
      t.setAttribute('x',pad.left-6);t.setAttribute('y',y+4);
      t.setAttribute('text-anchor','end');t.setAttribute('fill','#94a3b8');
      t.setAttribute('font-size','9');t.textContent='Y'+val;
      svg.appendChild(t);
      var l=document.createElementNS(svgNS,'line');
      l.setAttribute('x1',pad.left);l.setAttribute('x2',w-pad.right);
      l.setAttribute('y1',y);l.setAttribute('y2',y);
      l.setAttribute('stroke','#e8edec');l.setAttribute('stroke-width','0.5');
      svg.appendChild(l);
    }}
    data.forEach(function(d,i){{
      var x=pad.left+(cw*i/Math.max(data.length-1,1));
      var t=document.createElementNS(svgNS,'text');
      t.setAttribute('x',x);t.setAttribute('y',h-2);
      t.setAttribute('text-anchor','middle');t.setAttribute('fill','#94a3b8');
      t.setAttribute('font-size','9');t.textContent=d.date.slice(5);
      svg.appendChild(t);
    }});
    var areaPts='',linePts='';
    data.forEach(function(d,i){{
      var x=pad.left+(cw*i/Math.max(data.length-1,1));
      var y=pad.top+ch-(ch*(d.amount-min)/rng);
      areaPts+=(i===0?'M':'L')+x.toFixed(1)+','+y.toFixed(1)+' ';
      linePts+=(i===0?'M':'L')+x.toFixed(1)+','+y.toFixed(1)+' ';
    }});
    areaPts+='L'+(pad.left+cw).toFixed(1)+','+(pad.top+ch).toFixed(1)+' L'+pad.left+','+(pad.top+ch).toFixed(1)+' Z';
    var defs=document.createElementNS(svgNS,'defs');
    var grad=document.createElementNS(svgNS,'linearGradient');
    grad.setAttribute('id','g');grad.setAttribute('x1','0');grad.setAttribute('y1','0');grad.setAttribute('x2','0');grad.setAttribute('y2','1');
    var s1=document.createElementNS(svgNS,'stop');s1.setAttribute('offset','0%');s1.setAttribute('stop-color','#0d9488');s1.setAttribute('stop-opacity','0.25');
    var s2=document.createElementNS(svgNS,'stop');s2.setAttribute('offset','100%');s2.setAttribute('stop-color','#0d9488');s2.setAttribute('stop-opacity','0.02');
    grad.appendChild(s1);grad.appendChild(s2);defs.appendChild(grad);svg.appendChild(defs);
    var area=document.createElementNS(svgNS,'path');area.setAttribute('d',areaPts);area.setAttribute('fill','url(#g)');svg.appendChild(area);
    var path=document.createElementNS(svgNS,'path');path.setAttribute('d',linePts);path.setAttribute('fill','none');path.setAttribute('stroke','#0d9488');path.setAttribute('stroke-width','2');path.setAttribute('stroke-linecap','round');svg.appendChild(path);
    data.forEach(function(d,i){{
      var x=pad.left+(cw*i/Math.max(data.length-1,1));
      var y=pad.top+ch-(ch*(d.amount-min)/rng);
      var c=document.createElementNS(svgNS,'circle');
      c.setAttribute('cx',x.toFixed(1));c.setAttribute('cy',y.toFixed(1));
      c.setAttribute('r','3');c.setAttribute('fill','#fff');
      c.setAttribute('stroke','#0d9488');c.setAttribute('stroke-width','2');
      svg.appendChild(c);
    }});
    document.getElementById('trendChart').appendChild(svg);
  }}
}})();
</script>
</body>
</html>"""
    return html


def _render_rows(records):
    html = ""
    for r in reversed(records):
        soc = f"{r['start_soc']:.0f}%→{r['end_soc']:.0f}%" if r["start_soc"] is not None and r["end_soc"] is not None else "-"
        loss_tag = "-"
        if r["loss_rate"] is not None:
            cls = "tag-ok" if r["pile_loss"] > 0 and r["loss_rate"] < 10 else ("tag-neg" if r["pile_loss"] < 0 else "tag-hi")
            loss_tag = f'<span class="tag {cls}">{r["loss_rate"]:.1f}%</span>'
        html += f"""<tr>
          <td>{r["date"]}</td>
          <td style="max-width:130px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">{r["station"]}</td>
          <td class="kwh">{r["kwh"]}</td>
          <td class="amount">¥{r["amount"]:.2f}</td>
          <td>¥{r["unit_price"]:.2f}</td>
          <td>{soc}</td>
          <td>{loss_tag}</td>
        </tr>"""
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


if __name__ == "__main__":
    print("Reading Excel...")
    records = read_excel()
    summary = compute_summary(records)
    print(f"  {len(records)} records")

    print("Generating HTML...")
    html = render(records, summary)
    OUTPUT_PATH.write_text(html, encoding="utf-8")
    print(f"  Written: {OUTPUT_PATH} ({len(html):,} bytes)")
    print("Done.")

(() => {
  'use strict';
  const data = JSON.parse(document.getElementById('charging-data').textContent);
  const all = data.records;
  const $ = id => document.getElementById(id);
  const fmt = (n, places = 2) => n == null ? '—' : Number(n).toLocaleString('zh-CN', {minimumFractionDigits:places, maximumFractionDigits:places});
  const sum = (rows, key) => rows.reduce((total, row) => total + (row[key] || 0), 0);
  const monthName = month => `${month.slice(0,4)} 年 ${Number(month.slice(5))} 月`;
  const el = (tag, cls, text) => {const node = document.createElement(tag); if(cls)node.className=cls; if(text != null)node.textContent=text; return node;};
  const svgNS = 'http://www.w3.org/2000/svg';
  const svgEl = (tag, attrs, text) => {const node=document.createElementNS(svgNS,tag); for(const [key,value] of Object.entries(attrs || {}))node.setAttribute(key,value);if(text!=null)node.textContent=text;return node;};
  const monthValues = [...new Set(all.map(r=>r.date.slice(0,7)))].sort();
  const monthGroups = monthValues.map(month=>{const rows=all.filter(r=>r.date.startsWith(month));return {month,amount:sum(rows,'amount'),price:sum(rows,'amount')/sum(rows,'kwh'),count:rows.length};});
  let period = monthValues.at(-1) || 'all', metric='amount', limit=12, stationsExpanded=false;
  const params = new URLSearchParams(location.search);
  if(params.get('month') === 'all' || monthValues.includes(params.get('month'))) period=params.get('month');
  $('period').append(el('option','', '全部记录'));
  $('period').firstElementChild.value='all';
  for(const month of [...monthValues].reverse()){const opt=el('option','',monthName(month));opt.value=month;$('period').append(opt);}
  $('period').value=period;
  const selection = () => period==='all' ? all : all.filter(r=>r.date.startsWith(period));
  const summary = rows => ({amount:sum(rows,'amount'),kwh:sum(rows,'kwh'),coupon:sum(rows,'coupon'),count:rows.length,price:rows.length?sum(rows,'amount')/sum(rows,'kwh'):null});
  const selectedTitle = () => period==='all'?'全部记录':monthName(period);
  const duration = minutes => minutes == null ? '未记录时长' : `${fmt(minutes,0)} 分钟`;
  function updateUrl(){const url=new URL(location.href);if(period==='all')url.searchParams.set('month','all');else url.searchParams.set('month',period);history.replaceState(null,'',url);}
  function updateOverview(){
    const rows=selection(), s=summary(rows), latest=rows.at(-1);
    $('expense-label').textContent=`${selectedTitle()} · 实付花费`;
    $('expense').textContent=fmt(s.amount);
    $('expense-caption').textContent=`${s.count} 次充电 · 实际支付`;
    $('coupon-caption').textContent=s.coupon>0?`优惠节省 ¥${fmt(s.coupon,0)}`:'';
    $('price').textContent=fmt(s.price);
    $('energy').textContent=fmt(s.kwh,1);
    $('energy-caption').textContent=`来自 ${s.count} 次桩端充电记录`;
    $('latest').replaceChildren();
    if(!latest){$('latest-date').textContent='暂无记录';$('latest').append(el('p','empty','这个范围还没有充电记录。'));return;}
    $('latest-date').textContent=latest.date.replaceAll('-',' / ');
    $('latest').append(el('p','latest-station',latest.station),el('p','latest-platform',latest.platform || `实付电价 ${fmt(latest.unit_price)} 元 / 度`));
    const values=el('div','latest-values');
    for(const [label,value,unit] of [['实付花费',fmt(latest.amount),'元'],['充入电量',fmt(latest.kwh,1),'kWh']]){
      const block=el('div');block.append(el('small','',label));const strong=el('strong','',value);strong.append(el('span','',unit));block.append(strong);values.append(block);
    }
    const soc=el('div','soc');const label=el('span','', '电量变化');const val=el('strong','',latest.start_soc!=null&&latest.end_soc!=null?`${fmt(latest.start_soc,0)}% → ${fmt(latest.end_soc,0)}%`:'未记录');soc.append(label,val);
    $('latest').append(values,soc);
    if(latest.start_soc!=null&&latest.end_soc!=null&&latest.end_soc>=latest.start_soc){const meter=el('div','soc-meter');const filled=el('i');filled.style.left=`${latest.start_soc}%`;filled.style.width=`${latest.end_soc-latest.start_soc}%`;meter.append(filled);$('latest').append(meter);}
    const caption=el('p','soc-caption quiet-label');caption.append(el('span','',duration(latest.duration_min)),el('span','',latest.coupon>0?`本次优惠 ¥${fmt(latest.coupon,0)}`:'桩端充电量'));$('latest').append(caption);
  }
  function updateChart(){
    $('trend-spend').setAttribute('aria-pressed',String(metric==='amount'));$('trend-price').setAttribute('aria-pressed',String(metric==='price'));
    $('trend-unit').textContent=metric==='amount'?'实付花费 · 元':'平均实付电价 · 元 / 度';
    const width=Math.max(280,$('trend').clientWidth||600);
    const groups=monthGroups.slice(width<450?-6:-12);
    $('trend-caption').textContent=groups.length?`最近 ${groups.length} 个有记录月份 · ${metric==='amount'?'实际支付金额':'按充电量加权的平均电价'}`:'有了充电记录，就能看到月度变化。';
    $('trend').replaceChildren();
    if(!groups.length){$('trend').append(el('p','empty','暂无趋势数据'));return;}
    const height=160,left=36,right=8,top=20,bottom=30,chartH=height-top-bottom;
    const values=groups.map(g=>g[metric]),max=Math.max(...values),cap=max>0?max*1.23:1;
    const step=(width-left-right)/groups.length,barWidth=Math.min(45,step*.48);
    const svg=svgEl('svg',{viewBox:`0 0 ${width} ${height}`,role:'group','aria-label':'选择月份',preserveAspectRatio:'none'});
    for(let i=0;i<3;i++){const y=top+chartH*i/2;svg.append(svgEl('line',{x1:left,x2:width-right,y1:y,y2:y,stroke:'#edf1f4','stroke-dasharray':'3 4'}));svg.append(svgEl('text',{x:left-9,y:y+3,'text-anchor':'end',fill:'#8798a5','font-size':10},fmt(cap*(1-i/2),metric==='amount'?0:2)));}
    for(const [i,g] of groups.entries()){
      const x=left+step*(i+.5),value=g[metric],h=value/cap*chartH;
      const group=svgEl('g',{tabindex:'0',role:'button','aria-label':`${monthName(g.month)}，${metric==='amount'?'花费':'平均电价'} ${fmt(value)}，点击查看`});
      const active=period==='all'||g.month===period;
      group.style.cursor='pointer';group.append(svgEl('rect',{x:x-barWidth/2,y:top+chartH-h,width:barWidth,height:Math.max(h,2),rx:5,fill:active?'#285c7d':'#dfe9f0'}));
      group.append(svgEl('text',{x,y:top+chartH-h-7,'text-anchor':'middle',fill:active?'#395b73':'#95a9b7','font-size':10},fmt(value,metric==='amount'?0:2)));
      group.append(svgEl('text',{x,y:height-9,'text-anchor':'middle',fill:active?'#647f92':'#98a8b3','font-size':10},`${Number(g.month.slice(5))}月`));
      const select=()=>{period=g.month;$('period').value=period;limit=12;stationsExpanded=false;updateUrl();render(true);};
      group.addEventListener('click',select);group.addEventListener('keydown',event=>{if(event.key==='Enter'||event.key===' '){event.preventDefault();select();}});svg.append(group);
    }
    $('trend').setAttribute('aria-label',`月度${metric==='amount'?'实付花费':'平均实付电价'}：${groups.map(g=>`${monthName(g.month)} ${fmt(g[metric])}`).join('；')}`);
    $('trend').append(svg);
  }
  function updateStations(){
    const map=new Map();for(const row of selection()){if(row.station==='未记录站点')continue;const rows=map.get(row.station)||[];rows.push(row);map.set(row.station,rows);}
    const stations=[...map.entries()].map(([name,rows])=>({name,...summary(rows)})).sort((a,b)=>b.count-a.count||a.price-b.price||a.name.localeCompare(b.name,'zh-CN'));
    $('station-count').textContent=`${stations.length} 个站点`;$('stations').replaceChildren();
    if(!stations.length)$('stations').append(el('p','empty','暂无站点记录'));
    for(const [index,station] of (stationsExpanded?stations:stations.slice(0,6)).entries()){
      const item=el('div','station-item');item.append(el('span','station-index',String(index+1)));const info=el('div');const name=el('p','station-name',station.name);name.title=station.name;const meta=el('div','station-meta');meta.append(el('strong','',`${fmt(station.price)} 元 / 度`),el('span','',`${station.count} 次 · ${fmt(station.kwh,1)} 度`));info.append(name,meta);item.append(info);$('stations').append(item);
    }
    $('more-stations').hidden=stations.length<=6;$('more-stations').textContent=stationsExpanded?'收起站点':`展开其余 ${stations.length-6} 个站点`;
  }
  function updateStationOptions(){const previous=$('station-filter').value;$('station-filter').replaceChildren();const first=el('option','', '全部充电站');first.value='';$('station-filter').append(first);for(const name of [...new Set(selection().map(r=>r.station))].sort((a,b)=>a.localeCompare(b,'zh-CN'))){const option=el('option','',name);option.value=name;$('station-filter').append(option);}if([...$('station-filter').options].some(o=>o.value===previous))$('station-filter').value=previous;}
  function filteredRecords(){const search=$('search').value.trim().toLocaleLowerCase(),station=$('station-filter').value;const rows=selection().filter(r=>(!station||r.station===station)&&(!search||`${r.station} ${r.original_station} ${r.platform}`.toLocaleLowerCase().includes(search)));const order=$('sort').value;return [...rows].sort((a,b)=>order==='price'?a.unit_price-b.unit_price||b.date.localeCompare(a.date):order==='amount'?a.amount-b.amount||b.date.localeCompare(a.date):b.date.localeCompare(a.date));}
  function updateRecords(){
    const rows=filteredRecords();$('records').replaceChildren();
    for(const row of rows.slice(0,limit)){
      const tr=el('tr'),identity=el('td');identity.append(el('span','row-date',row.date),el('span','row-station',row.station));tr.append(identity);
      for(const [label,value] of [['充电量',`${fmt(row.kwh,1)} 度`],['实付花费',`¥${fmt(row.amount)}`],['实付电价',`${fmt(row.unit_price)} 元/度`],['电量变化',row.start_soc!=null&&row.end_soc!=null?`${fmt(row.start_soc,0)}% → ${fmt(row.end_soc,0)}%`:'未记录'],['时长',row.duration_min!=null?`${fmt(row.duration_min,0)} 分钟`:'未记录']]){
        const cell=el('td',label==='实付花费'?'money':label==='电量变化'?'row-soc':'',value);cell.dataset.label=label;if(label==='实付花费'&&row.coupon>0)cell.append(el('span','coupon',`优惠 ¥${fmt(row.coupon,0)}`));tr.append(cell);
      }$('records').append(tr);
    }
    $('empty').hidden=rows.length>0;$('more-records').hidden=rows.length<=limit;$('more-records').textContent=`查看更多 · 还有 ${Math.max(0,rows.length-limit)} 条`;
    $('record-count').textContent=rows.length?`显示 ${Math.min(limit,rows.length)} / ${rows.length} 条记录`:'0 条记录';
    $('history-caption').textContent=`${selectedTitle()} · ${rows.length} 次充电 · 实付 ¥${fmt(sum(rows,'amount'))}`;
    $('export').disabled=rows.length===0;
  }
  function render(resetStations=false){if(resetStations)updateStationOptions();updateOverview();updateChart();updateStations();updateRecords();}
  $('period').addEventListener('change',()=>{period=$('period').value;limit=12;stationsExpanded=false;updateUrl();render(true);});
  $('trend-spend').addEventListener('click',()=>{metric='amount';updateChart();});$('trend-price').addEventListener('click',()=>{metric='price';updateChart();});
  for(const id of ['search','station-filter','sort'])$(id).addEventListener(id==='search'?'input':'change',()=>{limit=12;updateRecords();});
  $('more-records').addEventListener('click',()=>{limit+=12;updateRecords();});$('more-stations').addEventListener('click',()=>{stationsExpanded=!stationsExpanded;updateStations();});
  let resizeFrame;window.addEventListener('resize',()=>{cancelAnimationFrame(resizeFrame);resizeFrame=requestAnimationFrame(updateChart);});
  $('export').addEventListener('click',()=>{
    const escaped=value=>`"${String(value ?? '').replaceAll('"','""').replace(/^[=+@\-]/,"'$&")}"`;
    const header=['日期','充电站','原始站名','电量(kWh)','实付(元)','优惠(元)','实付单价(元/度)','起始SOC(%)','结束SOC(%)','时长(分钟)','里程(km)','平台'];
    const rows=filteredRecords().map(r=>[r.date,r.station,r.original_station,r.kwh,fmt(r.amount),r.coupon,fmt(r.unit_price),r.start_soc,r.end_soc,r.duration_min,r.mileage,r.platform]);
    const csv='\uFEFF'+[header,...rows].map(row=>row.map(escaped).join(',')).join('\r\n');const url=URL.createObjectURL(new Blob([csv],{type:'text/csv;charset=utf-8'}));const anchor=el('a');anchor.href=url;anchor.download=`充电记录-${period}.csv`;document.body.append(anchor);anchor.click();anchor.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);
  });
  $('archive-caption').textContent=all.length?`${all[0].date} 起 · 共 ${all.length} 次充电`:'等待第一条充电记录';
  $('data-note').textContent=all.length?`最近记录 ${all.at(-1).date}`:'';
  const excluded=data.excluded||{};$('exclusion-note').textContent=`统计已排除 ${excluded.test||0} 条测试记录${excluded.invalid?`及 ${excluded.invalid} 条无效记录`:''}，原始数据保留。`;
  render(true);
})();

(() => {
'use strict';
if(location.hostname.endsWith('.pages.dev')){location.replace('https://charging.waylenlifeos.dpdns.org/admin/'+location.search);return;}
const $=id=>document.getElementById(id),form=$('entry-form'),save=$('entry-save'),error=$('entry-error');
const editId=new URLSearchParams(location.search).get('edit'),editing=Boolean(editId);
const key=editing?'charging:edit-draft:v1:'+editId:'charging:manual-draft:v1';
let busy=false,authenticated=false,requestId=crypto.randomUUID(),lastBody='',editVersion='',baseRecord={},draft=null;
const today=new Date(),localDate=[today.getFullYear(),String(today.getMonth()+1).padStart(2,'0'),String(today.getDate()).padStart(2,'0')].join('-');
const inputs=[...form.querySelectorAll('input[name]')];
$('entry-date').value=localDate;$('entry-date').max=localDate;
try{draft=JSON.parse(localStorage.getItem(key)||'null');}catch{}
function applyDraft(){if(!draft?.values)return;for(const input of inputs)if(typeof draft.values[input.name]==='string')input.value=draft.values[input.name];if(typeof draft.requestId==='string')requestId=draft.requestId;if(typeof draft.lastBody==='string')lastBody=draft.lastBody;if(editing&&typeof draft.version==='string')editVersion=draft.version;$('draft-note').textContent='已恢复当前浏览器中未保存的草稿。';}
function persist(){try{const values=Object.fromEntries(inputs.map(i=>[i.name,i.value]));localStorage.setItem(key,JSON.stringify({values,requestId,lastBody,version:editVersion}));}catch{$('draft-note').textContent='浏览器未能保存草稿，当前页面仍可修改。';}}
function estimate(){const amount=Number(form.elements.amount.value),kwh=Number(form.elements.kwh.value);$('entry-price').textContent=kwh>0&&form.elements.amount.value!==''?'这次实付电价约 '+(amount/kwh).toFixed(2)+' 元 / 度':'填入电量与金额后，可预览实付电价。';}
function message(text){error.textContent=text;error.hidden=false;}
function element(tag,text,cls){const node=document.createElement(tag);if(text!==undefined)node.textContent=text;if(cls)node.className=cls;return node;}
const labels={date:'充电日期',station:'充电站',kwh:'充入电量',amount:'实付金额',duration_min:'充电时长',start_soc:'起始电量',end_soc:'结束电量',mileage:'里程表',coupon:'优惠金额',order_id:'订单号',platform:'充电平台',gun:'充电枪',start_time:'开始时间',stop_method:'结束方式'};
const shown=value=>value===undefined||value===null||value===''?'未记录':String(value);
function renderHistory(history){
 $('entry-history').hidden=false;$('history-heading').textContent='修改历史 · '+history.length+' 次更正';$('history-list').replaceChildren();
 if(!history.length){$('history-list').append(element('p','尚未更正。保存修改后，这里会保留前后值。','history-note'));return;}
 for(const item of [...history].reverse()){const article=element('article',undefined,'history-entry');article.append(element('h3',new Intl.DateTimeFormat('zh-CN',{dateStyle:'medium',timeStyle:'short',timeZone:'Asia/Shanghai'}).format(new Date(item.at))));for(const field of item.changed){const row=element('div',undefined,'history-change');row.append(element('strong',labels[field]||field),element('span',shown(item.before[field])+' → '+shown(item.after[field])));article.append(row);}$('history-list').append(article);}
}
async function loadEdit(restoreDraft=true){
 save.disabled=true;inputs.forEach(i=>i.disabled=true);
 try{const response=await fetch('/admin/api/records/'+editId,{cache:'no-store'});if(!response.ok||!response.headers.get('content-type')?.includes('application/json'))throw Error('暂时无法载入这条记录，请刷新页面；已有草稿会保留。');
 const data=await response.json();baseRecord=data.record;editVersion=data.version;for(const input of inputs)input.value=baseRecord[input.name]===undefined?'':String(baseRecord[input.name]);
 if(restoreDraft)applyDraft();else{draft=null;requestId=crypto.randomUUID();lastBody='';try{localStorage.removeItem(key);}catch{};$('draft-note').textContent='已载入最新记录，未保存的修改已替换。';}
 renderHistory(data.history);estimate();inputs.forEach(i=>i.disabled=false);save.disabled=!authenticated;save.textContent='保存更正';
 if(restoreDraft&&editVersion!==data.version){message('记录已在别处更新。已恢复的草稿没有提交，请载入最新记录后再修改。');$('entry-reload').hidden=false;}else{error.hidden=true;$('entry-reload').hidden=true;}
 }catch(e){message(e.message);save.disabled=true;$('entry-reload').hidden=false;}
}
if(editing){document.title='更正充电记录 · 充能有数';$('entry-eyebrow').textContent='一程一记 · 核对更正';$('entry-heading').textContent='核对一笔，记录更准。';$('entry-description').textContent='修改原来的记录，每次更正都会保留前后值。';$('entry-another').textContent='新增一条';inputs.forEach(i=>i.disabled=true);}else{applyDraft();estimate();}
form.addEventListener('input',()=>{persist();estimate();error.hidden=true;});
async function session(){try{const res=await fetch('/admin/api/session',{cache:'no-store',credentials:'same-origin'});if(!res.ok||!res.headers.get('content-type')?.includes('application/json'))throw Error();const value=await res.json();authenticated=value.authenticated===true;$('entry-preview').hidden=!value.preview;
 if(editing){if(!/^[a-f0-9]{32}$/.test(editId)){message('记录链接无效，请返回账本重新选择。');return;}await loadEdit();}else{save.disabled=!authenticated;save.textContent='保存充电记录';}
 }catch{message('登录验证未完成，请联网后刷新此页；已填写的草稿会保留。');save.textContent='请刷新验证登录';}}
void session();
void fetch('/api/records',{cache:'no-store'}).then(res=>res.ok?res.json():null).then(data=>{if(!data?.records)return;for(const [id,field] of [['station-suggestions','station'],['platform-suggestions','platform']])for(const value of [...new Set(data.records.map(r=>r[field]).filter(Boolean))]){const option=document.createElement('option');option.value=value;$(id).append(option);}}).catch(()=>{});
form.addEventListener('submit',async event=>{
 event.preventDefault();if(busy||!authenticated||!form.reportValidity())return;
 const inputValues=Object.fromEntries(inputs.map(i=>[i.name,i.value.trim()]));
 const values=editing?{...baseRecord,...inputValues}:Object.fromEntries(Object.entries(inputValues).filter(([,v])=>v!==''));
 if(values.start_soc!==undefined&&values.start_soc!==''&&values.end_soc!==undefined&&values.end_soc!==''&&Number(values.end_soc)<Number(values.start_soc)){message('结束电量不能小于起始电量。');return;}
 const body=JSON.stringify(editing?{record:values,version:editVersion}:values);if(lastBody&&lastBody!==body)requestId=crypto.randomUUID();lastBody=body;persist();busy=true;save.disabled=true;save.textContent='正在保存…';error.hidden=true;
 try{const res=await fetch('/admin/api/records'+(editing?'/'+editId:''),{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json','X-Charging-Request':'manual-entry','Idempotency-Key':requestId},body,signal:AbortSignal.timeout(20000)});
 if(!res.headers.get('content-type')?.includes('application/json')||res.status===401)throw Error('登录可能已过期。草稿已保留，请刷新页面完成登录后重试。');
 const result=await res.json();if(!res.ok){if(result.error==='RECORD_CONFLICT')$('entry-reload').hidden=false;throw Error(result.message||'未能保存，请稍后重试。');}
 try{localStorage.removeItem(key);}catch{}
 form.hidden=true;$('entry-success').hidden=false;$('entry-success-heading').textContent=editing?(result.action==='no-change'?'这笔记录已确认。':'更正已保存，历史也留好了。'):'这笔充电，记好了。';$('entry-view').href='/?month='+encodeURIComponent(result.date.slice(0,7))+(editing?'&corrected=1':'&added=1')+'#history';
 if(editing){try{const detail=await fetch('/admin/api/records/'+editId,{cache:'no-store'});if(detail.ok)renderHistory((await detail.json()).history);}catch{/* Save already confirmed; history can be reopened later. */}}
 }catch(e){message(e.name==='TimeoutError'||e.name==='TypeError'?'暂时未能确认保存结果，请保持草稿并重试。重复保存同一次更正不会重复记录。':e.message);}
 finally{busy=false;save.disabled=!authenticated;save.textContent=editing?'保存更正':'保存充电记录';}
});
$('entry-reload').addEventListener('click',()=>{if(!busy&&editing)void loadEdit(false);});
$('entry-another').addEventListener('click',()=>{if(editing){location.assign('/admin/');return;}form.reset();$('entry-date').value=localDate;requestId=crypto.randomUUID();lastBody='';form.hidden=false;$('entry-success').hidden=true;error.hidden=true;$('draft-note').textContent='填写内容会暂存到当前浏览器。';estimate();form.elements.station.focus();});
window.addEventListener('beforeunload',event=>{if(busy){event.preventDefault();event.returnValue='';}});
})();

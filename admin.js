(() => {
'use strict';
if(location.hostname.endsWith('.pages.dev')){location.replace('https://charging.waylenlifeos.dpdns.org/admin/');return;}
const $=id=>document.getElementById(id),form=$('entry-form'),save=$('entry-save'),error=$('entry-error');
const key='charging:manual-draft:v1';let busy=false,authenticated=false,requestId=crypto.randomUUID(),lastBody='';
const today=new Date(),localDate=[today.getFullYear(),String(today.getMonth()+1).padStart(2,'0'),String(today.getDate()).padStart(2,'0')].join('-');
$('entry-date').value=localDate;$('entry-date').max=localDate;
try {const draft=JSON.parse(localStorage.getItem(key)||'null');if(draft&&draft.values){for(const input of form.querySelectorAll('input[name]'))if(typeof draft.values[input.name]==='string')input.value=draft.values[input.name];if(typeof draft.requestId==='string')requestId=draft.requestId;if(typeof draft.lastBody==='string')lastBody=draft.lastBody;$('draft-note').textContent='已恢复当前浏览器中未保存的草稿。';}}catch{}
function persist(){try{const values=Object.fromEntries([...form.querySelectorAll('input[name]')].map(i=>[i.name,i.value]));localStorage.setItem(key,JSON.stringify({values,requestId,lastBody}));}catch{$('draft-note').textContent='浏览器未能保存草稿，当前页面仍可录入。';}}
function estimate(){const amount=Number(form.elements.amount.value),kwh=Number(form.elements.kwh.value);$('entry-price').textContent=kwh>0&&form.elements.amount.value!==''?'这次实付电价约 '+(amount/kwh).toFixed(2)+' 元 / 度':'填入电量与金额后，可预览实付电价。';}
form.addEventListener('input',()=>{persist();estimate();error.hidden=true;});
estimate();
async function session(){try{const res=await fetch('/admin/api/session',{cache:'no-store',credentials:'same-origin'});if(!res.ok||!res.headers.get('content-type')?.includes('application/json'))throw Error();const value=await res.json();authenticated=value.authenticated===true;$('entry-preview').hidden=!value.preview;save.disabled=!authenticated;save.textContent='保存充电记录';}catch{error.textContent='登录验证未完成，请联网后刷新此页；已填写的草稿会保留。';error.hidden=false;save.textContent='请刷新验证登录';}}
void session();
void fetch('/api/records',{cache:'no-store'}).then(res=>res.ok?res.json():null).then(data=>{if(!data?.records)return;for(const [id,field] of [['station-suggestions','station'],['platform-suggestions','platform']])for(const value of [...new Set(data.records.map(r=>r[field]).filter(Boolean))]){const option=document.createElement('option');option.value=value;$(id).append(option);}}).catch(()=>{});
form.addEventListener('submit',async event=>{
 event.preventDefault();if(busy||!authenticated||!form.reportValidity())return;
 const values=Object.fromEntries([...form.querySelectorAll('input[name]')].filter(i=>i.value.trim()!=='').map(i=>[i.name,i.value.trim()]));
 if(values.start_soc!==undefined&&values.end_soc!==undefined&&Number(values.end_soc)<Number(values.start_soc)){error.textContent='结束电量不能小于起始电量。';error.hidden=false;return;}
 const body=JSON.stringify(values);if(lastBody&&lastBody!==body)requestId=crypto.randomUUID();lastBody=body;persist();busy=true;save.disabled=true;save.textContent='正在保存…';error.hidden=true;
 try{
  const res=await fetch('/admin/api/records',{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json','X-Charging-Request':'manual-entry','Idempotency-Key':requestId},body,signal:AbortSignal.timeout(20000)});
  if(!res.headers.get('content-type')?.includes('application/json')||res.status===401){throw Error('登录可能已过期。草稿已保留，请刷新页面完成登录后重试。');}
  const result=await res.json();if(!res.ok)throw Error(result.message||'未能保存，请稍后重试。');
  try{localStorage.removeItem(key);}catch{}
  form.hidden=true;$('entry-success').hidden=false;$('entry-view').href='/?month='+encodeURIComponent(values.date.slice(0,7))+'&added=1#history';
 }catch(e){error.textContent=e.name==='TimeoutError'||e.name==='TypeError'?'暂时未能确认保存结果，请保持草稿并重试。重复保存同一笔不会重复记账。':e.message;error.hidden=false;}
 finally{busy=false;save.disabled=false;save.textContent='保存充电记录';}
});
$('entry-another').addEventListener('click',()=>{form.reset();$('entry-date').value=localDate;requestId=crypto.randomUUID();lastBody='';form.hidden=false;$('entry-success').hidden=true;error.hidden=true;$('draft-note').textContent='填写内容会暂存到当前浏览器。';estimate();form.elements.station.focus();});
window.addEventListener('beforeunload',event=>{if(busy){event.preventDefault();event.returnValue='';}});
})();

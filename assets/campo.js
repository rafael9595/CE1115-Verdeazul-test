import {IndexedStore,createVault,openVault,seal,pruneReceipts,pendingCounts,makeDraft,acceptReceipt,markConflict,rebaseDraft} from './vault.js';
const $=id=>document.getElementById(id);
const store=new IndexedStore();let unlocked=null,current=null,busy=false,lastActivity=Date.now(),editing=null,dirty=false;
function message(s){$('message').textContent=s;}
function element(tag,text){const e=document.createElement(tag);if(text!==undefined)e.textContent=text;return e;}
function button(text,task){const b=element('button',text);b.type='button';b.addEventListener('click',()=>run(task));return b;}
async function run(task){if(busy)return;busy=true;document.querySelectorAll('button').forEach(b=>b.disabled=true);try{await task();}catch(e){message(e.message||'No se completó la operación.');}finally{busy=false;document.querySelectorAll('button').forEach(b=>b.disabled=false);}}
async function api(path,data){
 const headers={};let body;
 if(data!==undefined){headers['Content-Type']='application/json';headers['X-CSRFToken']=current?.csrf_token||'';body=JSON.stringify(data);}
 const controller=new AbortController();const timer=setTimeout(()=>controller.abort(),15000);
 try{const response=await fetch(path,{method:data===undefined?'GET':'POST',headers,body,credentials:'same-origin',cache:'no-store',signal:controller.signal});
  let result;try{result=await response.json();}catch{throw Error('Respuesta no confirmada. El pendiente local se conserva.');}
  if(!response.ok){const e=Error(result.error||`Servidor: ${response.status}`);e.status=response.status;throw e;}return result;
 }finally{clearTimeout(timer);}
}
async function context(){current=await api('/api/capture/bootstrap/');return current;}
function catalog(c){return {person_id:c.person_id,username:c.username,farms:c.farms,periods:c.periods,versions:c.versions,server_time:c.server_time};}
async function profiles(){const rows=await store.list();$('profile').replaceChildren(new Option('Seleccione un perfil',''));rows.forEach((r,i)=>$('profile').add(new Option(`Perfil local ${i+1} · ${r.person_id.slice(-8)}`,r.person_id)));if(current&&rows.some(r=>r.person_id===current.person_id))$('profile').value=current.person_id;}
async function commit(data){if(!unlocked)throw Error('El perfil está bloqueado.');const record=await seal(data,unlocked.key,unlocked.record);await store.save(record,unlocked.record.revision);unlocked={...unlocked,data,record};}
function selectOptions(id,options,selected){$(id).replaceChildren(new Option('Seleccione',''));options.forEach(o=>$(id).add(new Option(o.name,o.id)));if(selected)$(id).value=selected;}
function fillOptions(){
 const c=unlocked.data.catalog;
 $('source').replaceChildren(new Option('Nueva medición',''));
 c.versions.forEach(v=>$('source').add(new Option(`${v.measurement.farm} · versión ${v.number} · borrador`,v.id)));
 selectOptions('farm',c.farms);selectOptions('period',c.periods.filter(p=>p.status==='ABIERTA'));
 $('work-identity').textContent=`Perfil: ${c.username} · preparado ${new Date(c.server_time).toLocaleString()}`;
}
function addValue(value={name:'carbono_reportado',value:'',unit:'tCO2e'}){
 if($('values').children.length>=50)return;
 const row=element('div');row.className='row';
 for(const [field,label,max] of [['name','Variable',80],['value','Valor decimal',40],['unit','Unidad',30]]){
  const l=element('label',label);const input=element('input');input.dataset.field=field;input.value=value[field];input.required=true;input.maxLength=max;if(field==='value')input.inputMode='decimal';l.append(input);row.append(l);
 }
 const remove=element('button','Quitar');remove.type='button';remove.addEventListener('click',()=>{if($('values').children.length>1){row.remove();dirty=true;}});row.append(remove);$('values').append(row);
}
function resetForm(){editing=null;dirty=false;$('draft-form').reset();$('source').value='';$('values').replaceChildren();addValue();$('farm').disabled=false;$('period').disabled=false;selectOptions('period',unlocked.data.catalog.periods.filter(p=>p.status==='ABIERTA'));}
function loadFields(fields){$('farm').value=fields.farm_id;selectOptions('period',unlocked.data.catalog.periods,fields.period_id);$('measured').value=fields.measured_at;$('methodology').value=fields.methodology;$('values').replaceChildren();fields.values.forEach(addValue);$('farm').disabled=!!fields.version_id;$('period').disabled=!!fields.version_id;}
function fields(){
 const v=unlocked.data.catalog.versions.find(v=>v.id===$('source').value);
 const prior=editing?unlocked.data.drafts.find(d=>d.id===editing)?.payload:null;
 const data={farm_id:$('farm').value,period_id:$('period').value,version_id:prior?prior.version_id:(v?.id||null),base_revision:prior?prior.base_revision:(v?.edit_revision||0),
 measured_at:$('measured').value,methodology:$('methodology').value,values:[...$('values').children].map(row=>Object.fromEntries([...row.querySelectorAll('input')].map(x=>[x.dataset.field,x.value])))};
 if(!data.farm_id||!data.period_id||!data.measured_at||!data.methodology.trim()||!data.values.length)throw Error('Complete los datos del borrador.');
 for(const x of data.values)if(!x.name.trim()||!x.unit.trim()||!/^(-?)(0|[1-9][0-9]{0,17})(\.[0-9]{1,12})?$/.test(x.value))throw Error('Cada valor necesita nombre, unidad y decimal con punto.');
 return data;
}
async function saveDraft(){
 const input=fields();let next=structuredClone(unlocked.data);
 if(editing){const old=next.drafts.find(d=>d.id===editing);if(!old||old.attempted)throw Error('Un intento enviado no se edita. Reintente el mismo contenido o resuelva el conflicto.');old.payload={...old.payload,...input};old.message='Borrador actualizado localmente.';}
 else {if(pendingCounts(next).pending>=100)throw Error('Hay 100 pendientes; sincronice o exporte antes de continuar.');const d=makeDraft(next.person_id,input);next.drafts.push(d);editing=d.id;}
 await commit(next);dirty=false;renderQueue();message('Borrador cifrado y guardado en este navegador. Aún no se envió al servidor.');
}
function showUnlocked(){lastActivity=Date.now();$('unlock-section').hidden=true;$('workspace').hidden=false;$('passphrase').value='';fillOptions();resetForm();renderQueue();}
function lock(){unlocked=null;editing=null;dirty=false;$('workspace').hidden=true;$('unlock-section').hidden=false;$('drafts').replaceChildren();$('receipts').replaceChildren();$('values').replaceChildren();$('draft-form').reset();$('farm').replaceChildren();$('period').replaceChildren();$('source').replaceChildren();$('passphrase').value='';message('Perfil bloqueado. Los borradores guardados permanecen cifrados.');}
function renderQueue(){
 if(!unlocked)return;const d=unlocked.data;const counts=pendingCounts(d);$('counts').textContent=`${counts.pending} pendientes · ${counts.conflicts} conflictos`;$('drafts').replaceChildren();
 for(const draft of d.drafts){
  const card=element('article');card.className='draft';const farm=d.catalog.farms.find(f=>f.id===draft.payload.farm_id);
  card.append(element('strong',`${farm?.name||'Finca preparada'} · ${draft.status}`),element('p',draft.message),element('small',draft.id));
  const details=element('details');details.append(element('summary','Ver contenido local'),element('pre',JSON.stringify(draft.payload,null,2)));card.append(details);
  if(!draft.attempted&&draft.status==='PENDIENTE')card.append(button('Editar localmente',async()=>{editing=draft.id;$('source').value=draft.payload.version_id||'';loadFields(draft.payload);dirty=false;$('draft-form').scrollIntoView();}));
  if(draft.status==='CONFLICTO'&&draft.payload.version_id&&!draft.replaced_by)card.append(button('Comparar con servidor',()=>compare(draft.id,card)));
  $('drafts').append(card);
 }
 $('receipts').replaceChildren();for(const receipt of d.receipts)$('receipts').append(element('p',`${receipt.received_at} · Versión ${receipt.version_id} · Constancia ${receipt.receipt_id}`));
}
async function compare(id,card){
 await context();if(current.person_id!==unlocked.data.person_id)throw Error('Inicie sesión con el técnico de este perfil.');
 const old=unlocked.data.drafts.find(d=>d.id===id);const server=current.versions.find(v=>v.id===old.payload.version_id);
 if(!server)throw Error('La versión no está disponible como borrador editable. El pendiente se conserva para resolución o respaldo.');
 const details=element('details');details.open=true;details.append(element('summary','Versión actual del servidor'),element('pre',JSON.stringify({revision:server.edit_revision,values:server.values,methodology:server.methodology},null,2)));
 details.append(element('p','Revise ambos contenidos. El siguiente botón prepara otro intento con sus valores locales sobre esta revisión. Conserva el conflicto anterior; no sincroniza automáticamente.'));
 details.append(button('Preparar nuevo intento con mis valores',async()=>{await commit(rebaseDraft(unlocked.data,id,server));renderQueue();message('Nuevo intento preparado. El conflicto original se conserva hasta confirmar la recepción del nuevo.');}));card.append(details);
}
async function sync(){
 await context();if(current.person_id!==unlocked.data.person_id)throw Error('La sesión pertenece a otra persona. Cambie de cuenta sin borrar los pendientes.');
 const ids=unlocked.data.drafts.filter(d=>d.status!=='RESUELTO'&&!d.replaced_by).map(d=>d.id);
 for(const id of ids){
  let next=structuredClone(unlocked.data);next.drafts.find(d=>d.id===id).attempted=true;await commit(next);
  const draft=unlocked.data.drafts.find(d=>d.id===id);
  try{
   const controller=new AbortController();const timer=setTimeout(()=>controller.abort(),15000);let response;
   try{response=await fetch('/api/capture/action/sync/new/',{method:'POST',credentials:'same-origin',cache:'no-store',signal:controller.signal,
    headers:{'Content-Type':'application/json','X-CSRFToken':current.csrf_token,'Idempotency-Key':id},body:JSON.stringify(draft.payload)});}finally{clearTimeout(timer);}
   let result;try{result=await response.json();}catch{throw Error('No se obtuvo confirmación válida.');}
   if(!response.ok){await commit(markConflict(unlocked.data,id,result.error||`Servidor: ${response.status}`));if(response.status===401||response.status===403)break;continue;}
   await commit(acceptReceipt(unlocked.data,id,result));
  }catch(e){
   const pending=structuredClone(unlocked.data);const row=pending.drafts.find(d=>d.id===id);if(row)row.message='Recepción no confirmada. Reintente sin cambiar el UUID ni el contenido.';
   await commit(pending);message('Conexión o confirmación interrumpida. Se conservan los pendientes.');break;
  }
 }
 if(editing&&!unlocked.data.drafts.some(d=>d.id===editing))resetForm();
 renderQueue();await reportCounts();message('Sincronización terminada. Revise pendientes y constancias. Los borradores recibidos se envían a revisión desde el panel.');
}
async function reportCounts(){
 const counts=pendingCounts(unlocked.data);const controller=new AbortController();const timer=setTimeout(()=>controller.abort(),10000);try{await fetch('/api/capture/action/queue_status/new/',{method:'POST',signal:controller.signal,credentials:'same-origin',headers:{'Content-Type':'application/json','X-CSRFToken':current.csrf_token,'Idempotency-Key':crypto.randomUUID()},body:JSON.stringify({device_id:unlocked.data.device_id,...counts})});}catch{}finally{clearTimeout(timer);}
}
$('create').addEventListener('click',()=>run(async()=>{await context();if(await store.read(current.person_id))throw Error('Este perfil ya existe. Desbloquéelo con su frase local.');unlocked=await createVault(current.person_id,$('passphrase').value,catalog(current));try{await store.save(unlocked.record,null);}catch(e){unlocked=null;throw e;}showUnlocked();await profiles();message('Perfil preparado. Guarde borradores y exporte un respaldo cifrado antes de salir a campo.');}));
$('unlock').addEventListener('click',()=>run(async()=>{const record=await store.read($('profile').value);if(!record)throw Error('Seleccione un perfil guardado.');unlocked=await openVault(record,$('passphrase').value);await commit(pruneReceipts(unlocked.data));showUnlocked();message('Perfil desbloqueado. Puede trabajar con los datos preparados sin conexión.');}));
$('lock').addEventListener('click',()=>{if(!dirty||confirm('Hay cambios de formulario sin guardar. ¿Bloquear y descartarlos?'))lock();});
$('refresh').addEventListener('click',()=>run(async()=>{if(dirty)throw Error('Guarde el formulario antes de actualizar.');await context();if(current.person_id!==unlocked.data.person_id)throw Error('Sesión de otra persona.');await commit({...unlocked.data,catalog:catalog(current)});fillOptions();resetForm();renderQueue();message('Datos autorizados actualizados. Los pendientes locales se conservaron.');}));
$('source').addEventListener('change',()=>{editing=null;const v=unlocked.data.catalog.versions.find(v=>v.id===$('source').value);if(v){loadFields({...v,version_id:v.id,farm_id:v.measurement.farm_id,period_id:v.measurement.period_id});dirty=false;}else resetForm();});
$('add').addEventListener('click',()=>{addValue({name:'',value:'',unit:''});dirty=true;});
$('cancel-edit').addEventListener('click',()=>{if(!dirty||confirm('¿Limpiar los cambios de formulario sin guardar?'))resetForm();});
$('draft-form').addEventListener('input',()=>dirty=true);
$('draft-form').addEventListener('submit',e=>{e.preventDefault();run(saveDraft);});
$('sync').addEventListener('click',()=>run(async()=>{if(dirty)throw Error('Guarde el formulario antes de sincronizar.');await sync();}));
$('export').addEventListener('click',()=>run(async()=>{const record=await store.read(unlocked.data.person_id);const blob=new Blob([JSON.stringify(record)],{type:'application/json'});const url=URL.createObjectURL(blob);const link=element('a');link.href=url;link.download=`verdeazul-cifrado-${record.person_id.slice(-8)}.json`;link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);message('Respaldo cifrado exportado. Consérvelo junto con su frase en lugares separados.');}));
$('import').addEventListener('click',()=>run(async()=>{const file=$('import-file').files[0];if(!file||file.size>4500000)throw Error('Seleccione un respaldo de hasta 4.5 MB.');const record=JSON.parse(await file.text());const opened=await openVault(record,$('passphrase').value);if(await store.read(record.person_id))throw Error('El perfil ya existe; no se sobrescriben sus datos.');await store.save(record,null);unlocked=opened;showUnlocked();await profiles();message('Respaldo recuperado. La sincronización volverá a comprobar su sesión y permisos.');}));
for(const name of ['pointerdown','keydown','input'])document.addEventListener(name,()=>lastActivity=Date.now());
setInterval(()=>{if(unlocked&&!busy&&Date.now()-lastActivity>=300000)lock();},10000);
window.addEventListener('beforeunload',e=>{if(dirty){e.preventDefault();e.returnValue='';}});
try{
 if(!window.isSecureContext||!crypto.subtle||!window.indexedDB)throw Error('Se requiere HTTPS o localhost y soporte de Web Crypto e IndexedDB.');
 await profiles();
 if('serviceWorker' in navigator){await navigator.serviceWorker.register('/campo/sw.js',{scope:'/campo/'});await navigator.serviceWorker.ready;}
 try{await context();$('identity').textContent=`Sesión actual: ${current.username}. Puede preparar o desbloquear su perfil.`;await profiles();}catch{$('identity').textContent='Sin sesión de técnico disponible. Puede desbloquear un perfil ya preparado; para sincronizar deberá iniciar sesión.';}
 message('Almacén local listo. Prepare o desbloquee su perfil.');
}catch(e){message(e.message);}

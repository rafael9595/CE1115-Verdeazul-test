import {IndexedStore,createVault,openVault,seal,makeDraft,acceptReceipt,markConflict,pruneReceipts} from './vault.js';
const output=document.getElementById('output');
document.getElementById('start').onclick=async()=>{
 const name='verdeazul-prueba-'+crypto.randomUUID();const store=new IndexedStore(name);let n=0;
 const pass='Frase sintética de prueba 123';const person=crypto.randomUUID();
 const ok=(condition,label)=>{if(!condition)throw Error(label);n++;output.textContent+=`OK ${n}: ${label}\n`;};
 const rejects=async(fn)=>{try{await fn();return false;}catch{return true;}};
 output.textContent='';
 try{
  let v=await createVault(person,pass,{username:'sintetico',farms:[],periods:[],versions:[]});
  v.data.drafts.push(makeDraft(person,{farm_id:crypto.randomUUID(),period_id:crypto.randomUUID(),measured_at:'2026-11-11',methodology:'DATO_PRIVADO_PRUEBA',values:[{name:'carbono','value':'120.00','unit':'tCO2e'}]}));
  v.record=await seal(v.data,v.key,v.record);await store.save(v.record,null);
  const read=await store.read(person);ok(!JSON.stringify(read).includes('DATO_PRIVADO_PRUEBA'),'Contenido cifrado en IndexedDB');
  const opened=await openVault(read,pass);ok(opened.data.drafts.length===1,'Recuperación tras cerrar y abrir la base');
  ok(await rejects(()=>openVault(read,'Frase incorrecta de prueba 123')),'Frase incorrecta rechazada');
  const bad=structuredClone(read);bad.ciphertext=(bad.ciphertext[0]==='A'?'B':'A')+bad.ciphertext.slice(1);
  ok(await rejects(()=>openVault(bad,pass)),'Alteración detectada');
  const changed=await seal(opened.data,opened.key,opened.record);await store.save(changed,read.revision);
  ok(await rejects(()=>store.save(changed,read.revision)),'Escritura de pestaña obsoleta rechazada');
  const draft=opened.data.drafts[0];const conflict=markConflict(opened.data,draft.id,'Período cerrado');
  ok(conflict.drafts[0].payload.methodology==='DATO_PRIVADO_PRUEBA','Conflicto conserva contenido');
  ok(pruneReceipts({...opened.data,receipts:[{received_at:'2000-01-01T00:00:00Z'}]}).drafts.length===1,'Limpieza no elimina pendientes');
  ok(await rejects(async()=>acceptReceipt(opened.data,draft.id,{})),'Confirmación incompleta conserva el pendiente');
  output.textContent+=`\nRESULTADO: ${n}/${n} correctas. Compruebe también el recorrido sin red de la guía.\n`;
 }catch(e){output.textContent+='FALLO: '+e.message+'\n';}
 finally{indexedDB.deleteDatabase(name);}
};

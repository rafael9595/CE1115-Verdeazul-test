// Solo Web Crypto e IndexedDB nativos. La clave y la frase nunca se persisten.
const encoder=new TextEncoder();
const decoder=new TextDecoder('utf-8',{fatal:true});
export const FORMAT='VA-CAMPO-3';
export const ITERATIONS=600000;
const uuid=/^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
function b64(a){let s='';for(const v of new Uint8Array(a))s+=String.fromCharCode(v);return btoa(s);}
function unb64(s){if(typeof s!=='string')throw Error('Respaldo inválido.');return Uint8Array.from(atob(s),c=>c.charCodeAt(0));}
function aad(person,revision){return encoder.encode(`${FORMAT}:${person}:${revision}`);}
function validateRecord(r){
 if(!r||r.format!==FORMAT||!uuid.test(r.person_id)||r.iterations!==ITERATIONS||
    !Number.isSafeInteger(r.revision)||r.revision<1||typeof r.ciphertext!=='string'||r.ciphertext.length>4000000||
    unb64(r.salt).length!==16||unb64(r.iv).length!==12)throw Error('Formato de respaldo no admitido.');
}
async function derive(phrase,salt){
 if(typeof phrase!=='string'||phrase.length<15||phrase.length>1024)throw Error('La frase local debe tener de 15 a 1024 caracteres.');
 const material=await crypto.subtle.importKey('raw',encoder.encode(phrase),'PBKDF2',false,['deriveKey']);
 return crypto.subtle.deriveKey({name:'PBKDF2',salt,iterations:ITERATIONS,hash:'SHA-256'},material,
                               {name:'AES-GCM',length:256},false,['encrypt','decrypt']);
}
export async function seal(data,key,record){
 if(data.person_id!==record.person_id)throw Error('Identidad local distinta.');
 const iv=crypto.getRandomValues(new Uint8Array(12));
 const plain=encoder.encode(JSON.stringify(data));
 if(plain.byteLength>2500000)throw Error('El almacén local llegó al límite de 2.5 MB. Exporte los pendientes.');
 const revision=record.revision+1;
 const ciphertext=await crypto.subtle.encrypt({name:'AES-GCM',iv,additionalData:aad(record.person_id,revision),tagLength:128},key,plain);
 return {format:FORMAT,person_id:record.person_id,iterations:ITERATIONS,salt:record.salt,iv:b64(iv),ciphertext:b64(ciphertext),revision};
}
export async function createVault(person,phrase,catalog){
 if(!uuid.test(person))throw Error('Identidad no válida.');
 const salt=crypto.getRandomValues(new Uint8Array(16));const key=await derive(phrase,salt);
 const data={person_id:person,device_id:crypto.randomUUID(),catalog,drafts:[],receipts:[]};
 const record=await seal(data,key,{person_id:person,salt:b64(salt),revision:0});
 return {key,data,record};
}
export async function openVault(record,phrase){
 validateRecord(record);
 try{
  const key=await derive(phrase,unb64(record.salt));
  const plain=await crypto.subtle.decrypt({name:'AES-GCM',iv:unb64(record.iv),additionalData:aad(record.person_id,record.revision),tagLength:128},key,unb64(record.ciphertext));
  const data=JSON.parse(decoder.decode(plain));
  if(data.person_id!==record.person_id||!Array.isArray(data.drafts)||!Array.isArray(data.receipts)||!uuid.test(data.device_id))throw Error();
  return {key,data,record};
 }catch{throw Error('No se pudo desbloquear: frase incorrecta o archivo alterado.');}
}
export function pruneReceipts(data,now=Date.now()){
 return {...data,receipts:data.receipts.filter(x=>!Number.isFinite(Date.parse(x.received_at))||now-Date.parse(x.received_at)<7*86400000)};
}
export function pendingCounts(data){const pending=data.drafts.filter(d=>d.status!=='RESUELTO');return {pending:pending.length,conflicts:pending.filter(d=>d.status==='CONFLICTO').length};}
export function makeDraft(person,fields){
 if(!uuid.test(person))throw Error('Identidad no válida.');
 return {id:crypto.randomUUID(),attempted:false,status:'PENDIENTE',message:'Guardado localmente.',payload:{
  author_person_id:person,farm_id:fields.farm_id,period_id:fields.period_id,version_id:fields.version_id||null,
  base_revision:fields.version_id?fields.base_revision:0,captured_at:new Date().toISOString(),
  measured_at:fields.measured_at,methodology:fields.methodology,values:structuredClone(fields.values)}};
}
export function acceptReceipt(data,draftId,result){
 const draft=data.drafts.find(d=>d.id===draftId);
 if(!draft||result.request_id!==draftId||result.author_person_id!==data.person_id||!uuid.test(result.receipt_id)||
    !uuid.test(result.version_id)||!Number.isFinite(Date.parse(result.received_at)))throw Error('Confirmación incompleta; el pendiente se conserva.');
 const next=structuredClone(data);
 next.drafts=next.drafts.filter(d=>d.id!==draftId);
 for(const previous of next.drafts)if(previous.replaced_by===draftId){previous.status='RESUELTO';previous.message='Resuelto mediante un intento posterior confirmado.';}
 next.receipts.push({request_id:draftId,receipt_id:result.receipt_id,version_id:result.version_id,received_at:result.received_at});
 return next;
}
export function markConflict(data,id,message){const next=structuredClone(data);const draft=next.drafts.find(d=>d.id===id);if(draft){draft.status='CONFLICTO';draft.message=message;}return next;}
export function rebaseDraft(data,id,current){
 const old=data.drafts.find(d=>d.id===id);
 if(!old||old.status!=='CONFLICTO'||!old.payload.version_id||current.id!==old.payload.version_id||current.status!=='BORRADOR'||!Number.isSafeInteger(current.edit_revision))throw Error('No hay una versión editable compatible.');
 const next=structuredClone(data);const copy=makeDraft(data.person_id,{...old.payload,base_revision:current.edit_revision});
 next.drafts.find(d=>d.id===id).replaced_by=copy.id;next.drafts.push(copy);return next;
}
export class IndexedStore{
 constructor(name='verdeazul-campo-v3'){this.name=name;}
 async db(){return new Promise((resolve,reject)=>{const req=indexedDB.open(this.name,1);req.onupgradeneeded=()=>req.result.createObjectStore('vaults',{keyPath:'person_id'});req.onsuccess=()=>resolve(req.result);req.onerror=()=>reject(req.error);});}
 async read(id){const db=await this.db();return new Promise((resolve,reject)=>{const tx=db.transaction('vaults','readonly');const req=tx.objectStore('vaults').get(id);let result;req.onsuccess=()=>result=req.result;tx.oncomplete=()=>{db.close();resolve(result);};tx.onerror=()=>{db.close();reject(tx.error);};});}
 async list(){const db=await this.db();return new Promise((resolve,reject)=>{const tx=db.transaction('vaults','readonly');const req=tx.objectStore('vaults').getAll();let rows;req.onsuccess=()=>rows=req.result;tx.oncomplete=()=>{db.close();resolve(rows);};tx.onerror=()=>{db.close();reject(tx.error);};});}
 async save(record,expectedRevision){
  validateRecord(record);const db=await this.db();
  return new Promise((resolve,reject)=>{
   let conflict=false;let tx;
   try{tx=db.transaction('vaults','readwrite',{durability:'strict'});}catch{tx=db.transaction('vaults','readwrite');}
   const store=tx.objectStore('vaults');const req=store.get(record.person_id);
   req.onsuccess=()=>{const old=req.result;if((old?.revision??null)!==expectedRevision){conflict=true;tx.abort();}else store.put(record);};
   tx.oncomplete=()=>{db.close();resolve(record);};
   tx.onabort=()=>{db.close();reject(Error(conflict?'Otra pestaña cambió el almacén. Bloquee y vuelva a desbloquear antes de continuar.':'No se confirmó la escritura local. Conserve la página y exporte los pendientes.'));};
   tx.onerror=()=>{};
  });
 }
}

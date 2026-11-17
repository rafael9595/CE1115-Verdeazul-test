const rows=document.querySelector('#value-rows');
if(rows){
 document.querySelector('#add-value').addEventListener('click',()=>{
  if(rows.children.length>=50)return;
  const row=rows.firstElementChild.cloneNode(true);row.querySelectorAll('input').forEach(x=>x.value='');rows.append(row);
 });
 rows.addEventListener('click',e=>{if(e.target.matches('.remove-value')&&rows.children.length>1)e.target.closest('.value-row').remove();});
}

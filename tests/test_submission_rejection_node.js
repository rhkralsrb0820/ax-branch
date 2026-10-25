// Confirmed pre-creation rejection may reset a receipt; ambiguous/partial outcomes may not.
const {createPage}=require('./test_webui_node'),assert=require('node:assert/strict'),fs=require('node:fs');
const checks=[],pages=[],storage=new Map(),receipts=new Map(),requests=[];
let mode='reject',launches=0;
const json=(data,status=200)=>new Response(JSON.stringify(data),{status});
const until=async f=>{for(let i=0;i<100;i++){if(f())return;await new Promise(r=>setTimeout(r,10));}throw Error('condition timed out');};
const check=(name,ok)=>{checks.push({name,ok});assert(ok,name);};
function page(){
 const p=createPage({storage,async fetchOverride(url,opt,base){
   if(url==='/api/projects'){
     const body=JSON.parse(opt.body);requests.push(body);
     if(mode==='reject')return json({error:'invalid input',submission:'rejected_before_creation',request_id:body.request_id},400);
     if(mode==='lost-rejection'){mode='reject';throw Error('lost validation response');}
     if(mode==='generic')return json({error:'unclassified failure'},400);
     if(mode==='wrong-id')return json({error:'mismatched request',submission:'rejected_before_creation',request_id:'some-other-request'},400);
     if(mode==='server-error')return json({error:'unexpected failure',submission:'rejected_before_creation',request_id:body.request_id},500);
     const id='P-20261025-'+String(receipts.size+1).padStart(6,'0');receipts.set(body.request_id,id);
     if(mode==='partial')return json({error:'attachment failed after creation'},400);
     launches++;return json({id,created:true});
   }
   if(String(url).startsWith('/api/submission?'))return json({id:receipts.get(new URL(url,'http://fixture').searchParams.get('request_id'))||null});
   return base(url,opt);
 }});pages.push(p);p.load();return p;
}
(async()=>{
 let p=page();await until(()=>p.context.AXB.ov);
 p.nodes.get('goal').value='첨부와 부서 수정';p.context.AXB.files=[{name:'bad name.csv',data:'YQ=='}];p.context.AXB.pending=['removed'];
 await p.nodes.get('submit').click();const rejectedId=requests.at(-1).request_id;
 check('confirmed pre-creation rejection clears only pending ID',!storage.has('axb-pending-submission')&&p.context.AXB.requestId===null&&receipts.size===0&&launches===0);
 check('rejection retains editable goal and explains correction',p.nodes.get('goal').value==='첨부와 부서 수정'&&p.nodes.get('notice').textContent.includes('수정하고 다시 제출'));
 mode='success';p.context.AXB.files=[{name:'ok.csv',data:'YQ=='}];p.context.AXB.pending=['research'];
 await p.nodes.get('submit').click();
 check('corrected attachment and department create exactly once with new ID',receipts.size===1&&launches===1&&requests.at(-1).request_id!==rejectedId&&requests.at(-1).departments[0]==='research');
 p.close();p=page();await until(()=>p.context.AXB.ov);
 mode='lost-rejection';p.nodes.get('goal').value='거절 응답 유실';await p.nodes.get('submit').click();
 const uncertain=JSON.parse(storage.get('axb-pending-submission'));p.close();p=page();await until(()=>p.nodes.get('goal').value===uncertain.goal);
 check('lost rejection response stays uncertain after reload',storage.has('axb-pending-submission')&&p.context.AXB.requestId===uncertain.id);
 await p.nodes.get('submit').click();
 check('explicit retry obtains confirmed rejection before unlocking edits',!storage.has('axb-pending-submission')&&receipts.size===1&&launches===1);
 for(const errorMode of ['generic','wrong-id','server-error']){
   mode=errorMode;p.nodes.get('goal').value=errorMode;await p.nodes.get('submit').click();
   check(errorMode+' cannot clear uncertain receipt',storage.has('axb-pending-submission'));
   // Obtain the genuine pre-creation rejection before proceeding to the next test input.
   mode='reject';await p.nodes.get('submit').click();
 }
 mode='partial';p.nodes.get('goal').value='부분 생성';await p.nodes.get('submit').click();
 const partial=JSON.parse(storage.get('axb-pending-submission')),count=requests.length;
 check('partial creation preserves receipt instead of allowing new goal',!!partial&&receipts.has(partial.id)&&launches===1);
 p.close();p=page();await until(()=>p.context.AXB.project);
 check('partial creation reload recovers same project without POST or launch',p.context.AXB.pid===receipts.get(partial.id)&&requests.length===count&&receipts.size===2&&launches===1);
})().catch(e=>{checks.push({name:e.stack,ok:false});process.exitCode=1;}).finally(()=>{
 for(const p of pages)p.close();for(const c of checks)console.log(`${c.ok?'PASS':'FAIL'} ${c.name}`);
 if(process.argv[2])fs.writeFileSync(process.argv[2],JSON.stringify({runner:'Node DOM fixture only',passed:checks.filter(c=>c.ok).length,total:checks.length,checks},null,2));
});

// Reload uses a new VM/page, the same sessionStorage and the same receipt server fixture.
const {createPage}=require('./test_webui_node'), assert=require('node:assert/strict'), fs=require('node:fs');
const storage=new Map(), receipts=new Map(), pages=[], checks=[], requests=[];
let launches=0, lose=true, failBeforeCommit=false;
const json=d=>new Response(JSON.stringify(d));
const until=async f=>{for(let i=0;i<100;i++){if(f())return;await new Promise(r=>setTimeout(r,10));}throw Error('condition timed out');};
const report=(name,ok)=>{checks.push({name,ok});assert(ok,name);};
function page(){
  const p=createPage({storage,async fetchOverride(url,opt,base){
    if(url==='/api/projects'){
      const body=JSON.parse(opt.body);requests.push(body);
      if(failBeforeCommit) throw Error('connection failed before commit');
      let id=receipts.get(body.request_id),created=!id;
      if(!id){id='P-20261025-'+String(receipts.size+1).padStart(6,'0');receipts.set(body.request_id,id);launches++;}
      if(lose){lose=false;throw Error('server committed, client lost response');}
      return json({id,created});
    }
    if(String(url).startsWith('/api/submission?'))return json({id:receipts.get(new URL(url,'http://fixture').searchParams.get('request_id'))||null});
    return base(url,opt);
  }});pages.push(p);p.load();return p;
}
(async()=>{
  let p=page();await until(()=>p.context.AXB.ov);
  p.nodes.get('goal').value='같은 제출';await p.nodes.get('submit').click();
  report('W2 committed response loss retains pending receipt',storage.has('axb-pending-submission')&&receipts.size===1);
  const firstId=requests[0].request_id;p.close();
  p=page();await until(()=>p.context.AXB.project);
  report('W2 reload queries receipt and opens existing project',p.context.AXB.project.id===[...receipts.values()][0]);
  report('W2 reload causes exactly one project and launch',requests.length===1&&receipts.size===1&&launches===1);
  report('W2 recovery clearly labelled and storage cleared',p.nodes.get('notice').textContent.includes('복구')&&!storage.has('axb-pending-submission'));
  p.nodes.get('goal').value='의도한 새 목표';await p.nodes.get('submit').click();
  report('W2 intentional new goal gets distinct request',requests.length===2&&requests[1].request_id!==firstId&&receipts.size===2&&launches===2);
  failBeforeCommit=true;p.nodes.get('goal').value='아직 접수 안 된 목표';await p.nodes.get('submit').click();
  const pending=JSON.parse(storage.get('axb-pending-submission'));p.close();p=page();await until(()=>p.nodes.get('goal').value==='아직 접수 안 된 목표');
  report('W2 unconfirmed reload restores draft and original ID',p.context.AXB.requestId===pending.id);
  p.nodes.get('goal').value='다른 목표';await p.nodes.get('submit').click();
  report('W2 changed goal cannot reuse uncertain request ID',requests.length===3&&p.nodes.get('notice').textContent.includes('같은 목표'));
  p.nodes.get('goal').value=pending.goal;failBeforeCommit=false;await p.nodes.get('submit').click();
  report('W2 retry keeps original request ID',requests.length===4&&requests[3].request_id===pending.id&&launches===3);
  // Metadata is persisted; attachment contents never are. A reload requires reattachment before retry.
  p.context.AXB.files=[{name:'private.txt',data:'c2VjcmV0'}];failBeforeCommit=true;p.nodes.get('goal').value='첨부 복구';await p.nodes.get('submit').click();
  report('W2 stores attachment metadata without contents',!storage.get('axb-pending-submission').includes('c2VjcmV0'));
  p.close();p=page();await until(()=>p.nodes.get('goal').value==='첨부 복구');
  const count=requests.length;await p.nodes.get('submit').click();
  report('W2 missing reattached file blocks replay',requests.length===count&&p.nodes.get('fileNames').textContent.includes('다시 첨부'));
  p.context.AXB.files=[{name:'private.txt',data:'c2VjcmV0'}];failBeforeCommit=false;await p.nodes.get('submit').click();
  report('W2 same reattached file allows explicit retry',requests.length===count+1);
  p.close();storage.set('axb-pending-submission','{broken');p=page();await until(()=>p.context.AXB.ov);
  const beforeCorrupt=requests.length;p.nodes.get('goal').value='저장소 오류';await p.nodes.get('submit').click();
  report('W2 corrupt pending record prevents unsafe new submission',requests.length===beforeCorrupt&&p.nodes.get('notice').textContent.includes('제출을 멈췄습니다'));
})().catch(e=>{checks.push({name:e.stack,ok:false});process.exitCode=1;}).finally(()=>{
  for(const p of pages)p.close();for(const c of checks)console.log(`${c.ok?'PASS':'FAIL'} ${c.name}`);
  if(process.argv[2])fs.writeFileSync(process.argv[2],JSON.stringify({runner:'Node DOM fixture, not a real server/browser',passed:checks.filter(c=>c.ok).length,total:checks.length,checks},null,2));
});

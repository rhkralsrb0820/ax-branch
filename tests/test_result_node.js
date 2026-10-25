const {createPage}=require('./test_webui_node'),assert=require('node:assert/strict'),fs=require('node:fs');
const a='P-20261025-aaaaaa',b='P-20261025-bbbbbb',checks=[],calls=[];
let delayed,hold=false;
const response=d=>new Response(JSON.stringify(d));
const page=createPage({async fetchOverride(url,opt,base){
  if(url==='/api/library')return response({types:['Notes'],entries:[{project:a,title:'문서',type:'Notes',version:2,verification:'PASS',versions:[{version:2}]}]});
  if(String(url).endsWith('/result')){
    calls.push(url);if(hold){hold=false;await new Promise(r=>{delayed=r;});}
    return response({title:'검증된 결과',text:'확인된 문서 '+url});
  }
  return base(url,opt);
}});
const tick=()=>new Promise(r=>setImmediate(r));
const check=(name,ok)=>{checks.push({name,ok});assert(ok,name);};
(async()=>{
  page.load();await tick();await page.context.AXB.openProject(b);
  page.context.AXB.show('library');await tick();
  const button=page.nodes.get('libraryList').querySelectorAll('[data-open]')[0];
  await button.click();
  check('result library opens document for its own project',page.nodes.get('modal').open&&page.nodes.get('modalBody').textContent.includes(a));
  check('result library keeps selected project identity',page.context.AXB.pid===b);
  page.nodes.get('modal').close();hold=true;const prior=button.click();await tick();
  await page.context.AXB.openProject(b);delayed();await prior;
  check('delayed library result ignored after project navigation',!page.nodes.get('modal').open);
  await page.nodes.get('oRun').click();
  check('project result opens visible project result',page.nodes.get('modal').open&&page.nodes.get('modalBody').textContent.includes(b)&&calls.at(-1).includes(b));
})().catch(e=>{checks.push({name:e.stack,ok:false});process.exitCode=1;}).finally(()=>{
  page.close();for(const c of checks)console.log(`${c.ok?'PASS':'FAIL'} ${c.name}`);
  if(process.argv[2])fs.writeFileSync(process.argv[2],JSON.stringify({runner:'Node DOM fixture, not actual engine verification',passed:checks.filter(c=>c.ok).length,total:checks.length,checks},null,2));
});

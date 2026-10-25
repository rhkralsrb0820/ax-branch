// Real app.js in the Node DOM fixture. This is not Python/backend/real browser acceptance.
const {createPage}=require('./test_webui_node'),assert=require('node:assert/strict'),fs=require('node:fs');
const a='P-20261025-aaaaaa',b='P-20261025-bbbbbb',checks=[];
const page=createPage({async fetchOverride(url,opt,base){
 const r=await base(url,opt);
 if(url==='/api/project/'+a){const p=await r.json();
   p.attached=[{id:'product-planning',version:'1.0.0'}];
   p.experience={records:[{experience_id:'E-fixture',outcome:'FAIL',execution_mode:'injected'}],searches:[],
     uses:[{experience:'E-fixture',disposition:'REJECTED',reason:'customer <private>',difference:'different market'}],errors:[]};
   return new Response(JSON.stringify(p));}
 if(url==='/api/project/'+b){const p=await r.json();p.experience={records:[],uses:[],searches:[{status:'none'}],errors:[]};return new Response(JSON.stringify(p));}
 return r;
}});
const check=(name,ok)=>{checks.push({name,ok});assert(ok,name);};
(async()=>{
 page.load();await new Promise(r=>setImmediate(r));await page.context.AXB.openProject(a);
 let html=page.nodes.get('experience').innerHTML;
 check('experience displays reason, difference and uncertainty',html.includes('REJECTED')&&html.includes('different market')&&html.includes('개선은 비교 평가 전까지 미확인'));
 check('experience escapes retrieved text and folds technical details',!html.includes('<private>')&&html.includes('&lt;private&gt;')&&html.includes('<details>'));
 check('attached department shows pinned version',page.nodes.get('projectChips').innerHTML.includes('v1.0.0'));
 await page.context.AXB.openProject(b);html=page.nodes.get('experience').innerHTML;
 check('experience switching clears prior source and shows no match',!html.includes('E-fixture')&&html.includes('관련 경험을 찾지 못했습니다'));
})().catch(e=>{checks.push({name:e.stack,ok:false});process.exitCode=1;}).finally(()=>{
 page.close();for(const c of checks)console.log(`${c.ok?'PASS':'FAIL'} ${c.name}`);
 if(process.argv[2])fs.writeFileSync(process.argv[2],JSON.stringify({runner:'Node DOM fixture only',passed:checks.filter(c=>c.ok).length,total:checks.length,checks},null,2));
});

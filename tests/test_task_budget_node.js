// Shipped UI logic with a small DOM fixture. No browser, provider or user workspace is contacted.
const {createPage} = require('./test_webui_node');
const assert = require('node:assert/strict');
const storage = new Map(), checks = [], requests = [];
const json = d => new Response(JSON.stringify(d));
const until = async f => { for (let i=0;i<100;i++) { if (f()) return; await new Promise(r=>setTimeout(r,10)); } throw Error('condition timed out'); };
const report = (name, ok) => { checks.push({name,ok}); assert(ok,name); };
const profiles = [
  {id:'general',label:'기본 업무',max_reported_tokens:250000},
  {id:'product_planning',label:'상품기획',max_reported_tokens:150000},
  {id:'csv_analysis',label:'CSV 분석·후속 수정',max_reported_tokens:250000},
  {id:'web_app',label:'웹·서버형 결과물',max_reported_tokens:250000}
];
let page, failBeforeCommit=true, budget;
function create() {
  const p=createPage({storage,async fetchOverride(url,opt,base) {
    if(url==='/api/overview') { const d=await (await base(url,opt)).json(); return json({...d,task_budgets:profiles}); }
    if(url==='/api/projects') { requests.push(JSON.parse(opt.body)); if(failBeforeCommit) throw Error('response uncertain'); return json({id:'P-20261028-000001',created:true}); }
    if(String(url).startsWith('/api/submission?')) return json({id:null});
    if(String(url).match(/^\/api\/project\/P-[^/]+$/)) {
      const d=await (await base(url,opt)).json();
      return json({...d,state:budget?.paused?'PAUSED':'OWNER_REVIEW',pause_reason:budget?.paused?'Execution budget reserve':'',
        required_unmet:{},execution_budget:budget});
    }
    return base(url,opt);
  }});
  p.load();return p;
}
(async()=>{
  page=create();await until(()=>page.context.AXB.ov);
  report('default budget is explicit general250k',page.nodes.get('taskType').value==='general' && page.nodes.get('taskBudgetNote').textContent.includes('250,000'));
  page.nodes.get('taskType').value='product_planning';page.nodes.get('taskType').onchange();
  report('product choice explains150k cumulative allowance',page.nodes.get('taskBudgetNote').textContent.includes('150,000') && page.nodes.get('taskBudgetNote').textContent.includes('수정·재개'));
  page.nodes.get('goal').value='상품기획';page.context.AXB.pending=['research'];page.context.AXB.required=['research'];
  await page.nodes.get('submit').click();
  report('receipt records profile and required departments',JSON.parse(storage.get('axb-pending-submission')).task_type==='product_planning' && JSON.parse(storage.get('axb-pending-submission')).required[0]==='research');
  report('request sends selected budget profile',requests[0].task_type==='product_planning');
  page.close();page=create();await until(()=>page.nodes.get('goal').value==='상품기획');
  report('reload restores selected profile and required departments',page.nodes.get('taskType').value==='product_planning' && page.context.AXB.required[0]==='research');
  page.nodes.get('taskType').value='web_app';await page.nodes.get('submit').click();
  report('uncertain submission cannot change budget on retry',requests.length===1 && page.nodes.get('notice').textContent.includes('업무 종류'));
  page.nodes.get('taskType').value='product_planning';failBeforeCommit=false;await page.nodes.get('submit').click();
  report('same-profile retry retains original request id',requests.length===2 && requests[1].request_id===requests[0].request_id);
  budget={configured:true,label:'상품기획',reported_tokens:123000,known_tokens:123000,max_reported_tokens:150000,max_calls:20,max_seconds:3600,max_prompt_chars:200000,started_calls:8,paused:true,acceptance_pending:true,stop:{reserve:30000,remaining:27000,downstream:[]}};
  await page.context.AXB.openProject('P-20261028-000001');
  report('verified acceptance pause is not presented as completion',page.nodes.get('executionBudget').textContent.includes('최종 수락 대기') && page.nodes.get('executionBudget').textContent.includes('아직 끝나지 않았'));
  report('project card shows cumulative actual and limit',page.nodes.get('executionBudget').textContent.includes('123,000') && page.nodes.get('executionBudget').textContent.includes('150,000'));
  budget={...budget,reported_tokens:null,acceptance_pending:false};await page.context.AXB.openProject('P-20261028-000001');
  report('unreported usage is unknown rather than zero',page.nodes.get('executionBudget').textContent.includes('집계 대기·미확인') && page.nodes.get('executionBudget').textContent.includes('확인된 사용량 123,000'));
  budget=undefined;await page.context.AXB.openProject('P-20261028-000002');
  report('other project cannot retain previous budget card',page.nodes.get('executionBudget').hidden);
  console.log(JSON.stringify({runner:'Node DOM fixture, not browser',passed:checks.length,total:checks.length,checks},null,2));
})().catch(e=>{console.error(e);process.exitCode=1;}).finally(()=>page?.close());

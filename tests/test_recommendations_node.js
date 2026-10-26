// Real app.js with a DOM fixture: escaping, explicit acceptance and project isolation.
const {createPage}=require('./test_webui_node'),assert=require('node:assert/strict');
const a='P-20261027-aaaaaa',b='P-20261027-bbbbbb',posts=[];
let status='pending';
const page=createPage({async fetchOverride(url,opt,base){
  if(opt?.method==='POST' && url===`/api/project/${a}/recommendation`){
    posts.push(JSON.parse(opt.body));status='accepted';
    return new Response(JSON.stringify({changed:true}));
  }
  const r=await base(url,opt);
  if(url===`/api/project/${a}`){const p=await r.json();
    p.recommendations=[{id:7,department:'research',version:'1.1.0',lifecycle:'legacy',status,
      available:true,reason:'inspect <script>private</script>',note:'no execution'}];
    return new Response(JSON.stringify(p));}
  return r;
}});
(async()=>{
  page.load();await new Promise(r=>setImmediate(r));await page.context.AXB.openProject(a);
  let card=page.nodes.get('recommendations');
  assert.equal(posts.length,0,'display must not accept or launch');
  assert(card.innerHTML.includes('&lt;script&gt;')&&!card.innerHTML.includes('<script>'));
  assert(card.innerHTML.includes('작업 품질 미판정'));
  console.log('PASS bounded recommendation data escaped and legacy status honest');
  await card.querySelectorAll('[data-recommend]')[0].click();
  assert.deepEqual(posts,[{id:7,decision:'accepted'}]);
  assert(page.nodes.get('recommendations').innerHTML.includes('연결됨'));
  console.log('PASS only explicit Owner acceptance posts the project-specific decision');
  await page.context.AXB.openProject(b);
  assert.equal(page.nodes.get('recommendations').hidden,true);
  assert(!page.nodes.get('recommendations').innerHTML.includes('private'));
  console.log('PASS another project clears prior recommendation content');
})().catch(e=>{console.error(e);process.exitCode=1;}).finally(()=>page.close());

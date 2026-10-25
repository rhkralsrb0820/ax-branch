// Standard-library DOM fixture for app.js logic. This does not validate a browser's layout or rendering.
const vm = require('node:vm'), fs = require('node:fs'), path = require('node:path'), assert = require('node:assert/strict');
const nodes = new Map(), radios = [], stages = [], posts = [], reports = [];
class Element {
  constructor(id='') { this.id=id; this.dataset={}; this.value=''; this.textContent=''; this.hidden=false; this.style={}; this.checked=false; this.disabled=false;
    this.classList={add(){},remove(){},toggle(){}}; }
  set innerHTML(html) {
    this.html=html; this.textContent=html.replace(/<[^>]*>/g,'');
    for (const [id,e] of nodes) if (e.parent===this) nodes.delete(id);
    if (this.id==='owner') radios.length=0;
    if (this.id==='pipeline') stages.length=0;
    for (const m of html.matchAll(/<([\w]+)\b([^>]*)>/g)) {
      const attrs=m[2], id=/\bid="([^"]+)"/.exec(attrs)?.[1], e=new Element(id);
      e.parent=this;
      if (id) nodes.set(id,e);
      for (const d of attrs.matchAll(/data-([\w-]+)="([^"]*)"/g)) e.dataset[d[1]]=d[2];
      if (/name="works"/.test(attrs)) { e.value=/value="([^"]+)"/.exec(attrs)[1]; e.checked=/\bchecked\b/.test(attrs); radios.push(e); }
      if (/class="stage /.test(attrs)) stages.push(e);
    }
  }
  get innerHTML(){return this.html||'';}
  querySelectorAll(sel){return sel==='input[name=works]' ? radios : sel==='.stage' ? stages : [];}
  addEventListener(){} appendChild(){} focus(){} showModal(){} close(){}
  click(){ if(!this.disabled && this.onclick) return this.onclick(); }
}
const ids=[...fs.readFileSync(path.join(__dirname,'../axbranch/webui/index.html'),'utf8').matchAll(/id="([^"]+)"/g)].map(m=>m[1]);
for(const id of ids) nodes.set(id,new Element(id));
const document={hidden:false,body:new Element(),createElement:()=>new Element(),querySelector(sel){
  if(sel.startsWith('#')) return nodes.get(sel.slice(1))||null;
  if(sel==='meta[name=axb-token]') return {content:'fixture'};
  if(sel==='input[name=works]:checked') return radios.find(r=>r.checked)||null;
  if(sel==='.stage') return stages[0];
  return null;
},querySelectorAll:()=>[],addEventListener(){}};
const project=id=>({id,title:id,state:'OWNER_REVIEW',status:'WAITING_OWNER',iteration:2,banner:{text:id,color:'#fff'},attached:[],pipeline:[],verifications:[],acceptance:{},conflicts:[],contract:[],timeline:[],owner:{mode:'review',note:id+' 안내'}});
const json=d=>new Response(JSON.stringify(d),{headers:{'Content-Type':'application/json'}});
let done;
const finished=new Promise(r=>{done=r;});
const timers=new Set();
const sandbox={document,Response,URL,URLSearchParams,crypto:require('node:crypto').webcrypto,console,Date,Math,Promise,
  location:{search:'',reload(){}},sessionStorage:{getItem(){return null;},setItem(){},removeItem(){}},
  setTimeout(fn,ms){const t=setTimeout(fn,ms);timers.add(t);return t;},clearTimeout, setInterval(){},
  AXOrb:class{set(){} pulse(){} wake(){}},
  async fetch(url,opt){const u=new URL(url,'http://fixture');
    if(opt?.method==='POST') {const body=JSON.parse(opt.body);posts.push({path:u.pathname,body});
      if(u.pathname==='/api/test/report') reports.push(body);
      if(u.pathname==='/api/test/done') done(); return json({});}
    if(u.pathname==='/api/test/posts') return json(posts.slice());
    if(u.pathname==='/api/overview') return json({version:'test',settings:{},projects:[],groups:[],departments:[],refused:[],delegated:[],orb:'idle',orb_text:{idle:['','','']}});
    if(u.pathname==='/api/feeds') return json({});
    if(u.pathname.endsWith('/records')) return json({records:['기록']});
    if(u.pathname.startsWith('/api/project/')) return json(project(u.pathname.split('/')[3]));
    throw Error('unexpected '+url);
  }};
sandbox.window=sandbox;
const context=vm.createContext(sandbox);
(async()=>{
  vm.runInContext(fs.readFileSync(path.join(__dirname,'../axbranch/webui/app.js'),'utf8'),context);
  await new Promise(r=>setImmediate(r));
  vm.runInContext(fs.readFileSync(path.join(__dirname,'web_regressions.js'),'utf8'),context);
  await Promise.race([finished,new Promise((_,reject)=>{const t=setTimeout(()=>reject(Error('timeout')),15000);timers.add(t);})]);
  for(const r of reports) console.log(`${r.ok?'PASS':'FAIL'} ${r.name} ${r.detail||''}`);
  const summary={runner:'Node DOM fixture, not a real browser',passed:reports.filter(r=>r.ok).length,total:reports.length,checks:reports};
  if(process.argv[2]) fs.writeFileSync(process.argv[2],JSON.stringify(summary,null,2));
  assert(reports.length>0 && reports.every(r=>r.ok));
})().catch(e=>{console.error(e);process.exitCode=1;}).finally(()=>{for(const t of timers)clearTimeout(t);});

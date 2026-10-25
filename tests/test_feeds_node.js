const {createPage}=require('./test_webui_node'),assert=require('node:assert/strict'),fs=require('node:fs');
const now=Date.now()/1000,checks=[];
let feeds={'AI 동향':{source:'https://openai.com/news/rss.xml',fetched:now-172800,error:'timeout <untrusted>',items:
  [1,5,2,4,3].map(n=>({title:'기사 '+n,url:'https://openai.com/news/'+n,summary:'내용',published:now-n*1000}))},
  'AI 취업':{source:'https://www.python.org/jobs/feed/rss/',items:[],fetched:null,error:'HTTP 503'}};
const page=createPage({async fetchOverride(url,opt,base){if(url==='/api/feeds')return new Response(JSON.stringify(feeds));return base(url,opt);}});
const tick=()=>new Promise(r=>setImmediate(r));
const check=(name,ok)=>{checks.push({name,ok});assert(ok,name);};
(async()=>{
  page.load();await tick();await tick();
  let html=page.nodes.get('feed-AI 동향').innerHTML;
  check('W3 old nonempty cache shows refresh failure and age',html.includes('갱신 실패')&&html.includes('오래된 정보')&&html.includes('이전 수집 자료'));
  check('W3 failed refresh keeps last successful fetched timestamp',html.includes(new Date(feeds['AI 동향'].fetched*1000).toLocaleString()));
  check('W3 source and publication time visible',html.includes('openai.com')&&html.includes('게시:'));
  check('W3 home shows latest three in publication order',(html.match(/class="feed-item"/g)||[]).length===3&&html.indexOf('기사 1')<html.indexOf('기사 2')&&html.indexOf('기사 2')<html.indexOf('기사 3')&&!html.includes('기사 4'));
  check('W3 failure text escaped',html.includes('&lt;untrusted&gt;')&&!html.includes('<untrusted>'));
  let jobs=page.nodes.get('feed-AI 취업').innerHTML;
  check('W3 empty failed source shows failure and never collected',jobs.includes('HTTP 503')&&jobs.includes('수집 전')&&jobs.includes('아직 수집한 자료가 없습니다'));
  page.context.AXB.show('feed:AI 동향');await tick();
  check('W3 full feed retains all five items',(page.nodes.get('feedFull').innerHTML.match(/class="feed-item"/g)||[]).length===5);
  feeds['AI 동향']={...feeds['AI 동향'],fetched:now,error:'',items:[{title:'성공',url:'https://openai.com/news/new',summary:'내용',published:null}]};
  page.context.AXB.show('home');await tick();html=page.nodes.get('feed-AI 동향').innerHTML;
  check('W3 successful refresh clears failure and stale indicators',!html.includes('갱신 실패')&&!html.includes('오래된 정보')&&html.includes('성공'));
  check('W3 missing publication date explicitly labelled',html.includes('게시일 미상'));
})().catch(e=>{checks.push({name:e.stack,ok:false});process.exitCode=1;}).finally(()=>{
  page.close();for(const c of checks)console.log(`${c.ok?'PASS':'FAIL'} ${c.name}`);
  if(process.argv[2])fs.writeFileSync(process.argv[2],JSON.stringify({runner:'Node DOM fixture, no live public fetch',passed:checks.filter(c=>c.ok).length,total:checks.length,checks},null,2));
});

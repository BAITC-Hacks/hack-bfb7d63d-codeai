'use strict';

const ICONS = {
  network:'<circle cx="5" cy="6" r="2"/><circle cx="18" cy="4" r="2"/><circle cx="12" cy="13" r="3"/><circle cx="4" cy="20" r="2"/><circle cx="20" cy="19" r="2"/><path d="m7 7 3 4m4-1 3-4M10 15l-4 4m9-4 3 3"/>',
  rank:'<path d="M4 20V12h4v8m3 0V4h4v16m3 0v-9h4v9"/>',
  layers:'<path d="m12 3 10 5-10 5L2 8l10-5Zm-9 10 9 5 9-5M3 18l9 5 9-5"/>',
  scan:'<path d="M8 3H3v5m13-5h5v5M3 16v5h5m13-5v5h-5M8 12h8m-4-4v8"/>',
  upload:'<path d="M12 16V3m-5 5 5-5 5 5M4 16v5h16v-5"/>',
  download:'<path d="M12 3v13m-5-5 5 5 5-5M4 16v5h16v-5"/>',
  book:'<path d="M12 5v16M3 3h5l4 2 4-2h5v16h-5l-4 2-4-2H3V3Z"/>',
  refresh:'<path d="M20 8a8 8 0 0 0-14-3L3 8m0-5v5h5M4 16a8 8 0 0 0 14 3l3-3m0 5v-5h-5"/>',
  help:'<circle cx="12" cy="12" r="9"/><path d="M9.5 9a2.5 2.5 0 0 1 5 0c0 2-2.5 2-2.5 4m0 3v.01"/>',
  plus:'<path d="M12 5v14M5 12h14"/>',
  'arrow-up-right':'<path d="M6 18 18 6M6 6h12v12"/>',
  'arrow-right':'<path d="M4 12h16m-6-6 6 6-6 6"/>',
  nodes:'<rect x="3" y="3" width="6" height="6" rx="1"/><rect x="15" y="15" width="6" height="6" rx="1"/><path d="M9 6h9v9M6 9v9h9"/>',
  arrows:'<path d="M3 7h17l-4-4m4 14H3l4 4m13-14-4 4M3 17l4-4"/>',
  expand:'<path d="M8 3H3v5m13-5h5v5M3 16v5h5m13-5v5h-5"/>',
  search:'<circle cx="10" cy="10" r="6"/><path d="m15 15 6 6"/>',
  close:'<path d="m6 6 12 12M6 18 18 6"/>',
  mouse:'<rect x="6" y="2" width="12" height="20" rx="6"/><path d="M12 2v6"/>',
  pulse:'<path d="M2 12h5l3-8 4 16 3-8h5"/>',
  spark:'<path d="m12 2 3 7 7 3-7 3-3 7-3-7-7-3 7-3Zm7 0v4m-2-2h4"/>',
  shield:'<path d="m12 3 8 3v6c0 5-8 9-8 9S4 17 4 12V6l8-3Z"/><path d="m8 12 3 3 5-6"/>',
  warning:'<path d="m12 3 10 18H2L12 3Zm0 6v5m0 3v.1"/>',
  check:'<path d="m5 12 4 4L19 6"/>',
  file:'<path d="M14 2H5v20h14V7l-5-5Zm0 0v5h5M8 12h8m-8 4h8"/>',
  route:'<circle cx="5" cy="5" r="2"/><circle cx="19" cy="19" r="2"/><path d="M7 5h9a4 4 0 0 1 0 8H8a3 3 0 0 0 0 6h9"/>',
};
const icon = (name) => `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${ICONS[name] || ICONS.nodes}</svg>`;
document.querySelectorAll('[data-icon]').forEach(el => { el.innerHTML = icon(el.dataset.icon); });
const $ = (s) => document.querySelector(s);
const $$ = (s) => [...document.querySelectorAll(s)];
const escapeHTML = (v) => String(v ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const gidKey = (v) => String(v);
const num = (n) => Number.isFinite(Number(n)) ? Number(n) : 0;
const integer = new Intl.NumberFormat('kk-KZ', {maximumFractionDigits:0});
const decimal = new Intl.NumberFormat('kk-KZ', {maximumFractionDigits:1});
const count = (n) => integer.format(num(n));
const percent = (v) => Math.round(Math.max(0, Math.min(1, num(v))) * 100);
const shortMoney = (v) => { const n = num(v); return n >= 1e9 ? decimal.format(n/1e9)+' млрд ₸' : n >= 1e6 ? decimal.format(n/1e6)+' млн ₸' : n >= 1e3 ? decimal.format(n/1e3)+' мың ₸' : count(n)+' ₸'; };
const fullMoney = (v) => count(v)+' ₸';
const niceDate = (v) => { if (!v) return '—'; const d = new Date(String(v).slice(0,10)+'T12:00:00'); return Number.isNaN(d.getTime()) ? String(v) : d.toLocaleDateString('kk-KZ', {day:'2-digit',month:'2-digit',year:'numeric'}); };

const ROLES = {
  consolidator:{label:'Жинақтаушы',color:'#bcf078', description:'Бірнеше төлеушіден ақша шоғырландырады'},
  transit:{label:'Транзит',color:'#88c4df',description:'Кіріс пен шығыс көлемі жақын'},
  distributor:{label:'Таратушы',color:'#b5a3e4',description:'Көптеген алушыға қаражат жібереді'},
  terminal:{label:'Соңғы алушы үміткері',color:'#e3ba79',description:'Бақыланған кіріс шығыстан жоғары'},
  coordinator:{label:'Үйлестіруші үміткері',color:'#77deb1',description:'Желі топтарын байланыстыратын түйін'},
  peripheral:{label:'Шеткері',color:'#738a79',description:'Негізгі рөл белгілері жеткіліксіз'},
  boundary:{label:'Бақылау шекарасы',color:'#d4b279',description:'Төртінші қадамда бақылау үзіледі'},
  boundary_censored:{label:'Бақылау шекарасы',color:'#d4b279',description:'Төртінші қадамда бақылау үзіледі'},
};
const roleInfo = (r) => ROLES[r] || {label:r || 'Анықталмаған',color:'#94a885',description:''};
const roleBadge = (r) => `<span class="role-badge" style="color:${roleInfo(r).color}">${escapeHTML(roleInfo(r).label)}</span>`;
const FLAGS = {boundary_censored:'4-қадам: шығыс толық бақыланбайды',seed_inflow_incomplete:'Бастапқы шоттың кірісі толық емес',outflow_exceeds_observed_inflow:'Шығыс бақыланған кірістен жоғары',isolated:'Үзіндіде байланысы жоқ шот',no_observed_outflow:'Үзіндіде шығыс аударым көрінбейді'};
const localizeReason = (reason) => String(reason || '').split(',').map(part=>{const key=part.trim();if(key.startsWith('role='))return 'Рөл гипотезасы: '+roleInfo(key.slice(5)).label;return FLAGS[key] || (/^[a-z_]+$/.test(key)?'Қосымша тексеру қажет':key);}).join(' · ');

const state = {data:null,nodes:new Map(),adj:new Map(),view:'graph',selected:null,depth:4,cluster:'all',role:'all',focus:null,rankingPage:0,rankingFilter:'',rankingRole:'all',clusterLimit:18,requestLimit:25,uploadFiles:{},busy:false};
Object.assign(state,{graphMode:'overview',edgeMode:'all',highlight:null,replayDay:-1,replayMode:'day',replayDays:[],replayDaily:new Map(),replayEdges:[],replayTimer:null,insightTab:'events',insightKind:'all',insightSearch:'',insightLimit:24,storyStep:-1,storyGid:null,assistantBusy:false});
Object.assign(state,{labTab:'review',casebook:null,reviewEvidence:[],labelsPending:null,expansion:null,expansionLimit:25,expansionFilter:'',exploreResponse:null,explorePayload:null,assistantStatus:null,datasetRevision:0});
const FEATURE_LABELS={betweenness:'Жоларалық орталықтық',observed_volume:'Бақыланған айналым',fan_in:'Кіріс контрагенттері',fan_out:'Шығыс контрагенттері',pagerank:'Кіріс ағынындағы орын',community_bridging:'Топтар арасындағы байланыс',temporal_association:'Күндік уақыт сәйкестігі'};
const EVENT_KINDS={activity_spike:'Белсенділік секірісі',synchronized_payers:'Бір күндегі төлеушілер',fast_forward:'Жылдам өткізу белгісі',payment_splitting:'Соманы бөлшектеу белгісі',peer_outlier:'Өз қадамындағы ерекшелік',organizer_candidate:'Үйлестіруші үміткері'};
const graph = {canvas:$('#network-canvas'),ctx:null,width:0,height:0,nodes:[],edges:[],positions:new Map(),zoom:1,panX:0,panY:0,hover:null,drag:null,lastFrame:0};
graph.ctx = graph.canvas.getContext('2d');

function toast(message, error=false) {
  const el = $('#toast'); el.textContent=message; el.classList.remove('hidden');
  el.style.borderColor=error?'#9b6557':''; el.style.background=error?'#3b2b23':'';
  clearTimeout(toast.timer); toast.timer=setTimeout(()=>el.classList.add('hidden'),error?6500:3500);
}

async function api(path, options={}) {
  const response=await fetch(path,{...options,headers:{'Content-Type':'application/json',...(options.headers||{})}});
  let result; try { result=await response.json(); } catch { throw new Error('Сервер жарамды жауап қайтармады. Терминалдағы сервер күйін тексеріңіз.'); }
  if(!response.ok || result.error) throw new Error(result.error || result.message || `Сұрау қатесі: ${response.status}`);
  return result;
}

function setData(data) {
  if(!data || !Array.isArray(data.nodes) || !Array.isArray(data.edges)) throw new Error('Талдау нәтижесінің құрылымы жарамсыз.');
  state.data=data;state.datasetRevision++;state.casebook=null;state.expansion=null;state.labelsPending=null;state.exploreResponse=null;state.explorePayload=null; state.nodes=new Map(data.nodes.map(n=>[gidKey(n.gid),n]));
  state.adj=new Map(data.nodes.map(n=>[gidKey(n.gid),new Set()]));
  data.edges.forEach(e=>{state.adj.get(gidKey(e.src))?.add(gidKey(e.dst));state.adj.get(gidKey(e.dst))?.add(gidKey(e.src));});
  const first=(data.top_nodes||[]).find(n=>state.nodes.has(gidKey(n.gid)))||data.nodes[0];
  state.selected=first?gidKey(first.gid):null;state.depth=4;state.cluster='all';state.role='all';state.focus=null;state.rankingPage=0;state.clusterLimit=18;state.requestLimit=25;state.rankingFilter='';state.rankingRole='all';
  stopReplay();state.graphMode='overview';state.edgeMode='all';state.highlight=null;state.replayDay=-1;state.replayMode='day';state.storyStep=-1;state.insightLimit=24;state.insightSearch='';state.insightKind='all';state.insightTab='events';
  $('#graph-mode').value='overview';$('#edge-mode').value='all';$('#replay-mode').value='day';$('#insight-search').value='';$('#story-panel').classList.add('hidden');$('#assistant-messages').innerHTML='';
  $('#ranking-search').value='';$('#node-search').value='';
  $('#canvas-loading').classList.add('hidden');
  prepareReplay();renderOverview();renderFilterOptions();renderDetail();renderRanking();renderClusters();renderBlindspots();renderTimeline();renderInsights();renderAssistantSuggestions();buildGraph(true);resetLabForDataset();
}

function renderOverview() {
  const {meta,quality}=state.data;
  $('#metric-nodes').textContent=count(meta.n_nodes);$('#sidebar-node-count').textContent=count(meta.n_nodes)+' шот';
  $('#metric-seeds').textContent=count(meta.n_seeds)+' бастапқы шот';$('#metric-flow').textContent=shortMoney(meta.total_kzt);
  $('#metric-transactions').textContent=count(meta.n_transactions)+' транзакция · '+count(meta.n_edges)+' байланыс';
  $('#metric-clusters').textContent=count(meta.n_clusters);$('#metric-boundary').textContent=count(quality?.boundary_nodes)+' шот бақылау шекарасында';
  $('#dataset-period').textContent=niceDate(meta.period_start)+' — '+niceDate(meta.period_end);
  $('#demo-pill').innerHTML=`<span class="status-dot"></span>${meta.demo?'СИНТЕТИКАЛЫҚ ДЕМО':'ЖҮКТЕЛГЕН ДЕРЕКТЕР'}`;
  $('#dataset-status').textContent=meta.demo?'ДЕМО ЗЕРТТЕУ':'ЖЕРГІЛІКТІ ЗЕРТТЕУ';
}

function renderFilterOptions() {
  const roles=[...new Set(state.data.nodes.map(n=>n.role))];
  const options='<option value="all">Барлық рөл</option>'+roles.map(r=>`<option value="${escapeHTML(r)}">${escapeHTML(roleInfo(r).label)}</option>`).join('');
  $('#graph-role').innerHTML=options;$('#ranking-role').innerHTML=options;
  $('#graph-cluster').innerHTML='<option value="all">Барлық қауымдастық</option>'+state.data.clusters.map(c=>`<option value="${escapeHTML(c.cluster_id)}">Топ ${escapeHTML(c.cluster_id)} · ${count(c.n_nodes)} шот</option>`).join('');
  $$('[data-depth]').forEach(b=>b.classList.toggle('active',Number(b.dataset.depth)===state.depth));
}

function renderDetail() {
  const n=state.nodes.get(state.selected);if(!n){$('#node-detail').innerHTML='<div class="empty-detail"><h3>Шот табылмады</h3><p>Деректе шоттар жоқ.</p></div>';return;}
  const temporal=n.temporal||{};const flags=n.flags||[];const r=roleInfo(n.role);
  $('#node-detail').innerHTML=`
    <div class="detail-heading"><span>ШОТ ПРОФИЛІ · ТОЛЫҚ КЕЗЕҢ</span><span class="small-pill">${n.is_seed?'БАСТАПҚЫ ШОТ':escapeHTML(n.depth)+'-ҚАДАМ'}</span></div>
    <div class="detail-top"><div class="account-title"><div class="account-avatar" style="color:${r.color}">${icon('nodes')}</div><div><h3>#${escapeHTML(n.gid)}</h3><p>Қауымдастық ${escapeHTML(n.cluster_id)} · ${count(n.in_degree+n.out_degree)} байланыс</p></div></div>
    <div class="detail-role-row">${roleBadge(n.role)}<span>Гипотеза</span></div>
    <div class="priority-box"><div class="priority-top"><span>Тексеру басымдығы</span><strong class="priority-number">${percent(n.priority_score)}<small> / 100</small></strong></div><div class="score-track"><span style="width:${percent(n.priority_score)}%"></span></div><p>Эвристикалық ұпай · ықтималдық емес</p></div></div>
    <div class="detail-evidence"><div class="detail-section-label">${icon('shield')}НЕЛІКТЕН ОСЫ ШОТ?</div><p class="evidence-text">${escapeHTML(n.evidence)}</p></div>
    <div class="detail-stats"><div class="detail-stat"><span>Кіріс · ${count(n.in_degree)} төлеуші</span><strong title="${fullMoney(n.in_kzt)}">${shortMoney(n.in_kzt)}</strong>${n.in_tx==null?'':`<span class="detail-tx">${count(n.in_tx)} аударым</span>`}</div><div class="detail-stat"><span>Шығыс · ${count(n.out_degree)} алушы</span><strong title="${fullMoney(n.out_kzt)}">${shortMoney(n.out_kzt)}</strong>${n.out_tx==null?'':`<span class="detail-tx">${count(n.out_tx)} аударым</span>`}</div><div class="detail-stat"><span>Бақыланған шығыс / кіріс</span><strong>${n.pass_through==null?'— <small>толық емес</small>':decimal.format(n.pass_through)}</strong></div><div class="detail-stat"><span>Рөл белгісінің күші</span><strong>${percent(n.role_score)}<small> / 100</small></strong></div><div class="detail-stat"><span>Белсенді күндер</span><strong>${count(temporal.active_days)}</strong></div><div class="detail-stat"><span>Бір күндегі төлеушілер</span><strong>${count(temporal.synchronized_payers)}</strong></div></div>
    ${flags.length?`<div class="detail-flags">${flags.slice(0,3).map(f=>`<div class="detail-flag">${icon('warning')}<span>${escapeHTML(FLAGS[f]||f)}</span></div>`).join('')}</div>`:''}
    ${renderReplayNode(n)}
    <details class="detail-advanced"><summary>Метрикалар мен келесі қадам ${icon('plus')}</summary><div class="detail-advanced-body"><div class="advanced-metric"><span>Betweenness · жоларалық орын</span><strong>${num(n.betweenness).toFixed(5)}</strong></div><div class="advanced-metric"><span>PageRank · кіріс ағынындағы орын</span><strong>${num(n.pagerank).toFixed(5)}</strong></div><div class="advanced-metric"><span>0–1 күндегі көлем сәйкестігі</span><strong>${temporal.fast_forward_ratio==null?'Анықталмайды':percent(temporal.fast_forward_ratio)+'%'}</strong></div><p class="detail-caveat">Күндік сәйкестік бір қаражаттың әрі қарай өткенін дәлелдемейді.</p><h4>Басымдыққа қосылған ұпай</h4><div class="contributions">${Object.entries(n.priority_contributions||{}).map(([key,value])=>`<div><span>${escapeHTML(FEATURE_LABELS[key]||key)}</span><strong>${decimal.format(num(value)*100)}</strong><i style="width:${Math.min(100,num(value)*400)}%"></i></div>`).join('')||'<p>Үлестер бұл талдауда берілмеген.</p>'}</div><h4>Келесі дерек сұрауы</h4><p class="next-request">${escapeHTML(n.next_request||'Қосымша сұрау ұсынылмаған.')}</p><div class="node-extra-actions"><a class="button button-quiet button-small" href="/api/report.pdf?gid=${encodeURIComponent(gidKey(n.gid))}" download>${icon('download')}Шот PDF</a><button class="button button-quiet button-small" id="node-ask">${icon('spark')}Түсіндіру</button></div></div></details>
    <div class="detail-actions"><button class="button button-primary" id="node-simulate">Осы шотсыз желі ${icon('arrow-right')}</button><button class="text-button" id="node-focus">${icon('route')}Екі қадамдық маңайын ашу</button></div>`;
  $('#node-simulate').onclick=()=>openSimulation();$('#node-focus').onclick=()=>focusNode(state.selected);$('#node-ask').onclick=()=>{showView('assistant');askAssistant('Неге бұл шот таңдалды?');};$('.node-extra-actions').insertAdjacentHTML('beforeend',`<button class="button button-quiet button-small" id="node-review">${icon('shield')}Тексеру</button>`);$('#node-review').onclick=()=>{showView('lab');showLabTab('review');populateReview(state.selected);};updateAssistantContext();
}

function showView(view, updateHash=true) {
  if(!['graph','ranking','clusters','blindspots','insights','assistant','lab'].includes(view))view='graph';state.view=view;if(view!=='graph')stopReplay();
  $$('.view').forEach(el=>el.classList.toggle('active',el.id===view+'-view'));$$('[data-view]').forEach(el=>el.classList.toggle('active',el.dataset.view===view));
  const names={graph:['Ақша ізін <span>ашыңыз.</span>','Жекелеген аударымдардан — қаржы құрылымының тұтас көрінісіне.','Ақша графы'],ranking:['Дәлелге сүйенген <span>басымдық.</span>','Маңызды түйіндерді табыңыз. Әр ұпайдың артындағы белгілерді тексеріңіз.','Тексеру кезегі'],clusters:['Бір желі. <span>Бірнеше құрылым.</span>','Ақша ағындарын біріктіретін қауымдастықтарды зерттеңіз.','Қауымдастықтар'],blindspots:['Көрінбейтінді <span>ескеріңіз.</span>','Дерек шекараларын анықтаңыз және келесі сұрауды негіздеңіз.','Бақылау шегі']};
  names.insights=['Қайталанатын із. <span>Маңызды белгі.</span>','Циклдерді, бағыттарды және уақыттық ауытқуларды нақты аударымдардан табыңыз.','Паттерндер'];names.assistant=['Сұрақ қойыңыз. <span>Дәлелін ашыңыз.</span>','Ережелер немесе жергілікті тіл моделі талдау нәтижесін шоттарға сілтемелермен түсіндіреді.','Дерек көмекшісі'];
  names.lab=['Тексеріңіз. <span>Дәлелін сақтаңыз.</span>','Аналитик қорытындысы, қосымша деректер және жорамал сценарийлерге арналған кеңістік.','Тексеру зертханасы'];
  $('#page-title').innerHTML=names[view][0];$('#page-subtitle').textContent=names[view][1];$('#breadcrumb-current').textContent=names[view][2];
  if(updateHash)history.replaceState(null,'','#'+view);
  if(view==='graph')requestAnimationFrame(resizeGraph);
  if(view==='lab'&&state.data)showLabTab(state.labTab);if(view==='assistant')loadAssistantStatus();
}

function selectNode(gid, focus=false) {
  const key=gidKey(gid);if(!state.nodes.has(key)){toast('Бұл ID деректерде табылмады.',true);return false;}
  state.selected=key;state.depth=4;state.cluster='all';state.role='all';state.focus=focus?key:null;state.highlight=null;
  $('#graph-cluster').value='all';$('#graph-role').value='all';$$('[data-depth]').forEach(b=>b.classList.toggle('active',Number(b.dataset.depth)===4));
  showView('graph');renderDetail();buildGraph(true);return true;
}
function focusNode(gid) { selectNode(gid,true);toast('Екі байланыс қашықтығындағы маңай ашылды. Бағыттар жебемен көрсетіледі.'); }

function renderRanking() {
  if(!state.data)return;
  const ranks=new Map((state.data.top_nodes||[]).map(r=>[gidKey(r.gid),r]));
  let nodes=[...state.data.nodes].sort((a,b)=>num(b.priority_score)-num(a.priority_score)||gidKey(a.gid).localeCompare(gidKey(b.gid),undefined,{numeric:true}));
  nodes=nodes.map((n,i)=>({...n,displayRank:i+1,why:ranks.get(gidKey(n.gid))?.why||n.evidence})).filter(n=>(state.rankingRole==='all'||n.role===state.rankingRole)&&gidKey(n.gid).toLowerCase().includes(state.rankingFilter));
  const pageSize=20;const pageCount=Math.max(1,Math.ceil(nodes.length/pageSize));state.rankingPage=Math.min(state.rankingPage,pageCount-1);
  const rows=nodes.slice(state.rankingPage*pageSize,(state.rankingPage+1)*pageSize);
  $('#ranking-body').innerHTML=rows.length?rows.map(n=>`<tr data-gid="${escapeHTML(n.gid)}" tabindex="0" aria-label="${escapeHTML(n.gid)} шотын графта ашу"><td>${String(n.displayRank).padStart(2,'0')}</td><td><div class="table-account">#${escapeHTML(n.gid)}</div><div class="table-depth">${n.is_seed?'Бастапқы шот':escapeHTML(n.depth)+'-қадам'} · Топ ${escapeHTML(n.cluster_id)}</div></td><td>${roleBadge(n.role)}</td><td><div class="table-priority"><span>${percent(n.priority_score)}</span><div class="mini-score"><span style="width:${percent(n.priority_score)}%"></span></div></div></td><td class="table-evidence">${escapeHTML(n.why)}</td><td class="row-arrow">${icon('arrow-up-right')}</td></tr>`).join(''):'<tr><td colspan="6"><div class="no-results">Сүзгіге сәйкес шот табылмады.</div></td></tr>';
  $('#ranking-total').textContent=count(nodes.length)+' шот';$('#ranking-page-label').textContent=nodes.length?`${state.rankingPage*pageSize+1}–${Math.min((state.rankingPage+1)*pageSize,nodes.length)} / ${count(nodes.length)} шот`:'0 шот';
  $('#ranking-prev').disabled=state.rankingPage===0;$('#ranking-next').disabled=state.rankingPage>=pageCount-1;
  $$('#ranking-body tr[data-gid]').forEach(row=>{row.onclick=()=>{selectNode(row.dataset.gid,true);window.scrollTo({top:0,behavior:'smooth'});};row.onkeydown=e=>{if(e.key==='Enter')row.click();};});
}

function renderClusters() {
  if(!state.data)return;
  const all=[...state.data.clusters].sort((a,b)=>num(b.sum_kzt_internal)-num(a.sum_kzt_internal));
  const roleGroups=new Map();state.data.nodes.forEach(n=>{const id=String(n.cluster_id);if(!roleGroups.has(id))roleGroups.set(id,{});const counts=roleGroups.get(id);counts[n.role]=(counts[n.role]||0)+1;});
  $('#clusters-grid').innerHTML=all.slice(0,state.clusterLimit).map(c=>{
    const roles=roleGroups.get(String(c.cluster_id))||{};
    return `<article class="cluster-card"><div class="cluster-card-head"><div class="cluster-symbol">${icon('layers')}</div><h3>Қауымдастық ${escapeHTML(c.cluster_id)}</h3><span>${count(c.n_nodes)} шот</span></div><div class="cluster-flow" title="${fullMoney(c.sum_kzt_internal)}">${shortMoney(c.sum_kzt_internal)}</div><div class="cluster-flow-label">Топ ішіндегі бақыланған ағын</div><div class="cluster-stats"><span><strong>${count(c.n_seed)}</strong> бастапқы шот</span><span><strong>${Object.keys(roles).length}</strong> рөл түрі</span></div><div class="cluster-distribution" aria-label="Рөлдердің үлестірімі">${Object.entries(roles).map(([r,n])=>`<span style="width:${n/Math.max(1,c.n_nodes)*100}%;background:${roleInfo(r).color}" title="${escapeHTML(roleInfo(r).label)}: ${n}"></span>`).join('')}</div><p class="cluster-hypothesis">${escapeHTML(c.hypothesis)}</p><button class="text-button" data-cluster-open="${escapeHTML(c.cluster_id)}">Құрылымды ашу ${icon('arrow-right')}</button></article>`;
  }).join('')||'<div class="no-results">Қауымдастықтар жоқ.</div>';
  $('#clusters-more').classList.toggle('hidden',state.clusterLimit>=all.length);
  $$('[data-cluster-open]').forEach(b=>b.onclick=()=>{state.cluster=b.dataset.clusterOpen;state.role='all';state.depth=4;state.focus=null;$('#graph-cluster').value=state.cluster;$('#graph-role').value='all';$$('[data-depth]').forEach(x=>x.classList.toggle('active',Number(x.dataset.depth)===4));const c=state.data.clusters.find(c=>String(c.cluster_id)===state.cluster);if(c?.top_gids?.length)state.selected=gidKey(c.top_gids[0]);showView('graph');renderDetail();buildGraph(true);window.scrollTo({top:0,behavior:'smooth'});});
}

function renderBlindspots() {
  if(!state.data)return;const q=state.data.quality||{};
  const cards=[[q.boundary_nodes,'4-қадамдағы шот','Үзінді осы қадаммен шектелген.'],[q.isolated_seeds,'Байланысы жоқ seed','Үзіндіде оқшау, бірақ есептен шығарылмайды.'],[q.outflow_exceeds_inflow,'Шығыс кірістен жоғары','Бастапқы қалдық пен сыртқы кіріс белгісіз.'],[q.seeds_without_outgoing,'Шығыссыз бастапқы шот','Шекті сомалар мен кезеңді тексеру қажет.']];
  $('#quality-grid').innerHTML=cards.map(([v,label,description])=>`<div class="quality-card"><strong>${count(v)}</strong><span>${label}</span><p>${description}</p></div>`).join('');
  const reqs=q.requests||[];$('#request-count').textContent=count(reqs.length)+' сұрау';
  $('#request-list').innerHTML=reqs.slice(0,state.requestLimit).map((r,i)=>`<div class="request-row"><span class="request-number">${String(i+1).padStart(2,'0')}</span><div class="request-body"><strong>#${escapeHTML(r.gid)}</strong><span class="request-reason">${escapeHTML(localizeReason(r.reason))}</span><p>${escapeHTML(r.request)}</p></div><button class="text-button" data-request-gid="${escapeHTML(r.gid)}">Шотты ашу ${icon('arrow-up-right')}</button></div>`).join('')||'<div class="no-results">Қосымша сұраулар ұсынылмаған.</div>';
  $('#requests-more').classList.toggle('hidden',state.requestLimit>=reqs.length);
  $('#quality-warnings').innerHTML=(state.data.meta.warnings||[]).map(w=>`<p>${escapeHTML(w)}</p>`).join('');
  $$('[data-request-gid]').forEach(b=>b.onclick=()=>{selectNode(b.dataset.requestGid,true);window.scrollTo({top:0,behavior:'smooth'});});
}

function renderTimeline() {
  const timeline=state.data.timeline||[];const max=Math.max(1,...timeline.map(t=>num(t.sum_kzt)));
  $('#timeline').innerHTML=timeline.map(t=>`<button class="timeline-bar" data-replay-date="${escapeHTML(t.date)}" style="height:${Math.max(2,num(t.sum_kzt)/max*100)}%" aria-label="${niceDate(t.date)} күнін графта ашу" title="${niceDate(t.date)} · ${fullMoney(t.sum_kzt)} · ${count(t.n_tx)} транзакция"></button>`).join('');
  $$('[data-replay-date]').forEach(b=>b.onclick=()=>{const i=state.replayDays.indexOf(b.dataset.replayDate);if(i>=0)setReplayDay(i);});
  $('#timeline-start').textContent=niceDate(timeline[0]?.date);$('#timeline-end').textContent=niceDate(timeline[timeline.length-1]?.date);
}

function buildGraph(reset=false) {
  if(!state.data)return;
  let candidates=state.data.nodes.filter(n=>num(n.depth)<=state.depth&&(state.cluster==='all'||String(n.cluster_id)===state.cluster)&&(state.role==='all'||n.role===state.role));
  const eligible=new Set(candidates.map(n=>gidKey(n.gid)));let chosen=new Set();
  const limit=state.graphMode==='all'?Infinity:state.focus?170:130;
  const add=k=>{if(eligible.has(k)&&chosen.size<limit)chosen.add(k);};
  (state.highlight?.gids||[]).map(gidKey).forEach(add);
  if(state.focus){
    const visited=new Set([state.focus]);let frontier=[state.focus];add(state.focus);
    for(let depth=0;depth<2;depth++){const next=[];for(const id of frontier){const neighbors=[...(state.adj.get(id)||[])].sort((a,b)=>num(state.nodes.get(b)?.priority_score)-num(state.nodes.get(a)?.priority_score));for(const k of neighbors){if(!visited.has(k)){visited.add(k);next.push(k);add(k);}}}frontier=next;}
    candidates=candidates.filter(n=>visited.has(gidKey(n.gid)));
  }else if(candidates.length<=limit){candidates.forEach(n=>add(gidKey(n.gid)));}
  else{
    if(state.selected&&eligible.has(state.selected)){add(state.selected);[...(state.adj.get(state.selected)||[])].slice(0,30).forEach(add);}
    const sorted=[...candidates].sort((a,b)=>num(b.priority_score)-num(a.priority_score));
    for(const n of sorted.slice(0,15)){add(gidKey(n.gid));[...(state.adj.get(gidKey(n.gid))||[])].filter(k=>eligible.has(k)).sort((a,b)=>num(state.nodes.get(b)?.priority_score)-num(state.nodes.get(a)?.priority_score)).slice(0,5).forEach(add);}
    for(let d=0;d<=state.depth;d++)candidates.filter(n=>num(n.depth)===d).slice(0,9).forEach(n=>add(gidKey(n.gid)));
    for(const n of sorted)add(gidKey(n.gid));
  }
  graph.nodes=candidates.filter(n=>chosen.has(gidKey(n.gid)));
  const sourceEdges=state.replayDay>=0?state.replayEdges:state.data.edges;
  graph.edges=sourceEdges.filter(e=>chosen.has(gidKey(e.src))&&chosen.has(gidKey(e.dst)));
  $('#graph-count').textContent=count(graph.nodes.length)+' / '+count(candidates.length);
  $('#graph-scope').textContent=(state.focus?`Маңай: ${count(graph.nodes.length)} / ${count(candidates.length)} шот · 2 байланыс қашықтығы`:`${state.graphMode==='all'?'Толық граф':'Шолу'}: ${count(graph.nodes.length)} / ${count(candidates.length)} шот`)+` · ${count(graph.edges.length)} байланыс ${state.replayDay>=0?'таңдалған уақыт аралығында':''}`;
  $('#density-note').textContent=state.graphMode==='all'?'Барлық шот көрсетіледі. Үлкейтіп, ID арқылы таңдаңыз.':'ID іздеуі барлық шотты ашады';renderHighlight();
  $('#focus-reset').classList.toggle('hidden',!state.focus);
  if(reset){graph.zoom=1;graph.panX=0;graph.panY=0;$('#zoom-value').textContent='100%';}
  resizeGraph();
}

function resizeGraph() {
  const wrap=$('#canvas-wrap');const rect=wrap.getBoundingClientRect();if(!rect.width||!rect.height)return;
  graph.width=rect.width;graph.height=rect.height;const dpr=Math.min(window.devicePixelRatio||1,2);
  graph.canvas.width=Math.round(rect.width*dpr);graph.canvas.height=Math.round(rect.height*dpr);graph.ctx.setTransform(dpr,0,0,dpr,0,0);layoutGraph();drawGraph(performance.now());
}

function hash(s) {let h=2166136261;for(let i=0;i<s.length;i++){h^=s.charCodeAt(i);h=Math.imul(h,16777619);}return h>>>0;}

function layoutGraph() {
  const columns=new Map();for(let i=0;i<=4;i++)columns.set(i,[]);
  graph.nodes.forEach(n=>columns.get(Math.max(0,Math.min(4,num(n.depth))))?.push(n));
  for(const group of columns.values())group.sort((a,b)=>num(a.cluster_id)-num(b.cluster_id)||hash(gidKey(a.gid))-hash(gidKey(b.gid)));
  const marginX=graph.width<400?28:40,usableW=graph.width-2*marginX,marginY=53,usableH=graph.height-105;
  const maxDepth=Math.max(1,state.depth);graph.positions=new Map();
  const assign=()=>{for(const [d,nodes] of columns){nodes.forEach((n,i)=>{const key=gidKey(n.gid),jitter=((hash(key)%101)/100-.5)*Math.min(usableW/maxDepth*(graph.nodes.length>400?.7:.26),graph.nodes.length>400?60:20);const deg=num(n.in_degree)+num(n.out_degree);const radius=graph.nodes.length>400?Math.min(4,1.1+Math.log2(deg+1)*.35):Math.min(11,3.1+Math.log2(deg+1)*.8);graph.positions.set(key,{x:marginX+(d/maxDepth)*usableW+jitter,y:marginY+(i+.5)/Math.max(1,nodes.length)*usableH,r:radius,n});});}};
  assign();
  // Barycenter ordering reduces edge crossings without inventing relationships.
  for(let iteration=0;iteration<3;iteration++){
    for(let d=1;d<=maxDepth;d++){
      const group=columns.get(d);group.sort((a,b)=>{
        const center=n=>{const ys=[...(state.adj.get(gidKey(n.gid))||[])].map(k=>graph.positions.get(k)).filter(p=>p&&num(p.n.depth)<d).map(p=>p.y);return ys.length?ys.reduce((sum,y)=>sum+y,0)/ys.length:graph.positions.get(gidKey(n.gid))?.y||0;};
        return center(a)-center(b);
      });assign();
    }
  }
}

function edgeCurve(a,b) {
  if(a===b||a.n.gid===b.n.gid)return null;
  const dx=b.x-a.x;const dy=b.y-a.y;
  if(Math.abs(dx)<35){const bend=35+Math.min(45,Math.abs(dy)*.2);return {ax:a.x,ay:a.y,bx:b.x,by:b.y,c1x:a.x+bend,c1y:a.y+dy*.25,c2x:b.x+bend,c2y:b.y-dy*.25};}
  return {ax:a.x,ay:a.y,bx:b.x,by:b.y,c1x:a.x+dx*.47,c1y:a.y,c2x:b.x-dx*.47,c2y:b.y};
}
function curvePoint(c,t){const mt=1-t;return {x:mt*mt*mt*c.ax+3*mt*mt*t*c.c1x+3*mt*t*t*c.c2x+t*t*t*c.bx,y:mt*mt*mt*c.ay+3*mt*mt*t*c.c1y+3*mt*t*t*c.c2y+t*t*t*c.by};}

function drawGraph(time=0) {
  if(!graph.width||state.view!=='graph')return;const ctx=graph.ctx,w=graph.width,h=graph.height;
  ctx.clearRect(0,0,w,h);ctx.save();ctx.translate(w/2+graph.panX,h/2+graph.panY);ctx.scale(graph.zoom,graph.zoom);ctx.translate(-w/2,-h/2);
  const marginX=w<400?28:40,maxDepth=Math.max(1,state.depth),usableW=w-marginX*2;
  for(let d=0;d<=maxDepth;d++){
    const x=marginX+d/maxDepth*usableW;
    ctx.strokeStyle=d===4?'#77704b25':'#6575571d';ctx.lineWidth=1;ctx.setLineDash([3,7]);ctx.beginPath();ctx.moveTo(x,42);ctx.lineTo(x,h-43);ctx.stroke();ctx.setLineDash([]);
    ctx.font='10px Segoe UI, sans-serif';ctx.textAlign='center';ctx.fillStyle=d===4?'#b2a575':'#8da27e';ctx.fillText(d===0?'БАСТАПҚЫ':d+'-ҚАДАМ',x,24);
    if(d===4){ctx.font='9px Segoe UI, sans-serif';ctx.fillStyle='#a29566';ctx.fillText('БАҚЫЛАУ ШЕГІ',x,37);}
  }
  const active=graph.hover||state.selected;const connected=state.adj.get(active)||new Set();
  let animated=0;
  for(const e of graph.edges){
    const ak=gidKey(e.src),bk=gidKey(e.dst),a=graph.positions.get(ak),b=graph.positions.get(bk);if(!a||!b)continue;
    const c=edgeCurve(a,b);if(!c)continue;const selected=ak===active||bk===active;const highlighted=state.highlight?.edgeKeys?.has(ak+'→'+bk);
    if(state.edgeMode==='selected'&&!selected&&!highlighted)continue;
    ctx.beginPath();ctx.moveTo(c.ax,c.ay);ctx.bezierCurveTo(c.c1x,c.c1y,c.c2x,c.c2y,c.bx,c.by);
    ctx.strokeStyle=highlighted?'#f0c67bcf':selected?'#aaca6faa':graph.nodes.length>400?'#68805418':'#6880542f';ctx.lineWidth=highlighted?2.6:selected?1.7:.65+Math.min(.8,Math.log10(Math.max(1,num(e.sum_kzt)))*.075);ctx.stroke();
    const point=curvePoint(c,.80),previous=curvePoint(c,.78),angle=Math.atan2(point.y-previous.y,point.x-previous.x);const arrow=selected?3.9:2.8;
    if(selected||highlighted||graph.nodes.length<400){ctx.beginPath();ctx.moveTo(point.x,point.y);ctx.lineTo(point.x-arrow*Math.cos(angle-.52),point.y-arrow*Math.sin(angle-.52));ctx.lineTo(point.x-arrow*Math.cos(angle+.52),point.y-arrow*Math.sin(angle+.52));ctx.closePath();ctx.fillStyle=highlighted?'#ffe0a5':selected?'#b1d87ea0':'#81996165';ctx.fill();}
    if(selected&&animated<14&&!window.matchMedia('(prefers-reduced-motion: reduce)').matches){const p=curvePoint(c,((time*.0001)+(hash(ak+bk)%100)/100)%1);ctx.beginPath();ctx.arc(p.x,p.y,1.25,0,Math.PI*2);ctx.fillStyle='#d6fda5';ctx.fill();animated++;}
  }
  for(const [key,p] of graph.positions){
    const selected=key===state.selected,hovered=key===graph.hover,highlighted=state.highlight?.gids?.some(id=>gidKey(id)===key),relevant=key===active||connected.has(key)||highlighted,n=p.n;
    const color=n.is_seed?'#d1dfae':roleInfo(n.role).color;const boundary=num(n.depth)===4;
    if(selected||hovered||highlighted){ctx.beginPath();ctx.arc(p.x,p.y,p.r+11,0,Math.PI*2);ctx.fillStyle=highlighted?'#edc37a18':'#abd47810';ctx.fill();ctx.beginPath();ctx.arc(p.x,p.y,p.r+7,0,Math.PI*2);ctx.strokeStyle=highlighted?'#eac178b0':'#c0ee8570';ctx.lineWidth=1;ctx.stroke();}
    if(n.is_seed){ctx.beginPath();ctx.arc(p.x,p.y,p.r+3,0,Math.PI*2);ctx.strokeStyle='#b5c99c50';ctx.lineWidth=.7;ctx.stroke();}
    ctx.globalAlpha=active&&!relevant?.58:1;ctx.beginPath();ctx.arc(p.x,p.y,selected?p.r+1:p.r,0,Math.PI*2);
    ctx.fillStyle=boundary?'#273024':color;ctx.fill();ctx.strokeStyle=boundary?'#c4a967':selected?'#e7ffb8':'#c6e5a520';ctx.lineWidth=boundary?1.3:selected?1.8:1;ctx.stroke();
    if(!boundary){ctx.beginPath();ctx.arc(p.x-1,p.y-1,Math.max(1,p.r*.28),0,Math.PI*2);ctx.fillStyle='#efffe450';ctx.fill();}
    ctx.globalAlpha=1;
    if(selected||hovered||highlighted||(graph.zoom>1.4&&relevant)){
      const label='#'+key;ctx.font=(selected?'600 ':'')+'11px Segoe UI, sans-serif';ctx.textAlign='center';const width=ctx.measureText(label).width+10;ctx.fillStyle='#182418ee';ctx.fillRect(p.x-width/2,p.y+p.r+5,width,17);ctx.fillStyle=selected?'#d5f4ae':'#adbd97';ctx.fillText(label,p.x,p.y+p.r+17);
    }
  }
  if(!graph.nodes.length){ctx.textAlign='center';ctx.font='12px Segoe UI, sans-serif';ctx.fillStyle='#819575';ctx.fillText('Осы сүзгіде шоттар жоқ',w/2,h/2);}
  ctx.restore();
}

function graphPoint(e) {const r=graph.canvas.getBoundingClientRect();return {x:(e.clientX-r.left-graph.width/2-graph.panX)/graph.zoom+graph.width/2,y:(e.clientY-r.top-graph.height/2-graph.panY)/graph.zoom+graph.height/2,screenX:e.clientX-r.left,screenY:e.clientY-r.top};}
function hitNode(p) {let best=null,dist=Infinity;for(const [key,n] of graph.positions){const d=Math.hypot(p.x-n.x,p.y-n.y);if(d<Math.max(n.r+5,9/graph.zoom)&&d<dist){best=key;dist=d;}}return best;}
function zoomGraph(mult,point=null){const old=graph.zoom;graph.zoom=Math.min(3.5,Math.max(.45,old*mult));if(point){const ratio=graph.zoom/old;graph.panX=point.screenX-graph.width/2-(point.screenX-graph.width/2-graph.panX)*ratio;graph.panY=point.screenY-graph.height/2-(point.screenY-graph.height/2-graph.panY)*ratio;}$('#zoom-value').textContent=Math.round(graph.zoom*100)+'%';drawGraph(performance.now());}
graph.canvas.addEventListener('pointerdown',e=>{graph.drag={x:e.clientX,y:e.clientY,panX:graph.panX,panY:graph.panY,moved:false};graph.canvas.setPointerCapture(e.pointerId);$('#graph-tooltip').classList.add('hidden');});
graph.canvas.addEventListener('pointermove',e=>{
  const p=graphPoint(e);
  if(graph.drag){const dx=e.clientX-graph.drag.x,dy=e.clientY-graph.drag.y;if(Math.abs(dx)+Math.abs(dy)>4)graph.drag.moved=true;graph.panX=graph.drag.panX+dx;graph.panY=graph.drag.panY+dy;drawGraph(performance.now());return;}
  const key=hitNode(p);graph.hover=key;graph.canvas.style.cursor=key?'pointer':'grab';const tip=$('#graph-tooltip');
  if(key){const n=state.nodes.get(key);tip.innerHTML=`<strong>#${escapeHTML(key)}</strong><span>${escapeHTML(roleInfo(n.role).label)} · ${percent(n.priority_score)}/100</span>`;tip.classList.remove('hidden');tip.style.left=Math.min(p.screenX+13,graph.width-170)+'px';tip.style.top=Math.min(p.screenY+12,graph.height-60)+'px';}else tip.classList.add('hidden');drawGraph(performance.now());
});
graph.canvas.addEventListener('pointerup',e=>{if(graph.drag&&!graph.drag.moved){const key=hitNode(graphPoint(e));if(key){state.selected=key;renderDetail();}}graph.drag=null;drawGraph(performance.now());});
graph.canvas.addEventListener('pointercancel',()=>{graph.drag=null;});
graph.canvas.addEventListener('pointerleave',()=>{graph.hover=null;$('#graph-tooltip').classList.add('hidden');drawGraph(performance.now());});
graph.canvas.addEventListener('wheel',e=>{e.preventDefault();zoomGraph(e.deltaY<0?1.09:1/1.09,graphPoint(e));},{passive:false});
new ResizeObserver(()=>resizeGraph()).observe($('#canvas-wrap'));
function animate(t){if(t-graph.lastFrame>(graph.nodes.length>400?250:55)){drawGraph(t);graph.lastFrame=t;}requestAnimationFrame(animate);}requestAnimationFrame(animate);

function modal(header,body,footer='') {
  $('#modal-content').innerHTML=`<div class="modal-header">${header}<button class="modal-close" id="modal-close" aria-label="Терезені жабу">${icon('close')}</button></div><div class="modal-body">${body}</div>${footer?'<div class="modal-footer">'+footer+'</div>':''}`;
  $('#modal-close').onclick=()=>$('#modal').close();if(!$('#modal').open)$('#modal').showModal();
}
$('#modal').addEventListener('click',e=>{if(e.target===$('#modal')){const r=$('#modal').getBoundingClientRect();if(e.clientX<r.left||e.clientX>r.right||e.clientY<r.top||e.clientY>r.bottom)$('#modal').close();}});

function openMethod() {
  modal('<div><div class="modal-eyebrow">TRANSPARENT BY DESIGN</div><h2>Дәлелден — гипотезаға</h2><p>Жергілікті, түсіндірілетін ережелер. Қара жәшіксіз талдау.</p></div>',`
    <div class="method-section"><h3>01 / Граф және бақыланған ағын</h3><p>Түйін — иесіздендірілген шот. Жебе — төлеушіден алушыға аударым. Тереңдік — бастапқы шоттан ең аз қадам саны. Кіріс пен шығыс сомалары шоттың нақты қалдығын білдірмейді.</p></div>
    <div class="method-section"><h3>02 / Рөлдер қалай түсіндіріледі?</h3><p>Ережелер кіріс/шығыс байланыстарын, ағын қатынасын және желідегі орынды біріктіреді. Рөл ұпайы — ережелер белгілерінің күші; калибрленген ықтималдық емес.</p><div class="method-role-list">${Object.entries(ROLES).filter(([r])=>!r.startsWith('boundary')).map(([r,v])=>`<div><strong style="color:${v.color}">${v.label}</strong>${v.description}</div>`).join('')}</div></div>
    <div class="method-section"><h3>03 / Көрінбейтін дерек ескеріледі</h3><p>4-қадамда бақылау үзіледі. Сондықтан шығыстың болмауы соңғы алушы деген қорытындыға жеткіліксіз. Бастапқы шоттардың кірісі толық емес. 5 000 ₸ шегі, тек банкішілік аударымдар және уақыт аралығы көріністі шектейді.</p></div>
    <div class="method-section"><h3>04 / Басымдық пен қауымдастықтар</h3><p>Басымдық ұпайы тексеру кезегін құруға көмектеседі. Қауымдастық — транзакциялық байланыстар тобы. Екеуі де кінәліліктің немесе ұйымдасқан топтың дәлелі емес. Шолу графында ең маңызды шоттар мен көршілері көрсетіледі; барлық шот ID іздеу және рейтинг арқылы қолжетімді.</p></div>
    <div class="method-section"><h3>05 / «Осы шотсыз желі» сценарийі</h3><p>Симуляция түйін мен байланыстарды математикалық графтан алып тастайды. Нәтиже қолжетімділік пен байланыс құрылымының өзгерісін көрсетеді. Бұл нақты бұғаттау немесе қаржылық шығын болжамы емес.</p></div>`);
}

function openExports() {
  modal('<div><div class="modal-eyebrow">READY FOR REVIEW</div><h2>Талдау нәтижесін жүктеу</h2><p>Ағымдағы деректер бойынша толық есеп. CSV файлдары UTF-8 форматында.</p></div>',`<div class="export-grid">${[['nodes_roles.csv','Барлық шот пен рөл','Ұпайлар, қауымдастық және негіздеме'],['top_nodes.csv','Басымдық рейтингі','Алдымен тексерілетін түйіндер'],['clusters.csv','Қауымдастықтар','Топ өлшемі, ағын, негізгі шоттар'],['analysis.json','Толық талдау · JSON','Граф, метрикалар және дерек шектері']].map(([file,title,description])=>`<a class="export-card" href="/api/download/${file}" download="${file}">${icon('download')}<strong>${title}</strong><span>${description}</span><span>${file}</span></a>`).join('')}</div>`);
  $('#modal .export-grid').insertAdjacentHTML('beforeend',`<a class="export-card" href="/api/report.pdf" download>${icon('file')}<strong>Зерттеу есебі · PDF</strong><span>Негізгі шоттар, паттерндер, шектеулер</span></a>${state.selected?`<a class="export-card" href="/api/report.pdf?gid=${encodeURIComponent(state.selected)}" download>${icon('file')}<strong>Шот анықтамасы · PDF</strong><span>#${escapeHTML(state.selected)} · дәлелдер мен келесі сұрау</span></a>`:''}`);
}

function openUpload() {
  state.uploadFiles={};
  modal('<div><div class="modal-eyebrow">YOUR DATA. LOCAL ANALYSIS.</div><h2>Зерттеуді деректен бастаңыз</h2><p>Талдау үшін үш Parquet файлын бірге таңдаңыз.</p></div>',`<label class="upload-drop" id="upload-drop" for="upload-input">${icon('upload')}<strong>Файлдарды осында тастаңыз</strong><span>немесе файлдарды таңдау үшін басыңыз</span><input type="file" id="upload-input" accept=".parquet" multiple hidden></label><div class="upload-file-list" id="upload-file-list"></div><p class="upload-note">Деректер осы компьютерде өңделеді. Әр жүктеу ағымдағы талдау нәтижесін жаңартады.</p><button class="text-button" id="upload-demo">Синтетикалық демоны іске қосу ${icon('arrow-right')}</button><div class="inline-error hidden" id="upload-error"></div>`,`<span>3 файл · .parquet</span><button class="button button-quiet" id="upload-cancel">Бас тарту</button><button class="button button-primary" id="upload-submit" disabled>Талдауды бастау ${icon('arrow-right')}</button>`);
  renderUploadFiles();$('#upload-input').onchange=e=>acceptFiles(e.target.files);$('#upload-cancel').onclick=()=>$('#modal').close();$('#upload-submit').onclick=submitUpload;$('#upload-demo').onclick=()=>{$('#modal').close();$('#reset-demo').click();};
  const drop=$('#upload-drop');drop.addEventListener('dragover',e=>{e.preventDefault();drop.classList.add('dragover');});drop.addEventListener('dragleave',()=>drop.classList.remove('dragover'));drop.addEventListener('drop',e=>{e.preventDefault();drop.classList.remove('dragover');acceptFiles(e.dataTransfer.files);});
}
function acceptFiles(files) {
  const required=['nodes.parquet','edges.parquet','transactions.parquet'];let rejected=[];
  for(const file of files){const name=file.name.toLowerCase();if(required.includes(name))state.uploadFiles[name]=file;else rejected.push(file.name);}
  renderUploadFiles();if(rejected.length){$('#upload-error').textContent='Күтілетін файлдар: nodes.parquet, edges.parquet, transactions.parquet. Қабылданбады: '+rejected.join(', ');$('#upload-error').classList.remove('hidden');}else $('#upload-error').classList.add('hidden');
}
function renderUploadFiles() {
  const required=['nodes.parquet','edges.parquet','transactions.parquet'];
  $('#upload-file-list').innerHTML=required.map(name=>`<div class="upload-file-row ${state.uploadFiles[name]?'ready':''}">${icon(state.uploadFiles[name]?'check':'file')}<strong>${name}</strong><span>${state.uploadFiles[name]?decimal.format(state.uploadFiles[name].size/1024)+' КБ':'Күтілуде'}</span></div>`).join('');
  $('#upload-submit').disabled=!required.every(name=>state.uploadFiles[name]);
}
function fileBase64(file) {return new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(String(reader.result).split(',')[1]);reader.onerror=()=>reject(new Error('Файл оқылмады: '+file.name));reader.readAsDataURL(file);});}
async function submitUpload() {
  if(state.busy)return;const submit=$('#upload-submit');submit.disabled=true;submit.textContent='Талдау жүріп жатыр…';state.busy=true;$('#upload-error').classList.add('hidden');
  try{const files={};for(const [name,file] of Object.entries(state.uploadFiles))files[name]=await fileBase64(file);const data=await api('/api/analyze',{method:'POST',body:JSON.stringify({files})});setData(data);$('#modal').close();showView('graph');toast('Деректер талданды. '+count(data.meta.n_nodes)+' шот зерттеуге дайын.');}
  catch(error){if($('#upload-error')){$('#upload-error').textContent=error.message;$('#upload-error').classList.remove('hidden');}else toast(error.message,true);}
  finally{state.busy=false;if($('#upload-submit')){$('#upload-submit').disabled=false;$('#upload-submit').innerHTML='Талдауды бастау '+icon('arrow-right');}}
}

async function openSimulation(initialMode='selected') {
  const n=state.nodes.get(state.selected);if(!n){toast('Алдымен шотты таңдаңыз.');return;}
  modal('<div><div class="modal-eyebrow">WHAT IF / ҚҰРЫЛЫМДЫҚ СЦЕНАРИЙ</div><h2>Негізгі шоттарсыз желі</h2><p>Бір шоттың немесе басымдықтағы топ-N түйіннің құрылымға ықпалы.</p></div>',`<div class="simulation-notice">${icon('warning')}<span>Тек математикалық граф өзгереді. Бұл нақты бұғаттау немесе қаржылық шығын болжамы емес. Ұпайлар толық кезең бойынша есептелген.</span></div><label class="simulation-selector">Графтан алып тастау<select id="simulation-mode"><option value="selected">Таңдалған #${escapeHTML(n.gid)}</option>${[1,3,5,10,20].map(v=>`<option value="${v}">Басымдықтағы топ-${v}</option>`).join('')}</select></label><div id="simulation-results"></div>`);
  $('#simulation-mode').value=typeof initialMode==='string'?initialMode:'selected';$('#simulation-mode').onchange=runSimulation;await runSimulation();
  async function runSimulation(){const selector=$('#simulation-mode');if(!selector)return;const mode=selector.value;selector.disabled=true;$('#simulation-results').innerHTML='<div class="no-results"><span class="loading-orbit" style="display:block;margin:0 auto 13px"></span>Құрылым қайта есептелуде…</div>';
  try{const result=await api('/api/simulate',{method:'POST',body:JSON.stringify(mode==='selected'?{gids:[n.gid],curve:true}:{top_n:Number(mode),curve:true})});if(!$('#simulation-results'))return;
    const b=result.before,a=result.after;
    const curve=result.curve||[];const maxLost=Math.max(1,...curve.map(p=>num(p.lost_reachable)));const plot=curve.map((p,i)=>`${18+i/Math.max(1,curve.length-1)*460},${105-num(p.lost_reachable)/maxLost*85}`).join(' ');
    $('#simulation-results').innerHTML=`<div class="simulation-account"><strong>${mode==='selected'?'#'+escapeHTML(n.gid):'Топ-'+escapeHTML(mode)}</strong><span>${count(result.actual_n??result.removed?.length)} түйін алынды</span></div><div class="simulation-removed">${(result.removed||[]).map(gid=>'<span>#'+escapeHTML(gid)+'</span>').join('')}</div><div class="simulation-grid"><div class="simulation-stat"><span>Қолжетімділігі жоғалған шот</span><strong>${count(result.lost_reachable)}</strong><p>Өзі алынбаған, бірақ бастапқы шоттардан жетпейтін болды</p></div><div class="simulation-stat"><span>Алынған байланыстар ағыны</span><strong>${shortMoney(result.observed_flow_removed_kzt)}</strong><p>Бақыланған сома · шығын болжамы емес</p></div></div><table class="simulation-comparison"><thead><tr><th>ЖЕЛІ КӨРСЕТКІШІ</th><th>БҰРЫН</th><th>КЕЙІН</th></tr></thead><tbody>${[['n_nodes','Шоттар'],['n_edges','Байланыстар'],['components','Байланыс компоненттері'],['largest_component','Ең ірі компонент'],['reachable_from_seeds','Бастапқы шоттардан жететін түйіндер']].map(([k,label])=>`<tr><td>${label}</td><td>${count(b[k])}</td><td>${count(a[k])}</td></tr>`).join('')}</tbody></table>${curve.length?`<div class="removal-curve"><h3>Түйіндерді біртіндеп алып тастау</h3><p>Жоғалған қолжетімділік: әр қадамдағы нақты қайта есептеу</p><svg viewBox="0 0 500 125" role="img" aria-label="Түйіндерді алу саны артқандағы жоғалған қолжетімділік"><path d="M18 20V105H478" fill="none" stroke="#455f35"/><polyline points="${plot}" fill="none" stroke="#bcec83" stroke-width="2.5"/>${curve.map((p,i)=>`<circle cx="${18+i/Math.max(1,curve.length-1)*460}" cy="${105-num(p.lost_reachable)/maxLost*85}" r="3" fill="#d0f6a3"><title>${p.n} түйін алынды: ${count(p.lost_reachable)} шот қолжетімсіз</title></circle>`).join('')}<text x="18" y="121">0 түйін</text><text x="440" y="121">${curve.at(-1).n} түйін</text></svg><details><summary>Әр қадамның сандарын ашу</summary><table class="simulation-comparison"><thead><tr><th>АЛЫНДЫ</th><th>ҚОЛЖЕТІМСІЗ БОЛДЫ</th><th>КОМПОНЕНТТЕР</th></tr></thead><tbody>${curve.map(p=>`<tr><td>${p.n}</td><td>${count(p.lost_reachable)}</td><td>${count(p.after?.components??p.components)}</td></tr>`).join('')}</tbody></table></details></div>`:''}<p class="simulation-result-note">${escapeHTML(result.note)}</p>`;
  }catch(error){if($('#simulation-results'))$('#simulation-results').innerHTML=`<div class="inline-error">${escapeHTML(error.message)}</div>`;}finally{if($('#simulation-mode'))$('#simulation-mode').disabled=false;}}
}

$$('[data-view]').forEach(button=>button.onclick=()=>showView(button.dataset.view));
window.addEventListener('hashchange',()=>showView(location.hash.slice(1)||'graph',false));
$('#method-button').onclick=openMethod;$('#help-button').onclick=openMethod;$('#limitations-link').onclick=openMethod;
$('#export-button').onclick=openExports;$('#upload-button').onclick=openUpload;$('#upload-side').onclick=openUpload;
$$('[data-download]').forEach(b=>b.onclick=()=>{const a=document.createElement('a');a.href='/api/download/'+b.dataset.download;a.download=b.dataset.download;a.click();});
$('#simulation-shortcut').onclick=openSimulation;
$('#node-search').addEventListener('keydown',e=>{if(e.key==='Enter'){const val=e.target.value.trim().replace(/^#/, '');if(!val)return;if(selectNode(val,true))toast('#'+val+' шоты және оның байланыстары ашылды.');}});
$('#graph-cluster').onchange=e=>{state.cluster=e.target.value;state.focus=null;buildGraph(true);};
$('#graph-role').onchange=e=>{state.role=e.target.value;state.focus=null;buildGraph(true);};
$$('[data-depth]').forEach(b=>b.onclick=()=>{state.depth=Number(b.dataset.depth);$$('[data-depth]').forEach(x=>x.classList.toggle('active',x===b));buildGraph(true);});
$('#focus-reset').onclick=()=>{state.focus=null;buildGraph(true);};
$('#graph-fit').onclick=()=>{graph.zoom=1;graph.panX=0;graph.panY=0;$('#zoom-value').textContent='100%';drawGraph(performance.now());};
$('#zoom-in').onclick=()=>zoomGraph(1.2);$('#zoom-out').onclick=()=>zoomGraph(1/1.2);
$('#ranking-search').oninput=e=>{state.rankingFilter=e.target.value.trim().toLowerCase().replace(/^#/,'');state.rankingPage=0;renderRanking();};
$('#ranking-role').onchange=e=>{state.rankingRole=e.target.value;state.rankingPage=0;renderRanking();};
$('#ranking-prev').onclick=()=>{state.rankingPage=Math.max(0,state.rankingPage-1);renderRanking();};
$('#ranking-next').onclick=()=>{state.rankingPage++;renderRanking();};
$('#clusters-more').onclick=()=>{state.clusterLimit+=18;renderClusters();};$('#requests-more').onclick=()=>{state.requestLimit+=25;renderBlindspots();};
$('#reset-demo').onclick=async()=>{
  if(state.busy)return;state.busy=true;const b=$('#reset-demo');b.disabled=true;b.innerHTML=icon('refresh')+'Дайындалуда…';
  try{const data=await api('/api/demo',{method:'POST',body:'{}'});setData(data);showView('graph');toast('Синтетикалық демо жаңартылды.');}catch(error){toast(error.message,true);}finally{state.busy=false;b.disabled=false;b.innerHTML=icon('refresh')+'Демоны жаңарту';}
};

function prepareReplay() {
  const replay=state.data.replay||{};state.replayDays=Array.isArray(replay.days)?replay.days.map(String):[];state.replayDaily=new Map(state.replayDays.map(d=>[d,[]]));state.replayEdges=[];
  for(const edge of replay.edges||[]){for(const day of edge.days||[]){if(!state.replayDaily.has(day.date))state.replayDaily.set(day.date,[]);state.replayDaily.get(day.date).push({src:edge.src,dst:edge.dst,sum_kzt:num(day.sum_kzt),n_tx:num(day.n_tx)});}}
  const slider=$('#replay-slider');slider.max=Math.max(0,state.replayDays.length-1);slider.value=0;slider.disabled=!state.replayDays.length;$('#replay-play').disabled=!state.replayDays.length;$('#replay-mode').disabled=!state.replayDays.length;renderReplayHeader();
}
function stopReplay() {if(state.replayTimer){clearInterval(state.replayTimer);state.replayTimer=null;}const button=$('#replay-play');if(button){button.textContent='▶';button.setAttribute('aria-label','Уақытты ойнату');button.title='Уақытты ойнату';}}
function setReplayDay(index) {
  if(!state.replayDays.length)return;state.replayDay=Math.max(0,Math.min(state.replayDays.length-1,Number(index)));$('#replay-slider').value=state.replayDay;
  const last=state.replayDays[state.replayDay];const dates=state.replayMode==='day'?[last]:state.replayDays.slice(0,state.replayDay+1);const edges=new Map();
  for(const date of dates){for(const e of state.replayDaily.get(date)||[]){const k=gidKey(e.src)+'→'+gidKey(e.dst);if(!edges.has(k))edges.set(k,{...e});else{edges.get(k).sum_kzt+=e.sum_kzt;edges.get(k).n_tx+=e.n_tx;}}}
  state.replayEdges=[...edges.values()];renderReplayHeader();buildGraph(false);renderDetail();
}
function renderReplayHeader() {
  const active=state.replayDay>=0;const date=state.replayDays[state.replayDay];$('#replay-date').textContent=active?(state.replayMode==='cumulative'?'Дейін: ':'')+niceDate(date):'Толық кезең';
  const edges=active?state.replayEdges:state.data?.edges||[];$('#replay-volume').textContent=shortMoney(edges.reduce((s,e)=>s+num(e.sum_kzt),0))+' · '+count(edges.reduce((s,e)=>s+num(e.n_tx),0))+' аударым';
  $('#replay-note').textContent=state.replayDays.length?'Жебелердің сомасы мен саны таңдалған күндерден есептеледі. Рөлдер мен ұпайлар толық кезең бойынша қалады.':'Күндік қайта ойнату бұл талдауда жоқ. Деректерді қайта талдау қажет.';
  $$('[data-replay-date]').forEach(b=>b.classList.toggle('replay-active',active&&(state.replayMode==='day'?b.dataset.replayDate===date:b.dataset.replayDate<=date)));
}
function renderReplayNode(n) {
  if(state.replayDay<0)return '';let incoming=0,outgoing=0,inTx=0,outTx=0;const key=gidKey(n.gid);
  for(const e of state.replayEdges){if(gidKey(e.dst)===key){incoming+=num(e.sum_kzt);inTx+=num(e.n_tx);}if(gidKey(e.src)===key){outgoing+=num(e.sum_kzt);outTx+=num(e.n_tx);}}
  return `<div class="node-replay"><h4>${state.replayMode==='day'?'Таңдалған күн':'Осы күнге дейін'} · ${niceDate(state.replayDays[state.replayDay])}</h4><div><span>Кіріс<strong>${shortMoney(incoming)}</strong>${count(inTx)} аударым</span><span>Шығыс<strong>${shortMoney(outgoing)}</strong>${count(outTx)} аударым</span></div><p>Жоғарыдағы профиль және рөл ұпайлары толық кезеңге қатысты.</p></div>`;
}
function renderHighlight() {
  const box=$('#pattern-highlight');box.classList.toggle('hidden',!state.highlight);if(!state.highlight)return;
  const h=state.highlight;box.innerHTML=`<div>${icon('route')}<span><strong>${escapeHTML(h.title||'Таңдалған паттерн')}</strong><small>${h.group==='events'?'Қатысушы шоттар: ':''}${h.gids.map(id=>'#'+escapeHTML(id)).join(h.group==='events'?' · ':' → ')} · ${h.group==='events'?'шоттар сары шеңбермен белгіленген':'сары жебелер — таңдалған байланыстар'}</small></span></div><button class="icon-button" id="highlight-close" aria-label="Паттерн белгілеуін алып тастау">${icon('close')}</button>`;$('#highlight-close').onclick=()=>{state.highlight=null;renderHighlight();drawGraph(performance.now());};
}
function openInsight(item, group) {
  const gids=(item.gids||[]).filter(id=>state.nodes.has(gidKey(id)));if(!gids.length){toast('Бұл паттерннің шоттары ағымдағы талдауда жоқ.',true);return;}
  stopReplay();state.replayDay=-1;renderReplayHeader();state.selected=gidKey(gids[0]);state.depth=4;state.cluster='all';state.role='all';state.focus=null;state.graphMode='overview';
  state.highlight={...item,gids,edgeKeys:new Set((item.edges||[]).map(e=>gidKey(e.src)+'→'+gidKey(e.dst))),group};
  $('#graph-mode').value='overview';$('#graph-cluster').value='all';$('#graph-role').value='all';$$('[data-depth]').forEach(x=>x.classList.toggle('active',Number(x.dataset.depth)===4));
  showView('graph');renderDetail();buildGraph(true);window.scrollTo({top:0,behavior:'smooth'});
}
function renderInsights() {
  if(!state.data)return;const ins=state.data.insights||{},summary=ins.summary||{};const events=ins.events||[],cycles=ins.cycles||[],routes=ins.routes||[];
  $('#insight-summary').innerHTML=[[events.length,'Тексерілетін оқиға','pulse'],[cycles.length,'Көрсетілген цикл','refresh'],[routes.length,'Қайталанған бағыт','route']].map(([n,title,name])=>`<div><span>${icon(name)}${title}</span><strong>${count(n)}</strong></div>`).join('');
  $('#insight-kind').innerHTML='<option value="all">Барлық белгі</option>'+Object.entries(EVENT_KINDS).map(([key,label])=>`<option value="${key}">${label}${summary.events_by_kind?.[key]!=null?' · '+count(summary.events_by_kind[key]):''}</option>`).join('');$('#insight-kind').value=state.insightKind;$('#insight-kind').disabled=state.insightTab!=='events';
  $$('[data-insight-tab]').forEach(b=>b.classList.toggle('active',b.dataset.insightTab===state.insightTab));
  const all=ins[state.insightTab]||[];const filtered=all.filter(item=>(state.insightTab!=='events'||state.insightKind==='all'||item.kind===state.insightKind)&&(!state.insightSearch||(item.gids||[]).some(gid=>gidKey(gid).includes(state.insightSearch))));
  const labels={events:'оқиға',cycles:'цикл',routes:'бағыт'};const limits=ins.limits||{};const truncated=Object.entries(limits).some(([key,val])=>key.toLowerCase().includes('truncat')&&val===true);
  const detected=limits[state.insightTab+'_detected'];const searchCapped=limits[state.insightTab==='cycles'?'cycle_search_truncated':'route_search_truncated'];
  $('#insight-limits').innerHTML=`<span>Сүзгі: ${count(filtered.length)} ${labels[state.insightTab]} · ${Math.min(state.insightLimit,filtered.length)} көрсетілді${detected!=null?' · Іздеу кезінде '+count(detected)+' табылды; '+count(all.length)+' сақталды':''}</span><span>${truncated?'Есептеу шегіне жеткен тізімдер бар. ':''}${searchCapped&&state.insightTab!=='events'?'Іздеу кандидаттар шегінде тоқтады. ':''}${state.insightTab==='events'?'Ережелік сигналдар; расталған бұзушылық емес.':'Қысқа маршруттарды шектеулі іздеу. Толық тізім деп қабылдамаңыз.'}</span>`;
  $('#insight-list').innerHTML=filtered.slice(0,state.insightLimit).map(item=>{
    const index=all.indexOf(item),isEvent=state.insightTab==='events';const dates=item.observed_dates||[];const occurrences=item.occurrences||[];
    return `<article class="pattern-card"><div class="pattern-card-header"><span class="pattern-kind">${escapeHTML(isEvent?EVENT_KINDS[item.kind]||'Ережелік белгі':state.insightTab==='cycles'?'Бағытталған цикл':'Қайталанған бағыт')}</span><span class="pattern-date">${item.date?niceDate(item.date):dates.length?count(dates.length)+' бақыланған күн':''}</span></div><h3>${escapeHTML(item.title||'Тексерілетін паттерн')}</h3><p>${escapeHTML(item.evidence||'Негіздеме берілмеген.')}</p><div class="pattern-accounts">${(item.gids||[]).map(gid=>`<button data-pattern-node="${escapeHTML(gid)}">#${escapeHTML(gid)}</button>`).join(isEvent?'<span>·</span>':'<span>→</span>')}</div>${item.sum_kzt!=null?`<div class="pattern-metric">Байланыстардағы бақыланған сома <strong>${shortMoney(item.sum_kzt)}</strong></div>`:''}${item.n_occurrences!=null?`<div class="pattern-metric">Уақыттық сәйкестік <strong>${item.n_occurrences_is_lower_bound?"кемінде ":""}${count(item.n_occurrences)} рет</strong></div>`:''}${occurrences.length?`<details class="pattern-dates"><summary>Кездескен күндерді ашу</summary>${occurrences.slice(0,8).map(o=>`<p>${(o.dates||[o.start_date,o.end_date]).filter(Boolean).map(niceDate).join(' → ')}</p>`).join('')}${occurrences.length>8||item.occurrences_truncated?'<p>Көрсетілген күндер — сақталған сәйкестіктердің бір бөлігі.</p>':''}</details>`:''}${item.same_day_order_unknown?'<div class="pattern-caveat">Бір күн ішіндегі операциялар реті белгісіз.</div>':''}<button class="text-button" data-open-pattern="${index}" data-pattern-group="${state.insightTab}">${isEvent?'Шоттарды графта ашу':'Бағытты графта белгілеу'} ${icon('arrow-right')}</button></article>`;
  }).join('')||'<div class="no-results">Осы сүзгіде паттерн табылмады. Бұл күмәнді әрекет жоқ деген қорытынды емес.</div>';
  $('#insights-more').classList.toggle('hidden',state.insightLimit>=filtered.length);
  $('#insight-method').innerHTML=`${icon('shield')}<p>Цикл — ақша жіберушіге қайтатын бағыттың құрылымдық белгісі. Қайталанған күндік бағыт сол ақшаның қозғалғанын дәлелдемейді. Оқиғалар, циклдер және бағыттар сан мен іздеу тереңдігі бойынша шектеледі; сақталмаған нәтижелер болуы мүмкін. Нақты ережелер мен шектер толық JSON есебінің insights бөлімінде беріледі.</p>`;
  $$('[data-open-pattern]').forEach(b=>b.onclick=()=>openInsight((ins[b.dataset.patternGroup]||[])[Number(b.dataset.openPattern)],b.dataset.patternGroup));
  $$('[data-pattern-node]').forEach(b=>b.onclick=()=>{selectNode(b.dataset.patternNode,true);window.scrollTo({top:0,behavior:'smooth'});});
}
function updateAssistantContext() {if($('#assistant-context-label'))$('#assistant-context-label').textContent=state.selected?'#'+state.selected+' шотын ескеру':'Таңдалған шотты ескеру';}
function renderAssistantSuggestions(suggestions=['Кімді бірінші тексеру керек?','Қай шоттар ақша жинайды?','Қандай дерек жетіспейді?','Циклдерді көрсет']) {
  $('#assistant-suggestions').innerHTML=suggestions.slice(0,6).map(q=>`<button class="assistant-suggestion">${escapeHTML(q)}</button>`).join('');$$('.assistant-suggestion').forEach(b=>b.onclick=()=>askAssistant(b.textContent));updateAssistantContext();
}
async function askAssistant(question) {
  const text=String(question||'').trim();if(!text||state.assistantBusy)return;state.assistantBusy=true;const datasetRevision=state.datasetRevision;const requestedMode=$('#assistant-mode')?.value||'local_rules';$('#assistant-submit').disabled=true;$('#assistant-submit').textContent='Жауап дайындалуда…';
  const container=$('#assistant-messages'),context=$('#assistant-use-context').checked&&state.selected;container.insertAdjacentHTML('beforeend',`<div class="assistant-question"><span>Сіздің сұрағыңыз${context?' · #'+escapeHTML(state.selected):''}</span><p>${escapeHTML(text)}</p></div>`);$('#assistant-question').value='';
  const answer=document.createElement('div');answer.className='assistant-answer';answer.innerHTML='<span>Дерек көмекшісі</span><p>Талдау нәтижесінен жауап ізделуде…</p>';container.append(answer);answer.scrollIntoView({behavior:'smooth',block:'nearest'});
  try{const response=await api('/api/assistant',{method:'POST',body:JSON.stringify({question:text,mode:requestedMode,...(context?{gid:state.selected}:{})})});if(datasetRevision!==state.datasetRevision)return;answer.innerHTML=`<span>${icon('spark')}${escapeHTML(assistantModeText(response))}</span><p>${escapeHTML(response.answer)}</p><div class="assistant-citations">${(response.citations||[]).map(c=>`<button data-citation-gid="${escapeHTML(c.gid)}">${escapeHTML(c.label||'#'+c.gid)} ${icon('arrow-up-right')}</button>`).join('')}</div>`;answer.querySelectorAll('[data-citation-gid]').forEach(b=>b.onclick=()=>selectNode(b.dataset.citationGid,true));if(response.suggestions?.length)renderAssistantSuggestions(response.suggestions);if(response.note)answer.insertAdjacentHTML('beforeend',`<p class="assistant-response-note">${escapeHTML(response.note)}</p>`);}
  catch(error){answer.innerHTML=`<span>Сұрау орындалмады</span><p>${escapeHTML(error.message)}</p>`;answer.classList.add('assistant-error');}
  finally{state.assistantBusy=false;$('#assistant-submit').disabled=false;$('#assistant-submit').innerHTML='Сұрау '+icon('arrow-right');}
}
function startStory() {
  const top=state.data?.top_nodes?.[0];if(!top){toast('Алдымен деректі жүктеңіз.');return;}state.storyGid=gidKey(top.gid);state.storyStep=0;selectNode(state.storyGid,true);renderStory();
}
function renderStory() {
  const box=$('#story-panel');if(state.storyStep<0){box.classList.add('hidden');return;}box.classList.remove('hidden');const n=state.nodes.get(state.storyGid);if(!n)return;
  const ins=state.data.insights||{};const match=[...(ins.cycles||[]).map(i=>({...i,group:'cycles'})),...(ins.routes||[]).map(i=>({...i,group:'routes'})),...(ins.events||[]).map(i=>({...i,group:'events'}))].find(i=>(i.gids||[]).some(g=>gidKey(g)===state.storyGid));
  const steps=[['Үміткерді таңдаңыз',`#${n.gid} — басымдық ұпайы ${percent(n.priority_score)}/100. ${n.evidence}`],['Паттернді зерттеңіз',match?match.evidence:'Осы шотқа тіркелген қысқа цикл не қайталанған маршрут табылмады. Көршілерін және бағытталған байланыстарын зерттеңіз.'],['Белгіні дәлелмен салыстырыңыз',`${count(n.in_degree)} төлеуші, ${count(n.out_degree)} алушы. Кіріс: ${fullMoney(n.in_kzt)}; шығыс: ${fullMoney(n.out_kzt)}. Рөл — ${roleInfo(n.role).label}.`],['Келесі деректі сұраңыз',n.next_request||'Кезең мен бақылау шегін кеңейту қажеттілігін тексеріңіз.'],['Есепті сақтаңыз','Шоттың белгілері, ұпай үлестері және шектеулері бар PDF анықтаманы жүктеп, тексеруге тіркеңіз.']];const step=steps[state.storyStep];
  box.innerHTML=`<div class="story-progress">${steps.map((s,i)=>`<span class="${i<=state.storyStep?'done':''}"></span>`).join('')}</div><div class="story-content"><div><span class="story-step">${state.storyStep+1} / 5 · #${escapeHTML(n.gid)}</span><h3>${step[0]}</h3><p>${escapeHTML(step[1])}</p></div><button class="icon-button" id="story-close" aria-label="Зерттеу нұсқаулығын жабу">${icon('close')}</button></div><div class="story-actions">${state.storyStep>0?'<button class="text-button" id="story-back">← Алдыңғы</button>':'<span></span>'}${state.storyStep===1&&match?'<button class="button button-quiet button-small" id="story-pattern">Паттернді белгілеу</button>':''}${state.storyStep===4?`<a class="button button-primary button-small" href="/api/report.pdf?gid=${encodeURIComponent(state.storyGid)}" download>Шот PDF ${icon('download')}</a>`:'<button class="button button-primary button-small" id="story-next">Келесі →</button>'}</div>`;
  $('#story-close').onclick=()=>{state.storyStep=-1;renderStory();};if($('#story-back'))$('#story-back').onclick=()=>{state.storyStep--;renderStory();};if($('#story-next'))$('#story-next').onclick=()=>{state.storyStep++;renderStory();if(state.storyStep===2){state.selected=state.storyGid;renderDetail();$('#node-detail details')?.setAttribute('open','');}};if($('#story-pattern'))$('#story-pattern').onclick=()=>openInsight(match,match.group);
}

$('#graph-mode').onchange=e=>{state.graphMode=e.target.value;state.focus=null;if(state.graphMode==='all'){state.edgeMode='selected';$('#edge-mode').value='selected';}buildGraph(true);};
$('#edge-mode').onchange=e=>{state.edgeMode=e.target.value;drawGraph(performance.now());};
$('#replay-slider').oninput=e=>{stopReplay();setReplayDay(e.target.value);};
$('#replay-mode').onchange=e=>{state.replayMode=e.target.value;setReplayDay(state.replayDay<0?0:state.replayDay);};
$('#replay-reset').onclick=()=>{stopReplay();state.replayDay=-1;renderReplayHeader();buildGraph(false);renderDetail();};
$('#replay-play').onclick=()=>{if(state.replayTimer){stopReplay();return;}if(!state.replayDays.length)return;if(state.replayDay<0||state.replayDay>=state.replayDays.length-1)setReplayDay(0);$('#replay-play').textContent='Ⅱ';$('#replay-play').setAttribute('aria-label','Уақытты кідірту');$('#replay-play').title='Уақытты кідірту';state.replayTimer=setInterval(()=>{if(state.replayDay>=state.replayDays.length-1){stopReplay();return;}setReplayDay(state.replayDay+1);},1200);};
$$('[data-insight-tab]').forEach(b=>b.onclick=()=>{state.insightTab=b.dataset.insightTab;state.insightLimit=24;renderInsights();});
$('#insight-kind').onchange=e=>{state.insightKind=e.target.value;state.insightLimit=24;renderInsights();};
$('#insight-search').oninput=e=>{state.insightSearch=e.target.value.trim().replace(/^#/,'');state.insightLimit=24;renderInsights();};
$('#insights-more').onclick=()=>{state.insightLimit+=24;renderInsights();};
$('#insight-simulation').onclick=()=>openSimulation('5');
$('#assistant-form').onsubmit=e=>{e.preventDefault();askAssistant($('#assistant-question').value);};
$('#story-start').onclick=startStory;

const REVIEW_STATUS={unreviewed:'Әлі тексерілмеген',in_review:'Тексеру үстінде',supported:'Белгілер дерекпен расталды',rejected:'Гипотеза расталмады'};
const REVIEW_ROLES=['consolidator','transit','distributor','terminal','coordinator','peripheral'];
function reviewHypothesisNotice(review) {const current=state.nodes.get(gidKey(review.gid))?.role;return review.predicted_role_at_review&&current&&review.predicted_role_at_review!==current?`<p class="review-context-note">Сақталған шешім бұрынғы «${escapeHTML(roleInfo(review.predicted_role_at_review).label)}» гипотезасына қатысты. Қазіргі рөл: «${escapeHTML(roleInfo(current).label)}». Бағалау қазіргі рөлдермен салыстырылады.</p>`:'';}
function exactJSON(text) {return JSON.parse(text,(_key,value)=>{if(typeof value==='number'&&Number.isInteger(value)&&!Number.isSafeInteger(value))throw new Error('Үлкен бүтін сандарды, әсіресе шот ID мәндерін, JSON ішінде тырнақшаға алып жазыңыз.');return value;});}
function csvRows(text) {
  const source=String(text).replace(/^\uFEFF/,'');const first=source.split(/\r?\n/,1)[0];const separator=first.includes(';')&&!first.includes(',')?';':',';let rows=[],row=[],cell='',quoted=false;
  for(let i=0;i<source.length;i++){const c=source[i];if(c==='"'){if(quoted&&source[i+1]==='"'){cell+='"';i++;}else quoted=!quoted;}else if(c===separator&&!quoted){row.push(cell);cell='';}else if((c==='\n'||c==='\r')&&!quoted){if(c==='\r'&&source[i+1]==='\n')i++;row.push(cell);if(row.some(x=>x.trim()))rows.push(row);row=[];cell='';}else cell+=c;}
  if(quoted)throw new Error('CSV файлындағы тырнақша жабылмаған.');row.push(cell);if(row.some(x=>x.trim()))rows.push(row);if(rows.length<2)throw new Error('Файлда баған атаулары мен кемінде бір жол болуы керек.');const headers=rows.shift().map(h=>h.trim());if(new Set(headers).size!==headers.length)throw new Error('CSV баған атаулары қайталанбауы керек.');return rows.map((values,i)=>{if(values.length!==headers.length)throw new Error(`CSV ${i+2}-жолдағы баған саны сәйкес емес.`);return Object.fromEntries(headers.map((h,j)=>[h,values[j].trim()]));});
}
function normalizeLabelRows(rows,skipBlank=false) {
  const fields=['gid','verified_role','source_reference','reviewer'],annotations=fields.slice(1),seen=new Set(),labels=[];let skipped=0;
  for(let i=0;i<rows.length;i++){
    const row=rows[i];if(!row||typeof row!=='object'||Array.isArray(row)||Object.keys(row).length!==fields.length||!fields.every(key=>Object.hasOwn(row,key)))throw new Error(`${i+1}-жолда дәл осы бағандар болуы керек: ${fields.join(', ')}.`);
    const raw=gidKey(row.gid).trim();if(!/^-?\d{1,20}$/.test(raw))throw new Error(`${i+1}-жолдағы gid нақты бүтін ID болуы керек.`);const integerId=BigInt(raw);if(integerId<-(2n**63n)||integerId>=2n**63n)throw new Error(`${i+1}-жолдағы gid int64 шегінен тыс.`);const gid=integerId.toString();
    if(!state.nodes.has(gid))throw new Error(`${i+1}-жолдағы #${gid} ағымдағы деректерде жоқ.`);if(seen.has(gid))throw new Error(`${i+1}-жолда #${gid} шоты қайталанады.`);seen.add(gid);
    for(const key of annotations)if(typeof row[key]!=='string')throw new Error(`${i+1}-жолдағы ${key} мәтін болуы керек.`);
    const values=Object.fromEntries(annotations.map(key=>[key,row[key].trim()]));if(skipBlank&&annotations.every(key=>values[key]==='')){skipped++;continue;}
    for(const key of annotations)if(!values[key])throw new Error(`${i+1}-жолда ${key} бағаны толтырылмаған.`);if(!REVIEW_ROLES.includes(values.verified_role))throw new Error(`${i+1}-жолдағы verified_role сөздікке сәйкес емес.`);labels.push({gid,...values});
  }
  return {labels,skipped};
}
function datasetFingerprintGuard() {const fingerprint=state.data?.meta?.dataset_fingerprint;return fingerprint?{expected_dataset_fingerprint:fingerprint}:{};}
function labError(target,error) {const el=$(target);if(el)el.innerHTML=`<div class="inline-error">${escapeHTML(error.message||error)}</div>`;}
function showLabTab(tab) {
  state.labTab=['review','expansion','search','recovery'].includes(tab)?tab:'review';$$('[data-lab-tab]').forEach(b=>{const active=b.dataset.labTab===state.labTab;b.classList.toggle('active',active);b.setAttribute('aria-selected',String(active));});$$('.lab-panel').forEach(panel=>{const active=panel.id==='lab-'+state.labTab;panel.hidden=!active;panel.classList.toggle('active',active);});
  if(state.labTab==='review'&&!state.casebook)loadReviews();if(state.labTab==='expansion'&&!state.expansion)loadExpansion();if(state.labTab==='search'){if(!$('#explore-start').value)$('#explore-start').value=state.selected||'';updateExploreScope();}
}
function resetLabForDataset() {
  $('#review-evaluation').innerHTML='<p class="lab-note">Тексерулерді ашу үшін зертхана бөлімін таңдаңыз.</p>';$('#reviews-list').innerHTML='';$('#reviews-count').textContent='—';
  $('#review-gid').value=state.selected||'';$('#explore-start').value=state.selected||'';$('#explore-end').value='';$('#review-form').reset();$('#review-gid').value=state.selected||'';state.reviewEvidence=[];syncReviewRequirements();$('#labels-preview').innerHTML='';$('#labels-import').disabled=true;$('#labels-file').value='';$('#expansion-json').value='';$('#expansion-file').value='';$('#expansion-disjoint').checked=false;$('#expansion-preview').innerHTML='';$('#expansion-search').value='';state.expansionLimit=25;state.expansionFilter='';$('#explore-results').innerHTML='';$('#explore-summary').innerHTML='';$('#explore-more').classList.add('hidden');$('#recovery-results').innerHTML='<div class="no-results">Параметрлерді таңдап, үш құрылымның айырмасын салыстырыңыз.</div>';renderExpansion();if(state.view==='lab')showLabTab(state.labTab);
}
function syncReviewRequirements() {const status=$('#review-status').value,finalized=['supported','rejected'].includes(status);$('#review-reviewer').required=status!=='unreviewed';$('#review-source').required=finalized;$('#review-role').disabled=!finalized;if(!finalized)$('#review-role').value='';}
async function loadReviews() {
  const revision=state.datasetRevision;$('#review-evaluation').innerHTML='<p>Сақталған тексерулер жүктелуде…</p>';
  try{const result=await api('/api/reviews');if(revision!==state.datasetRevision)return;state.casebook=result;renderReviews();populateReview($('#review-gid').value||state.selected);}
  catch(error){labError('#review-evaluation',error);}
}
function populateReview(gid) {
  const key=gidKey(gid||'').trim();$('#review-gid').value=key;const review=state.casebook?.reviews?.find(r=>gidKey(r.gid)===key);state.reviewEvidence=review?.evidence?[...review.evidence]:[];
  $('#review-status').value=review?.status||'unreviewed';$('#review-reviewer').value=review?.reviewer||'';$('#review-source').value=review?.source_reference||'';$('#review-notes').value=review?.notes||'';syncReviewRequirements();$('#review-role').value=review?.verified_role||'';$('#review-evidence-source').value='';$('#review-evidence-summary').value='';
  $('#review-save-status').textContent=review?`Сақталған пікір ашылды. ${state.reviewEvidence.length} дәлел жазбасы сақталады.`:state.nodes.has(key)?'Осы шотқа жаңа тексеру жазбасын жасаңыз.':'ID ағымдағы бастапқы деректерде болуы керек.';
}
function renderReviews() {
  const book=state.casebook||{},evaluation=book.evaluation||{};const metric=(value)=>value==null?'—':decimal.format(num(value)*100)+'%';
  $('#review-evaluation').innerHTML=`<div class="evaluation-stats"><div><strong>${count(evaluation.evaluated_count)}</strong><span>Белгісі бар шот</span></div><div><strong>${metric(evaluation.coverage)}</strong><span>Деректі қамту</span></div><div><strong>${metric(evaluation.accuracy)}</strong><span>Дәл сәйкестік</span></div><div><strong>${metric(evaluation.macro_f1)}</strong><span>Macro F1</span></div></div><p class="lab-note">Тек аналитик берген тексерілген белгілер бойынша. Бұл үлгі бүкіл желінің сапасын кепілдемейді.</p>${num(evaluation.evaluated_count)?`<div class="table-scroll"><table class="lab-table"><thead><tr><th>Рөл</th><th>Precision</th><th>Recall</th><th>F1</th><th>Белгі</th></tr></thead><tbody>${Object.entries(evaluation.per_class||{}).map(([role,m])=>`<tr><td>${escapeHTML(roleInfo(role).label)}</td><td>${metric(m.precision)}</td><td>${metric(m.recall)}</td><td>${metric(m.f1)}</td><td>${count(m.support)}</td></tr>`).join('')}</tbody></table></div>`:'<p class="evaluation-empty">Сапаны бағалау үшін дереккөзі көрсетілген тәуелсіз рөл белгілерін енгізіңіз. Белгісіз мәндер нөлдік сапа деп есептелмейді.</p>'}${book.notice?`<p class="lab-note">Аналитик енгізген пікірлер мен рөл белгілері тәуелсіз тексеруден өткен факт немесе сот қорытындысы емес. Бағалау тек берілген белгілер жиынындағы сәйкестікті көрсетеді.</p>`:''}`;
  if(num(evaluation.evaluated_count)){
    const matrix=evaluation.confusion_matrix||{},baseline=evaluation.baseline||{};
    $('#review-evaluation').insertAdjacentHTML('beforeend',`<details class="review-matrix"><summary>Рөлдер сәйкестік матрицасы</summary><p>Жолдар — аналитик берген тексерілген рөл. Бағандар — жүйенің қазіргі рөл гипотезасы. Ұяшықтағы сан — шот саны.</p><div class="table-scroll"><table class="lab-table confusion-table"><thead><tr><th scope="col">Тексерілген ↓ / жүйе →</th>${REVIEW_ROLES.map(role=>`<th scope="col">${escapeHTML(roleInfo(role).label)}</th>`).join('')}</tr></thead><tbody>${REVIEW_ROLES.map(actual=>`<tr><th scope="row">${escapeHTML(roleInfo(actual).label)}</th>${REVIEW_ROLES.map(predicted=>`<td class="${actual===predicted?'matrix-match':''}">${count(matrix[actual]?.[predicted])}</td>`).join('')}</tr>`).join('')}</tbody></table></div>${baseline.role?`<p class="matrix-baseline">Салыстыру негізі: осы белгілер жиынындағы ең жиі рөлді («${escapeHTML(roleInfo(baseline.role).label)}») барлық шотқа болжау — ${metric(baseline.accuracy)} сәйкестік.</p>`:''}<p>Бұл салыстыру сол белгіленген жиынның өзінен алынған. Оның тәуелсіз сынақ жиыны екені расталмаған; нәтиже бүкіл желінің дәлдігі ретінде қолданылмайды.</p></details>`);
  }
  const reviews=book.reviews||[];$('#reviews-count').textContent=count(reviews.length)+' тексеру';$('#reviews-list').innerHTML=reviews.length?reviews.map(review=>`<article class="review-row"><div><button class="review-gid" data-review-open="${escapeHTML(review.gid)}">#${escapeHTML(review.gid)}</button><span class="review-status status-${escapeHTML(review.status)}">${escapeHTML(REVIEW_STATUS[review.status]||review.status)}</span>${review.verified_role?roleBadge(review.verified_role):''}</div><p>${escapeHTML(review.notes||'Ескерту енгізілмеген.')}</p>${reviewHypothesisNotice(review)}<small>${escapeHTML(review.reviewer||'Аналитик көрсетілмеген')} · ${escapeHTML(review.source_reference||'Дереккөз тіркелмеген')} · ${count(review.evidence?.length)} дәлел</small></article>`).join(''):'<div class="no-results">Бұл деректер жиынына сақталған тексерулер жоқ.</div>';
  $$('[data-review-open]').forEach(b=>b.onclick=()=>{populateReview(b.dataset.reviewOpen);$('#review-form').scrollIntoView({behavior:'smooth',block:'center'});});
}
async function saveReview(e) {
  e.preventDefault();const revision=state.datasetRevision;const button=$('#review-save');button.disabled=true;const evidence=[...state.reviewEvidence];const summary=$('#review-evidence-summary').value.trim();if(summary)evidence.push({kind:$('#review-evidence-kind').value,source_reference:$('#review-evidence-source').value.trim(),summary,related_gids:[]});
  const payload={gid:$('#review-gid').value.trim(),status:$('#review-status').value,reviewer:$('#review-reviewer').value.trim(),source_reference:$('#review-source').value.trim(),notes:$('#review-notes').value.trim(),verified_role:$('#review-role').value||null,evidence,...(state.casebook?{expected_revision:state.casebook.revision}:{}),...datasetFingerprintGuard()};
  try{const result=await api('/api/reviews',{method:'POST',body:JSON.stringify(payload)});if(revision!==state.datasetRevision)return;state.casebook=result;renderReviews();populateReview(payload.gid);$('#review-save-status').textContent='Тексеру және дәлел сілтемелері сақталды.';toast('Аналитик тексеруі сақталды.');}
  catch(error){if(revision!==state.datasetRevision)return;$('#review-save-status').textContent=error.message;toast(error.message,true);}finally{button.disabled=false;}
}
async function previewLabels(file) {
  state.labelsPending=null;$('#labels-import').disabled=true;if(!file)return;
  try{const text=await file.text(),isCSV=file.name.toLowerCase().endsWith('.csv');const parsed=isCSV?csvRows(text):exactJSON(text);const rows=Array.isArray(parsed)?parsed:parsed.labels;if(!Array.isArray(rows)||!rows.length)throw new Error('Белгілер массиві бос немесе жоқ. JSON үшін labels массивін қолданыңыз.');
    const {labels,skipped}=normalizeLabelRows(rows,isCSV);
    state.labelsPending=labels;$('#labels-preview').innerHTML=`<div class="preview-success">${icon('check')}<span>${count(labels.length)} толтырылған белгі оқылды.${skipped?' '+count(skipped)+' толтырылмаған үлгі жолы өткізілді.':''} ${labels.length?'Сақтау кезінде деректер жиынымен сәйкестігі қайта тексеріледі.':'Кемінде бір шоттың рөлін, дереккөзін және аналитик белгісін толтырыңыз.'}</span></div>`;$('#labels-import').disabled=!labels.length;
  }catch(error){labError('#labels-preview',error);}
}
async function importLabels() {
  if(!state.labelsPending?.length)return;const revision=state.datasetRevision;$('#labels-import').disabled=true;
  try{const result=await api('/api/reviews',{method:'POST',body:JSON.stringify({action:'import_labels',labels:state.labelsPending,...(state.casebook?{expected_revision:state.casebook.revision}:{}),...datasetFingerprintGuard()})});if(revision!==state.datasetRevision)return;state.casebook=result;renderReviews();$('#labels-preview').innerHTML='<div class="preview-success">'+icon('check')+'Белгілер сақталды. Бағалау жаңартылды.</div>';state.labelsPending=null;toast('Тексерілген белгілер импортталды.');}
  catch(error){if(revision!==state.datasetRevision)return;labError('#labels-preview',error);$('#labels-import').disabled=false;}
}
function expansionInput() {
  const input=exactJSON($('#expansion-json').value);const rows=Array.isArray(input)?input:input.transactions;if(!Array.isArray(rows)||!rows.length)throw new Error('transactions массивінде кемінде бір қосымша аударым болуы керек.');
  const ids=new Set();for(let i=0;i<rows.length;i++){const row=rows[i];for(const field of ['src','dst','date','sum_kzt','source_reference','transaction_id'])if(row[field]==null||String(row[field]).trim()==='')throw new Error(`${i+1}-жолда ${field} толтырылмаған.`);if(!/^-?\d+$/.test(gidKey(row.src))||!/^-?\d+$/.test(gidKey(row.dst)))throw new Error(`${i+1}-жолдағы src/dst бүтін шот ID болуы керек.`);if(!Number.isFinite(Number(row.sum_kzt))||Number(row.sum_kzt)<=0)throw new Error(`${i+1}-жолдағы сома оң сан болуы керек.`);const id=String(row.source_reference)+'\n'+String(row.transaction_id);if(ids.has(id))throw new Error(`${i+1}-жолда дереккөз бен transaction_id қайталанады.`);ids.add(id);}
  return rows;
}
function previewExpansion() {
  try{const rows=expansionInput(),ids=new Set(rows.flatMap(r=>[gidKey(r.src),gidKey(r.dst)])),newIds=[...ids].filter(id=>!state.nodes.has(id));$('#expansion-preview').innerHTML=`<div class="preview-success">${icon('check')}<span>${count(rows.length)} жазба · ${count(ids.size)} шот · бастапқы графта жоқ ${count(newIds.length)} ID · ${shortMoney(rows.reduce((sum,r)=>sum+Number(r.sum_kzt),0))}. Бұл тек файл құрылымының тексеруі; дереккөздің шынайылығын растамайды.</span></div>`;return rows;}
  catch(error){labError('#expansion-preview',error);return null;}
}
async function saveExpansion() {
  const rows=previewExpansion();if(!rows)return;if(!$('#expansion-disjoint').checked){labError('#expansion-preview',new Error('Алдымен қосымша жазбалардың бастапқы үзіндіден бөлек екенін растаңыз.'));return;}
  const button=$('#expansion-submit');button.disabled=true;button.textContent='Қосымша граф есептелуде…';const revision=state.datasetRevision;
  try{const result=await api('/api/expand',{method:'POST',body:JSON.stringify({incremental_disjoint:true,transactions:rows,...datasetFingerprintGuard()})});if(revision!==state.datasetRevision)return;state.expansion=result;state.expansionLimit=25;renderExpansion();$('#expansion-preview').innerHTML=`<div class="preview-success">${icon('check')}Қосымша граф сақталды. Бастапқы есеп пен рөлдер өзгертілмеді.</div>`;toast('Қосымша аударымдар бөлек графқа сақталды.');}
  catch(error){if(revision!==state.datasetRevision)return;labError('#expansion-preview',error);}finally{button.disabled=false;button.textContent='Қосымша графқа сақтау';}
}
async function loadExpansion() {
  const revision=state.datasetRevision;try{const result=await api('/api/expansion');if(revision!==state.datasetRevision)return;state.expansion=result.available===false?null:result;renderExpansion();}catch(error){labError('#expansion-summary',error);}
}
function renderExpansion() {
  const result=state.expansion;$('#expansion-download').disabled=!result?.graph;updateExploreScope();
  if(!result?.graph){$('#expansion-summary').innerHTML='<p class="lab-note">Қосымша аударымдар жүктелмеген. JSON файлында дереккөз бен әр операцияның бірегей ID-ін көрсетіңіз.</p>';$('#expansion-links').innerHTML='<div class="no-results">Қосымша граф сақталғаннан кейін байланыстар осында ашылады.</div>';$('#expansion-provenance').innerHTML='';$('#expansion-more').classList.add('hidden');return;}
  const graphData=result.graph,meta=graphData.meta||{},provenance=result.provenance||graphData.expansion||{},comparison=result.base_comparison||{};
  $('#expansion-summary').innerHTML=`<div class="evaluation-stats"><div><strong>${count(graphData.nodes.length)}</strong><span>Кеңейтілген графтағы шот</span></div><div><strong>${count(graphData.edges.length)}</strong><span>Бақыланған байланыс</span></div><div><strong>${count(provenance.total_supplementary_transactions)}</strong><span>Барлық қосымша жазба</span></div><div><strong>${count(comparison.new_nodes)}</strong><span>Соңғы импорттағы жаңа шот</span></div></div><p class="lab-note">${escapeHTML(result.note||'Бастапқы рөлдер қайта есептелмеген.')}</p><p class="lab-note">Кезең: ${niceDate(meta.period_start)} — ${niceDate(meta.period_end)}. Соңғы импорт: ${count(provenance.accepted_transactions)} қабылданды, ${count(provenance.duplicate_transactions)} бұрын сақталған ID өткізілді.</p>`;
  $('#expansion-provenance').innerHTML=`<h3>Дереккөздер</h3>${(provenance.supplementary_sources||[]).map(source=>`<div class="provenance-row"><span>${escapeHTML(source.source_reference)}</span><strong>${count(source.n_transactions)} жазба</strong></div>`).join('')}${(provenance.warnings||[]).map(text=>`<p class="provenance-warning">${escapeHTML(text)}</p>`).join('')}`;
  const supplementaryPairs=new Set((graphData.expansion?.records||[]).map(r=>gidKey(r.src)+'→'+gidKey(r.dst)));const edges=[...graphData.edges].filter(e=>!state.expansionFilter||gidKey(e.src).includes(state.expansionFilter)||gidKey(e.dst).includes(state.expansionFilter)).sort((a,b)=>Number(supplementaryPairs.has(gidKey(b.src)+'→'+gidKey(b.dst)))-Number(supplementaryPairs.has(gidKey(a.src)+'→'+gidKey(a.dst))));
  $('#expansion-links').innerHTML=`<div class="lab-list-count">${Math.min(edges.length,state.expansionLimit)} / ${count(edges.length)} байланыс көрсетілді · сома бастапқы және қосымша жазбаларды қамтиды</div>`+edges.slice(0,state.expansionLimit).map(e=>`<div class="expanded-edge"><div><button data-expanded-node="${escapeHTML(e.src)}">#${escapeHTML(e.src)}</button><span>→</span><button data-expanded-node="${escapeHTML(e.dst)}">#${escapeHTML(e.dst)}</button></div><div><strong>${shortMoney(e.sum_kzt)}</strong><span>${count(e.n_tx)} аударым</span>${supplementaryPairs.has(gidKey(e.src)+'→'+gidKey(e.dst))?'<small>Қосымша жазба бар</small>':''}</div></div>`).join('');$('#expansion-more').classList.toggle('hidden',state.expansionLimit>=edges.length);$$('[data-expanded-node]').forEach(b=>b.onclick=()=>openExpandedNode(b.dataset.expandedNode));
}
function openExpandedNode(gid) {
  const key=gidKey(gid),n=state.expansion?.graph?.nodes?.find(node=>gidKey(node.gid)===key);if(!n){if(state.nodes.has(key))selectNode(key,true);else toast('Шот ағымдағы деректе жоқ.',true);return;}
  const records=(state.expansion.graph.expansion?.records||[]).filter(r=>gidKey(r.src)===key||gidKey(r.dst)===key),base=state.nodes.get(key);const depth=n.observed_depth??n.depth;
  modal(`<div><div class="modal-eyebrow">ҚОСЫМША ГРАФ · БАҚЫЛАНҒАН ДЕРЕК</div><h2 class="long-gid">#${escapeHTML(key)}</h2><p>${base?'Шот бастапқы үзіндіде де бар. Рөл мен ұпай сол үзіндіге қатысты.':'Шот қосымша деректе алғаш көрінді. Рөл мен басымдық тағайындалмаған.'}</p></div>`,`<div class="simulation-notice">${icon('warning')}<span>${escapeHTML(n.scope_note||'Кеңейтілген ағындар бойынша рөлдер қайта есептелмеген.')}</span></div><div class="simulation-grid"><div class="simulation-stat"><span>Кеңейтілген кіріс</span><strong>${shortMoney(n.in_kzt)}</strong><p>${count(n.in_tx)} аударым · ${count(n.in_degree)} төлеуші</p></div><div class="simulation-stat"><span>Кеңейтілген шығыс</span><strong>${shortMoney(n.out_kzt)}</strong><p>${count(n.out_tx)} аударым · ${count(n.out_degree)} алушы</p></div></div><p>Бастапқы шоттардан ең аз бақыланған қадам: <strong>${depth==null?'Жол көрінбейді':escapeHTML(depth)}</strong></p>${base?`<p>Бастапқы рөл гипотезасы: ${roleBadge(base.role)} · ${percent(base.priority_score)}/100</p>`:'<p class="unknown-role">Рөл: анықталмаған · ұпай есептелмеген</p>'}<h3 class="lab-modal-title">Қосымша дереккөз жазбалары</h3><div class="node-source-records">${records.slice(0,12).map(r=>`<div><strong>${niceDate(r.date)} · ${shortMoney(r.sum_kzt)}</strong><span>${escapeHTML(r.source_reference)} · ${escapeHTML(r.transaction_id)}</span></div>`).join('')||'<p>Бұл шотқа тікелей жаңа жазба тіркелмеген.</p>'}</div>${records.length>12?'<p>Алғашқы 12 жазба көрсетілді; толық тізім граф JSON файлында.</p>':''}`,`${base?'<button class="button button-quiet" id="expanded-base-card">Бастапқы шот картасы</button>':''}<button class="button button-primary" id="expanded-explore">Осы шоттан бағыт іздеу</button>`);
  if($('#expanded-base-card'))$('#expanded-base-card').onclick=()=>{$('#modal').close();selectNode(key,true);};$('#expanded-explore').onclick=()=>{$('#modal').close();showView('lab');showLabTab('search');$('#explore-start').value=key;$('#explore-scope').value='expanded';updateExploreScope();};
}
function downloadExpansion() {if(!state.expansion?.graph)return;const blob=new Blob([JSON.stringify(state.expansion,null,2)],{type:'application/json;charset=utf-8'}),url=URL.createObjectURL(blob),link=document.createElement('a');link.href=url;link.download='aqsha_expanded_graph.json';link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
function updateExploreScope() {const selector=$('#explore-scope');if(!selector)return;$('#explore-scope-expanded').disabled=!state.expansion?.graph;if(selector.value==='expanded'&&!state.expansion?.graph)selector.value='base';$('#explore-source-label').textContent=selector.value==='expanded'?'Бастапқы + құжатталған қосымша аударымдар бойынша':'Бастапқы бақыланған граф бойынша';}
function syncExploreKind() {const kind=$('#explore-kind').value,shortest=kind==='shortest';$('#explore-end').disabled=kind==='cycles';$('#explore-end').required=shortest;$('#explore-hops').disabled=shortest;$('#explore-limit').disabled=shortest;$('#explore-budget').disabled=shortest;$('#explore-kind-note').textContent=shortest?'Ең қысқа жол бүкіл таңдалған графтан есептеледі; қадам мен кандидат шегі қолданылмайды.':kind==='cycles'?'Іздеу бастапқы шотқа қайтатын қарапайым циклдерді табады. Соңғы шот қажет емес.':'Соңғы шотты бос қалдырсаңыз, бастапқы шоттан шығатын бағыттар ізделеді.';}
async function runExplore(append=false) {
  const button=$('#explore-submit');button.disabled=true;$('#explore-more').disabled=true;const revision=state.datasetRevision;
  if(!append){const kind=$('#explore-kind').value;state.explorePayload={scope:$('#explore-scope').value,start_gid:$('#explore-start').value.trim(),kind,max_hops:Number($('#explore-hops').value),max_results:Number($('#explore-limit').value),budget:Number($('#explore-budget').value),...(kind!=='cycles'&&$('#explore-end').value.trim()?{end_gid:$('#explore-end').value.trim()}:{})};state.exploreResponse=null;$('#explore-results').innerHTML='';}
  $('#explore-summary').textContent='Бағытталған байланыстар зерттелуде…';
  try{const cursor=append?state.exploreResponse?.next_cursor:null;const result=await api('/api/explore',{method:'POST',body:JSON.stringify({...state.explorePayload,...(cursor?{cursor}:{})})});if(revision!==state.datasetRevision)return;if(append)result.routes=[...(state.exploreResponse?.routes||[]),...(result.routes||[])];state.exploreResponse=result;renderExplore();}
  catch(error){labError('#explore-summary',error);}finally{button.disabled=false;$('#explore-more').disabled=false;}
}
function renderExplore() {
  const result=state.exploreResponse;if(!result)return;const routes=result.routes||[],limits=result.limits||{},scope=state.explorePayload?.scope||'base';
  $('#explore-summary').innerHTML=`<span>${count(routes.length)} бағыт көрсетілді · ${scope==='expanded'?'қосымша граф':'бастапқы граф'} · ${count(result.scope?.graph_nodes)} шот</span><span>${result.complete_within_scope?'Сұралған аяда іздеу аяқталды.':'Іздеу шекте тоқтады; келесі бөлікті жалғастыруға болады.'}${limits.cumulative_work!=null?' '+count(limits.cumulative_work)+' кандидат қаралды.':''}</span>`;
  $('#explore-results').innerHTML=routes.map((route,i)=>`<article class="pattern-card"><div class="pattern-card-header"><span class="pattern-kind">${state.explorePayload.kind==='cycles'?'Бағытталған цикл':state.explorePayload.kind==='shortest'?'Ең қысқа бағыт':'Бағытталған жол'}</span><span class="pattern-date">${count(route.length)} байланыс</span></div><div class="pattern-accounts explore-accounts">${(route.gids||[]).map(gid=>`<button data-explore-node="${escapeHTML(gid)}">#${escapeHTML(gid)}</button>`).join('<span>→</span>')}</div><p>${escapeHTML(route.evidence)}</p><div class="pattern-metric"><span>Қабырға сомаларының қосындысы</span><strong>${shortMoney(route.observed_volume_kzt)}</strong></div><button class="text-button" data-explore-route="${i}">${scope==='base'?'Графта белгілеу':'Байланыс дәлелдерін ашу'} ${icon('arrow-right')}</button></article>`).join('')||'<div class="no-results">Осы аяда бағыт табылмады. Бұл көрінбейтін аударымдар жоқ деген тұжырым емес.</div>';$('#explore-more').classList.toggle('hidden',!result.next_cursor);
  $$('[data-explore-node]').forEach(b=>b.onclick=()=>scope==='expanded'?openExpandedNode(b.dataset.exploreNode):selectNode(b.dataset.exploreNode,true));$$('[data-explore-route]').forEach(b=>b.onclick=()=>{const route=routes[Number(b.dataset.exploreRoute)];if(scope==='base')openInsight({...route,title:'Терең іздеу · '+count(route.length)+' байланыс'},state.explorePayload.kind==='cycles'?'cycles':'routes');else openRouteEvidence(route);});
}
function openRouteEvidence(route) {modal('<div><div class="modal-eyebrow">ҚОСЫМША ГРАФ · НАҚТЫ БАЙЛАНЫСТАР</div><h2>Бағыттағы аударымдар</h2><p>Құрылымдық жол. Ақшаның уақыт ретімен өткенін немесе бір қаражат екенін дәлелдемейді.</p></div>',`<div class="route-evidence-list">${(route.edges||[]).map(e=>`<div><div><button data-route-node="${escapeHTML(e.src)}">#${escapeHTML(e.src)}</button><span>→</span><button data-route-node="${escapeHTML(e.dst)}">#${escapeHTML(e.dst)}</button></div><p>${shortMoney(e.sum_kzt)} · ${count(e.n_tx)} бақыланған аударым</p></div>`).join('')}</div>`);$$('[data-route-node]').forEach(b=>b.onclick=()=>openExpandedNode(b.dataset.routeNode));}
async function runRecovery(e) {
  e.preventDefault();const button=$('#recovery-submit');button.disabled=true;$('#recovery-results').innerHTML='<div class="no-results">Жорамал сценарий құрылымы есептелуде…</div>';const revision=state.datasetRevision;
  try{const result=await api('/api/recovery',{method:'POST',body:JSON.stringify({top_n:Number($('#recovery-top').value),replacement_fraction:Number($('#recovery-fraction').value)/100})});if(revision!==state.datasetRevision)return;renderRecovery(result);}
  catch(error){labError('#recovery-results',error);}finally{button.disabled=false;}
}
function renderRecovery(result) {
  const metrics=[['n_nodes','Түйіндер'],['n_edges','Байланыстар'],['components','Байланыс компоненттері'],['largest_component','Ең үлкен компонент'],['reachable_from_seeds','Бастапқы шоттардан жететін түйіндер']];
  $('#recovery-results').innerHTML=`<div class="recovery-stage-labels"><div><span class="observed-badge">БАҚЫЛАНҒАН</span><h3>Бастапқы желі</h3><p>Жүктелген транзакциялар</p></div><div><span class="removed-badge">ҚҰРЫЛЫМДЫҚ ӨЗГЕРІС</span><h3>${count(result.removed?.length)} түйін алынған</h3><p>Графтан математикалық алу</p></div><div><span class="assumption-badge">ЖОРАМАЛ</span><h3>${percent(result.replacement_fraction)}% қайта байланысу</h3><p>Ықтималдық немесе болжам емес</p></div></div><div class="table-scroll"><table class="lab-table recovery-table"><thead><tr><th>Көрсеткіш</th><th>Бастапқы</th><th>Алынғаннан кейін</th><th>Жорамал сценарий</th></tr></thead><tbody>${metrics.map(([key,label])=>`<tr><td>${label}</td><td>${count(result.baseline?.[key])}</td><td>${count(result.post_removal?.[key])}</td><td>${count(result.scenario?.[key])}</td></tr>`).join('')}</tbody></table></div><div class="recovery-assumptions"><h3>Сценарийге енгізілген жорамалдар</h3><p>${count(result.hypothetical_nodes?.length)} жорамал түйін · ${count(result.assumed_edges?.length)} жорамал байланыс · ${count(result.observed_survivors_reconnected)} сақталған шоттың қолжетімділігі қайтты</p>${(result.assumptions||[]).map(text=>`<p>${escapeHTML(text)}</p>`).join('')}<p>${escapeHTML(result.note||'')}</p></div><details class="recovery-edge-details"><summary>Жорамал байланыстарды бөлек көру (${count(result.assumed_edges?.length)})</summary><p>Төмендегі байланыстар — сценарийде қосылған, бақыланған транзакциялар емес. Алғашқы 30 байланыс көрсетіледі.</p>${(result.assumed_edges||[]).slice(0,30).map(edge=>`<div><span class="assumption-badge">ЖОРАМАЛ</span><strong>${escapeHTML(scenarioNodeLabel(edge.src))} → ${escapeHTML(scenarioNodeLabel(edge.dst))}</strong><small>Негіз болған байланыс: #${escapeHTML(edge.reference_src)} → #${escapeHTML(edge.reference_dst)} · бұрын бақыланған ${shortMoney(edge.prior_observed_kzt)}</small></div>`).join('')}</details>`;
}
function scenarioNodeLabel(id) {const match=/^hypothetical-(\d+)$/.exec(String(id));return match?'Жорамал түйін '+match[1]:'#'+String(id);}
function assistantModeText(response) {if(response.mode==='local_rules_guard'||response.guarded)return 'Дерек шегін тексеру';return response.mode==='local_llm'?'Жергілікті тіл моделі'+(response.model?' · '+String(response.model):''):'Жергілікті ережелер · LLM емес';}
function updateAssistantModeLabel() {const local=$('#assistant-mode').value==='local_llm';const badge=$('.assistant-main .panel-heading .small-pill');if(badge)badge.textContent=local?'ЖЕРГІЛІКТІ ТІЛ МОДЕЛІ':'ЖЕРГІЛІКТІ ЕРЕЖЕЛЕР · LLM ЕМЕС';}
async function loadAssistantStatus() {
  if(!$('#assistant-model-status'))return;$('#assistant-model-status').textContent='Жергілікті модель күйі тексерілуде…';
  try{const status=await api('/api/assistant/status');state.assistantStatus=status;const available=status.available===true;$('#assistant-mode-llm').disabled=!available;if(!available&&$('#assistant-mode').value==='local_llm')$('#assistant-mode').value='local_rules';$('#assistant-model-status').textContent=available?'Модель дайын: '+String(status.model||'жергілікті тіл моделі'):'Жергілікті тіл моделі қосылмаған. Ережелік режим қолжетімді.';updateAssistantModeLabel();}
  catch(error){$('#assistant-model-status').textContent='Модель күйі алынбады. Ережелік режимді пайдаланыңыз.';$('#assistant-mode-llm').disabled=true;}
}

function setupLab() {
  $('#review-role').innerHTML='<option value="">Рөл әлі расталмаған</option>'+REVIEW_ROLES.map(role=>`<option value="${role}">${escapeHTML(roleInfo(role).label)}</option>`).join('');
  $('.label-import').insertAdjacentHTML('beforeend','<div class="lab-inline-links"><a href="/api/reviews/template.csv" download>CSV үлгісін жүктеу</a><a href="/api/reviews/export.json" download>Тексерулер JSON</a></div>');
  $('#explore-form .lab-form-footer').insertAdjacentHTML('beforebegin','<div class="explore-scope-row"><label for="explore-scope">Деректер аясы<select id="explore-scope" aria-label="Деректер аясы"><option value="base">Бастапқы граф</option><option value="expanded" id="explore-scope-expanded" disabled>Бастапқы + қосымша граф</option></select></label><p id="explore-kind-note"></p></div>');
  $('#assistant-form').insertAdjacentHTML('beforebegin',`<div class="assistant-mode-controls"><div><label for="assistant-mode">Жауап режимі<select id="assistant-mode" aria-label="Жауап режимі"><option value="local_rules">Түсіндірмелі ережелер</option><option value="local_llm" id="assistant-mode-llm" disabled>Жергілікті тіл моделі</option></select></label><button class="text-button" id="assistant-status-refresh">Күйін жаңарту ${icon('refresh')}</button></div><p id="assistant-model-status">Ережелік режим дайын. Модель күйін жаңарту арқылы тексеріңіз.</p></div>`);
  $$('[data-lab-tab]').forEach(button=>button.onclick=()=>showLabTab(button.dataset.labTab));$('#review-form').onsubmit=saveReview;$('#review-status').onchange=syncReviewRequirements;$('#review-use-selected').onclick=()=>populateReview(state.selected);$('#review-gid').onchange=e=>populateReview(e.target.value);$('#review-refresh').onclick=loadReviews;$('#labels-file').onchange=e=>previewLabels(e.target.files[0]);$('#labels-import').onclick=importLabels;
  $('#expansion-file').onchange=async e=>{const file=e.target.files[0];if(!file)return;try{$('#expansion-json').value=await file.text();previewExpansion();}catch(error){labError('#expansion-preview',error);}};$('#expansion-preview-button').onclick=previewExpansion;$('#expansion-submit').onclick=saveExpansion;$('#expansion-refresh').onclick=loadExpansion;$('#expansion-download').onclick=downloadExpansion;$('#expansion-go-search').onclick=()=>{showLabTab('search');if(state.expansion?.graph)$('#explore-scope').value='expanded';updateExploreScope();};$('#expansion-search').oninput=e=>{state.expansionFilter=e.target.value.trim().replace(/^#/,'');state.expansionLimit=25;renderExpansion();};$('#expansion-more').onclick=()=>{state.expansionLimit+=25;renderExpansion();};
  $('#explore-form').onsubmit=e=>{e.preventDefault();runExplore(false);};$('#explore-more').onclick=()=>runExplore(true);$('#explore-kind').onchange=syncExploreKind;$('#explore-scope').onchange=updateExploreScope;$('#recovery-form').onsubmit=runRecovery;$('#recovery-fraction').oninput=e=>{$('#recovery-fraction-label').textContent=e.target.value+'%';};$('#assistant-mode').onchange=updateAssistantModeLabel;$('#assistant-status-refresh').onclick=loadAssistantStatus;syncExploreKind();syncReviewRequirements();
}
setupLab();

async function init() {
  showView(location.hash.slice(1)||'graph',false);
  try{setData(await api('/api/analysis'));}
  catch(error){$('#canvas-loading').innerHTML=`${icon('warning')}<strong>Деректерді ашу мүмкін болмады</strong><span style="max-width:330px;text-align:center;padding:0 15px">${escapeHTML(error.message)}</span><button class="button button-primary button-small" id="initial-demo">Демоны іске қосу</button>`;$('#initial-demo').onclick=()=>$('#reset-demo').click();}
}
init();

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
  state.data=data; state.nodes=new Map(data.nodes.map(n=>[gidKey(n.gid),n]));
  state.adj=new Map(data.nodes.map(n=>[gidKey(n.gid),new Set()]));
  data.edges.forEach(e=>{state.adj.get(gidKey(e.src))?.add(gidKey(e.dst));state.adj.get(gidKey(e.dst))?.add(gidKey(e.src));});
  const first=(data.top_nodes||[]).find(n=>state.nodes.has(gidKey(n.gid)))||data.nodes[0];
  state.selected=first?gidKey(first.gid):null;state.depth=4;state.cluster='all';state.role='all';state.focus=null;state.rankingPage=0;state.clusterLimit=18;state.requestLimit=25;state.rankingFilter='';state.rankingRole='all';
  $('#ranking-search').value='';$('#node-search').value='';
  $('#canvas-loading').classList.add('hidden');
  renderOverview();renderFilterOptions();renderDetail();renderRanking();renderClusters();renderBlindspots();renderTimeline();buildGraph(true);
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
    <div class="detail-heading"><span>ШОТ ПРОФИЛІ</span><span class="small-pill">${n.is_seed?'БАСТАПҚЫ ШОТ':escapeHTML(n.depth)+'-ҚАДАМ'}</span></div>
    <div class="detail-top"><div class="account-title"><div class="account-avatar" style="color:${r.color}">${icon('nodes')}</div><div><h3>#${escapeHTML(n.gid)}</h3><p>Қауымдастық ${escapeHTML(n.cluster_id)} · ${count(n.in_degree+n.out_degree)} байланыс</p></div></div>
    <div class="detail-role-row">${roleBadge(n.role)}<span>Гипотеза</span></div>
    <div class="priority-box"><div class="priority-top"><span>Тексеру басымдығы</span><strong class="priority-number">${percent(n.priority_score)}<small> / 100</small></strong></div><div class="score-track"><span style="width:${percent(n.priority_score)}%"></span></div><p>Эвристикалық ұпай · ықтималдық емес</p></div></div>
    <div class="detail-evidence"><div class="detail-section-label">${icon('shield')}НЕЛІКТЕН ОСЫ ШОТ?</div><p class="evidence-text">${escapeHTML(n.evidence)}</p></div>
    <div class="detail-stats"><div class="detail-stat"><span>Кіріс · ${count(n.in_degree)} төлеуші</span><strong title="${fullMoney(n.in_kzt)}">${shortMoney(n.in_kzt)}</strong>${n.in_tx==null?'':`<span class="detail-tx">${count(n.in_tx)} аударым</span>`}</div><div class="detail-stat"><span>Шығыс · ${count(n.out_degree)} алушы</span><strong title="${fullMoney(n.out_kzt)}">${shortMoney(n.out_kzt)}</strong>${n.out_tx==null?'':`<span class="detail-tx">${count(n.out_tx)} аударым</span>`}</div><div class="detail-stat"><span>Бақыланған шығыс / кіріс</span><strong>${n.pass_through==null?'— <small>толық емес</small>':decimal.format(n.pass_through)}</strong></div><div class="detail-stat"><span>Рөл белгісінің күші</span><strong>${percent(n.role_score)}<small> / 100</small></strong></div><div class="detail-stat"><span>Белсенді күндер</span><strong>${count(temporal.active_days)}</strong></div><div class="detail-stat"><span>Бір күндегі төлеушілер</span><strong>${count(temporal.synchronized_payers)}</strong></div></div>
    ${flags.length?`<div class="detail-flags">${flags.slice(0,3).map(f=>`<div class="detail-flag">${icon('warning')}<span>${escapeHTML(FLAGS[f]||f)}</span></div>`).join('')}</div>`:''}
    <div class="detail-actions"><button class="button button-primary" id="node-simulate">Осы шотсыз желі ${icon('arrow-right')}</button><button class="text-button" id="node-focus">${icon('route')}Екі қадамдық маңайын ашу</button></div>`;
  $('#node-simulate').onclick=()=>openSimulation();$('#node-focus').onclick=()=>focusNode(state.selected);
}

function showView(view, updateHash=true) {
  if(!['graph','ranking','clusters','blindspots'].includes(view))view='graph';state.view=view;
  $$('.view').forEach(el=>el.classList.toggle('active',el.id===view+'-view'));$$('[data-view]').forEach(el=>el.classList.toggle('active',el.dataset.view===view));
  const names={graph:['Ақша ізін <span>ашыңыз.</span>','Жекелеген аударымдардан — қаржы құрылымының тұтас көрінісіне.','Ақша графы'],ranking:['Дәлелге сүйенген <span>басымдық.</span>','Маңызды түйіндерді табыңыз. Әр ұпайдың артындағы белгілерді тексеріңіз.','Тексеру кезегі'],clusters:['Бір желі. <span>Бірнеше құрылым.</span>','Ақша ағындарын біріктіретін қауымдастықтарды зерттеңіз.','Қауымдастықтар'],blindspots:['Көрінбейтінді <span>ескеріңіз.</span>','Дерек шекараларын анықтаңыз және келесі сұрауды негіздеңіз.','Бақылау шегі']};
  $('#page-title').innerHTML=names[view][0];$('#page-subtitle').textContent=names[view][1];$('#breadcrumb-current').textContent=names[view][2];
  if(updateHash)history.replaceState(null,'','#'+view);
  if(view==='graph')requestAnimationFrame(resizeGraph);
}

function selectNode(gid, focus=false) {
  const key=gidKey(gid);if(!state.nodes.has(key)){toast('Бұл ID деректерде табылмады.',true);return false;}
  state.selected=key;state.depth=4;state.cluster='all';state.role='all';state.focus=focus?key:null;
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
  $('#timeline').innerHTML=timeline.map(t=>`<div class="timeline-bar" style="height:${Math.max(2,num(t.sum_kzt)/max*100)}%" title="${niceDate(t.date)} · ${fullMoney(t.sum_kzt)} · ${count(t.n_tx)} транзакция"></div>`).join('');
  $('#timeline-start').textContent=niceDate(timeline[0]?.date);$('#timeline-end').textContent=niceDate(timeline[timeline.length-1]?.date);
}

function buildGraph(reset=false) {
  if(!state.data)return;
  let candidates=state.data.nodes.filter(n=>num(n.depth)<=state.depth&&(state.cluster==='all'||String(n.cluster_id)===state.cluster)&&(state.role==='all'||n.role===state.role));
  const eligible=new Set(candidates.map(n=>gidKey(n.gid)));let chosen=new Set();
  const limit=state.focus?170:130;
  const add=k=>{if(eligible.has(k)&&chosen.size<limit)chosen.add(k);};
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
  graph.edges=state.data.edges.filter(e=>chosen.has(gidKey(e.src))&&chosen.has(gidKey(e.dst)));
  $('#graph-count').textContent=count(graph.nodes.length)+' / '+count(candidates.length);
  $('#graph-scope').textContent=state.focus?`Маңай: ${count(graph.nodes.length)} / ${count(candidates.length)} шот · 2 байланыс қашықтығы`:`Шолу: ${count(graph.nodes.length)} / ${count(candidates.length)} шот · барлық ${count(state.data.nodes.length)} шот рейтингте`;
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
  const assign=()=>{for(const [d,nodes] of columns){nodes.forEach((n,i)=>{const key=gidKey(n.gid),jitter=((hash(key)%101)/100-.5)*Math.min(usableW/maxDepth*.26,20);const deg=num(n.in_degree)+num(n.out_degree);const radius=Math.min(11,3.1+Math.log2(deg+1)*.8);graph.positions.set(key,{x:marginX+(d/maxDepth)*usableW+jitter,y:marginY+(i+.5)/Math.max(1,nodes.length)*usableH,r:radius,n});});}};
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
    const c=edgeCurve(a,b);if(!c)continue;const selected=ak===active||bk===active;
    ctx.beginPath();ctx.moveTo(c.ax,c.ay);ctx.bezierCurveTo(c.c1x,c.c1y,c.c2x,c.c2y,c.bx,c.by);
    ctx.strokeStyle=selected?'#aaca6f88':'#6880542f';ctx.lineWidth=selected?1.35:.65+Math.min(.8,Math.log10(Math.max(1,num(e.sum_kzt)))*.075);ctx.stroke();
    const point=curvePoint(c,.80),previous=curvePoint(c,.78),angle=Math.atan2(point.y-previous.y,point.x-previous.x);const arrow=selected?3.9:2.8;
    ctx.beginPath();ctx.moveTo(point.x,point.y);ctx.lineTo(point.x-arrow*Math.cos(angle-.52),point.y-arrow*Math.sin(angle-.52));ctx.lineTo(point.x-arrow*Math.cos(angle+.52),point.y-arrow*Math.sin(angle+.52));ctx.closePath();ctx.fillStyle=selected?'#b1d87ea0':'#81996165';ctx.fill();
    if(selected&&animated<14&&!window.matchMedia('(prefers-reduced-motion: reduce)').matches){const p=curvePoint(c,((time*.0001)+(hash(ak+bk)%100)/100)%1);ctx.beginPath();ctx.arc(p.x,p.y,1.25,0,Math.PI*2);ctx.fillStyle='#d6fda5';ctx.fill();animated++;}
  }
  for(const [key,p] of graph.positions){
    const selected=key===state.selected,hovered=key===graph.hover,relevant=key===active||connected.has(key),n=p.n;
    const color=n.is_seed?'#d1dfae':roleInfo(n.role).color;const boundary=num(n.depth)===4;
    if(selected||hovered){ctx.beginPath();ctx.arc(p.x,p.y,p.r+11,0,Math.PI*2);ctx.fillStyle='#abd47810';ctx.fill();ctx.beginPath();ctx.arc(p.x,p.y,p.r+7,0,Math.PI*2);ctx.strokeStyle='#c0ee8570';ctx.lineWidth=1;ctx.stroke();}
    if(n.is_seed){ctx.beginPath();ctx.arc(p.x,p.y,p.r+3,0,Math.PI*2);ctx.strokeStyle='#b5c99c50';ctx.lineWidth=.7;ctx.stroke();}
    ctx.globalAlpha=active&&!relevant?.58:1;ctx.beginPath();ctx.arc(p.x,p.y,selected?p.r+1:p.r,0,Math.PI*2);
    ctx.fillStyle=boundary?'#273024':color;ctx.fill();ctx.strokeStyle=boundary?'#c4a967':selected?'#e7ffb8':'#c6e5a520';ctx.lineWidth=boundary?1.3:selected?1.8:1;ctx.stroke();
    if(!boundary){ctx.beginPath();ctx.arc(p.x-1,p.y-1,Math.max(1,p.r*.28),0,Math.PI*2);ctx.fillStyle='#efffe450';ctx.fill();}
    ctx.globalAlpha=1;
    if(selected||hovered||(graph.zoom>1.4&&relevant)){
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
function animate(t){if(t-graph.lastFrame>45){drawGraph(t);graph.lastFrame=t;}requestAnimationFrame(animate);}requestAnimationFrame(animate);

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

async function openSimulation() {
  const n=state.nodes.get(state.selected);if(!n){toast('Алдымен шотты таңдаңыз.');return;}
  modal('<div><div class="modal-eyebrow">WHAT IF / ҚҰРЫЛЫМДЫҚ СЦЕНАРИЙ</div><h2>Осы шотсыз желі</h2><p>#'+escapeHTML(n.gid)+' шотының құрылымдағы үлесін тексеру.</p></div>',`<div class="simulation-notice">${icon('warning')}<span>Тек математикалық граф өзгереді. Бұл шотты нақты бұғаттау немесе қаржылық шығын болжамы емес.</span></div><div id="simulation-results"><div class="no-results"><span class="loading-orbit" style="display:block;margin:0 auto 13px"></span>Құрылым қайта есептелуде…</div></div>`);
  try{const result=await api('/api/simulate',{method:'POST',body:JSON.stringify({gids:[n.gid]})});if(!$('#simulation-results'))return;
    const b=result.before,a=result.after;
    $('#simulation-results').innerHTML=`<div class="simulation-account"><strong>#${escapeHTML(n.gid)}</strong>${roleBadge(n.role)}</div><div class="simulation-grid"><div class="simulation-stat"><span>Қолжетімділігі жоғалған шот</span><strong>${count(result.lost_reachable)}</strong><p>Бастапқы шоттардан бағытталған жол</p></div><div class="simulation-stat"><span>Алынған байланыстар ағыны</span><strong>${shortMoney(result.observed_flow_removed_kzt)}</strong><p>Бақыланған сома · шығын болжамы емес</p></div></div><table class="simulation-comparison"><thead><tr><th>ЖЕЛІ КӨРСЕТКІШІ</th><th>БҰРЫН</th><th>КЕЙІН</th></tr></thead><tbody>${[['n_nodes','Шоттар'],['n_edges','Байланыстар'],['components','Байланыс компоненттері'],['largest_component','Ең ірі компонент'],['reachable_from_seeds','Бастапқы шоттардан жететін түйіндер']].map(([k,label])=>`<tr><td>${label}</td><td>${count(b[k])}</td><td>${count(a[k])}</td></tr>`).join('')}</tbody></table><p class="simulation-result-note">${escapeHTML(result.note)}</p>`;
  }catch(error){if($('#simulation-results'))$('#simulation-results').innerHTML=`<div class="inline-error">${escapeHTML(error.message)}</div>`;}
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

async function init() {
  showView(location.hash.slice(1)||'graph',false);
  try{setData(await api('/api/analysis'));}
  catch(error){$('#canvas-loading').innerHTML=`${icon('warning')}<strong>Деректерді ашу мүмкін болмады</strong><span style="max-width:330px;text-align:center;padding:0 15px">${escapeHTML(error.message)}</span><button class="button button-primary button-small" id="initial-demo">Демоны іске қосу</button>`;$('#initial-demo').onclick=()=>$('#reset-demo').click();}
}
init();

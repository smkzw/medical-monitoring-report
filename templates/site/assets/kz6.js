/* V6 前端深度优化（审阅者 2026-11-02，docs/v6/FRONTEND.md）：
 *  - K.subjEvidence / K.rawBrowser：个例「原始数据」——逐表单浏览 listing 原行，带信号的行加徽标、点行看对应风险/质疑；
 *  - K.journey：受试者旅程泳道图（给药/访视/AE/合并用药/检验异常/质疑同一时间轴）；
 *  - K.groupSig：信号聚合（同受试者×同日期×同类别×同表单 → 一张卡），风险排名共用。
 * 颜色只表达两件事：风险等级（状态色，配文字）与身份；不用双 y 轴。 */
(function(){
const K=window.K;
const D=()=>window.KZ;
const shKey=(wb,sh)=>wb&&!String(sh).includes(':')?wb+':'+sh:sh;
/* ---- 个例证据索引：[{sh,row,kind,label,pr,open}] —— 检验风险行、专项/规则信号、医学质疑 */
K.allEvidence=()=>{if(K._ev)return K._ev;const by={},put=(sid,e)=>(by[sid]=by[sid]||[]).push(e);
  (K.lab||[]).filter(g=>!['NCS'].includes(g.risk)).forEach(g=>(g.pts||[]).forEach(p=>put(g.sid,{sh:shKey(p[11],p[7]),row:p[8],kind:'lab',label:`${g.test} · ${(K.RISK&&K.RISK[g.risk]&&K.RISK[g.risk][0])||g.risk}`,pr:g.pr||2,open:()=>K.showLabG(g)})));
  (D().others||[]).filter(o=>o.sh).forEach(o=>put(o.sid,{sh:shKey(o.wb,o.sh),row:o.row,kind:'oth',label:o.cat,pr:o.pr||1,open:()=>K.showOth(o)}));
  (D().queries||[]).forEach(q=>(q.ev||[]).forEach(e=>put(q.sid,{sh:e[0],row:e[1],kind:'q',label:`${q.id} ${K.catN(q.cat)}`,pr:4,open:()=>K.showQ(q.id)})));
  return K._ev=by};
K.subjEvidence=sid=>K.allEvidence()[sid]||[];
/* ---- 原始数据浏览器（个例） */
K.rawBrowser=async(el,sid,evid=[])=>{el.innerHTML='<div class="card empty">载入原始数据…</div>';
  const I=await K.rawIdx(),R=I&&await K.raw(sid);
  if(!I||!R){el.innerHTML='<div class="card empty">本报告未包含原始数据层（旧构建或该受试者无原始记录）。</div>';return}
  const ev={};evid.forEach(e=>{const k=K.rawKey(I,e.sh);if(!k)return;((ev[k]=ev[k]||{})[e.row]=ev[k][e.row]||[]).push(e)});
  const ks=Object.keys(R).sort((a,b)=>(Object.keys(ev[b]||{}).length-Object.keys(ev[a]||{}).length)||(I.sheets[a].mapped===I.sheets[b].mapped?0:I.sheets[a].mapped?-1:1)||I.sheets[a].name.localeCompare(I.sheets[b].name,'zh'));
  const DN={subjects:'受试者',visits:'访视',exposure:'给药',ae:'AE',mh:'病史',cm:'合并用药',proc:'操作',findings:'检查',lab:'检验',vs:'生命体征',ecg:'心电图',pe:'体格检查',exam:'专项检查',efficacy:'有效性',pd:'方案偏离',sample:'样本'};
  el.innerHTML=`<div class="grid" style="grid-template-columns:250px 1fr;gap:12px;align-items:start">
   <div class="card" style="padding:6px 0;max-height:760px;overflow:auto"><div class="xs muted" style="padding:2px 10px 6px">${ks.length} 张表单 · 有信号的排在前</div>${ks.map(k=>{const m=I.sheets[k],n=Object.keys(ev[k]||{}).length;
     return `<div class="it rs" data-k="${K.esc(k)}" style="padding:5px 10px;cursor:pointer;display:flex;gap:6px;align-items:center"><span class="small" style="flex:1;color:var(--ink)">${K.esc(m.name)}</span>${m.mapped?`<span class="xs faint">${K.esc(DN[m.domain]||m.domain||'')}</span>`:'<span class="xs" style="color:#B86400">未映射</span>'}<span class="xs faint">${R[k].length}</span>${n?`<span class="p org sq">${n}</span>`:''}</div>`}).join('')}</div>
   <div class="card" style="min-width:0;overflow:hidden"><div class="flex mb" style="gap:8px"><b id="rsn" style="color:var(--ink)"></b><span class="xs muted" id="rsm"></span><span class="sp"></span><input class="s" id="rsq" placeholder="在本表单内搜索" style="width:180px"><label class="xs muted"><input type="checkbox" id="rsh"> 只看有信号的行</label></div><div id="rst"></div>
   <div class="xs faint mt">橙底＝有风险/质疑的行（点行查看）；表头橙字为该表单的判定相关列；已剔除姓名/缩写等隐私列${(I.dropped||[]).length?'（'+I.dropped.map(K.esc).join('、')+'）':''}。</div></div></div>`;
  let cur=null;const q=el.querySelector('#rsq'),onlyHit=el.querySelector('#rsh');
  const draw=()=>{const m=I.sheets[cur],e=ev[cur]||{},kw=q.value.trim();
    let rows=R[cur];if(onlyHit.checked)rows=rows.filter(r=>e[r[0]]);if(kw)rows=rows.filter(r=>r.some(v=>String(v).includes(kw)));
    el.querySelector('#rsn').textContent=m.name;el.querySelector('#rsm').textContent=`${R[cur].length} 行${Object.keys(e).length?' · 信号 '+Object.keys(e).length+' 行':''}`;
    const box=el.querySelector('#rst');box.innerHTML=rows.length?K.rawTable(m,rows,new Set(Object.keys(e).map(Number)),{max:600}):'<div class="empty">无匹配行</div>';
    box.querySelectorAll('tr.hit').forEach(tr=>{tr.style.cursor='pointer';tr.onclick=()=>{const rn=+tr.firstElementChild.textContent,its=e[rn]||[];
      if(its.length===1)return its[0].open();
      const b=K.drawer(`${sid} · ${K.esc(m.name)} 第 ${rn} 行`,`<div class="small muted mb">本行涉及 ${its.length} 条风险/质疑</div>${its.map((x,i)=>`<div class="drow click" data-i="${i}" style="padding:6px 0;border-bottom:1px solid #F0F1F4">${K.p({lab:'检验',oth:'专项',q:'质疑'}[x.kind],x.kind==='q'?'org':'line')} ${K.esc(x.label)}</div>`).join('')}`);
      b.querySelectorAll('[data-i]').forEach(d=>d.onclick=()=>its[+d.dataset.i].open())}})};
  const pick=k=>{cur=k;el.querySelectorAll('.rs').forEach(x=>x.classList.toggle('on',x.dataset.k===k));draw()};
  el.querySelectorAll('.rs').forEach(x=>x.onclick=()=>pick(x.dataset.k));q.oninput=draw;onlyHit.onchange=draw;
  if(ks.length)pick(ks[0])};
/* ---- 受试者旅程（ECharts custom 泳道） */
const LANES=['给药','访视','不良事件','合并用药','检验异常','质疑'];
K.journeyH=d=>Math.min(320,120+Math.min(4,Math.max(1,...(d.ae||[]).map((_,i)=>i%4+1)))*12+Math.min(3,(d.cm||[]).length?2:0)*10);
K.journey=(el,d,{lr=[],ot=[],qs=[]}={})=>{if(!el||!window.echarts)return;
  const end=d.lo||d.ld||d.fd,clip=x=>x&&String(x).slice(0,10),isD=x=>/^\d{4}-\d{2}-\d{2}/.test(String(x||''));
  const bars=[],pts=[];
  (d.ec||[]).forEach(e=>{if(isD(e.s))bars.push({lane:0,s:clip(e.s),e:clip(isD(e.e)?e.e:e.s),c:'#587B3B',t:`给药 ${clip(e.s)}${isD(e.e)?' → '+clip(e.e):''}${e.n?' · '+e.n:''}${e.pause?' · '+e.pause:''}`,go:()=>K.evDrawer(`${d.id} · 研究药物给药`,d.id,[[K.evKey(e.wb,e.sh),e.row]])})});
  (d.visits||[]).forEach(v=>{if(isD(v[2]))pts.push({lane:1,d:clip(v[2]),c:'#407AAA',sym:'rect',sz:7,t:`${v[0]} 访视 ${clip(v[2])}`,lab:v[0],go:()=>K.evDrawer(`${d.id} · ${K.esc(v[0])} 访视`,d.id,[[K.evKey(v[5],v[4]),v[3]]])})});
  const gc=g=>{const n=parseInt(g)||0;return n>=3?'#8B0000':n===2?'#E67E00':'#E8C300'};
  (d.ae||[]).forEach((a,i)=>{if(!isD(a.s))return;bars.push({lane:2,sub:i%4,s:clip(a.s),e:clip(isD(a.e)?a.e:end),open:!isD(a.e),c:gc(a.g),bd:a.sae?'#000':null,
    t:`AE“${a.t}”${a.g||''}${a.sae?' · SAE':''}${a.aesi?' · AESI':''}<br>${clip(a.s)} → ${isD(a.e)?clip(a.e):'持续'}${a.rel?'<br>相关性：'+a.rel:''}`,go:()=>K.evDrawer(`${d.id} · AE ${K.esc(a.t)}`,d.id,[[K.evKey(a.wb,a.sh),a.row]],K.aeBox(a))})});
  (d.cm||[]).forEach((c,i)=>{   /* F12⑥：合并用药泳道不再 30 条截断（全部呈现） */if(!isD(c.s))return;bars.push({lane:3,sub:i%3,s:clip(c.s),e:clip(isD(c.e)?c.e:end),c:'#9DB7D3',t:`合并用药“${c.t}”<br>${clip(c.s)} → ${isD(c.e)?clip(c.e):'持续'}`,go:()=>K.evDrawer(`${d.id} · 合并用药 ${K.esc(c.t)}`,d.id,[[K.evKey(c.wb,c.sh),c.row]])})});
  lr.filter(g=>!['NCS','MHX-T'].includes(g.risk)).forEach(g=>(g.pts||[]).forEach(p=>{if(isD(p[1]))pts.push({lane:4,d:clip(p[1]),sev:p[5]===2?2:1,c:p[5]===2?'#8B0000':'#E67E00',sym:p[5]===2?'circle':'emptyCircle',sz:p[5]===2?10:8,t:`${g.test} ${p[2]??''} ${p[3]||''}（${p[0]||''}）${p[5]===2?' · CS':p[5]===1?' · NCS':''}${p[4]?' · '+p[4]+'级':''}<br>${K.esc(((K.RISK||{})[g.risk]||[g.risk])[0])}`,go:()=>K.showLabG(g)})}));
  ot.filter(o=>o.pr>=3&&isD(o.d)).forEach(o=>pts.push({lane:4,d:clip(o.d),c:'#B86400',sym:'diamond',sz:9,t:`${K.catN(o.cat)}<br>${K.esc(String(o.sum||'').slice(0,80))}`,go:()=>K.showOth(o)}));
  qs.forEach(q=>{if(isD(q.d))pts.push({lane:5,d:clip(q.d),c:'#E67E00',sym:'pin',sz:14,t:`${q.id} ${K.catN(q.cat)}<br>${K.esc(String(q.text||'').slice(0,90))}`,go:()=>K.showQ(q.id)})});
  pts.sort((a,b)=>(a.sev||0)-(b.sev||0));             /* CS 实心点画在最上层，不被同日的空心点盖住 */
  const ts=(x)=>+new Date(x+'T00:00:00');
  const all=[...bars.flatMap(b=>[b.s,b.e]),...pts.map(p=>p.d)].filter(Boolean).sort();
  if(!all.length){el.style.display='none';return}
  const pad=86400000*7,x0=ts(all[0])-pad,x1=ts(all[all.length-1])+pad;
  const laneY=(api,lane,sub,nsub)=>{const top=api.coord([x0,lane])[1],h=api.size([0,1])[1];return {y:top-h/2+4+(sub||0)*Math.max(4,(h-8)/(nsub||1)),h:Math.max(3,(h-8)/(nsub||1)-2)}};
  const nsub={2:Math.min(4,Math.max(1,(d.ae||[]).length)),3:Math.min(3,Math.max(1,(d.cm||[]).length))};
  K.chart(el,{grid:{left:70,right:16,top:6,bottom:28},
    tooltip:{trigger:'item',confine:true,formatter:p=>p.data&&p.data.t?p.data.t:''},
    xAxis:{type:'time',min:x0,max:x1,...K.axis,splitLine:{show:false}},
    yAxis:{type:'category',data:LANES,inverse:true,...K.axis,axisLabel:{color:'#64676B',fontSize:11},splitLine:{show:true,lineStyle:{color:'#F0F1F4'}}},
    dataZoom:[{type:'inside',xAxisIndex:0,filterMode:'weakFilter'}],
    series:[{type:'custom',renderItem:(params,api)=>{const b=bars[params.dataIndex];const a=api.coord([ts(b.s),b.lane]),z=api.coord([ts(b.e)+86400000,b.lane]);const L=laneY(api,b.lane,(b.sub||0)%(nsub[b.lane]||1),nsub[b.lane]);
        return {type:'rect',shape:{x:a[0],y:L.y,width:Math.max(3,z[0]-a[0]),height:L.h,r:2},style:{fill:b.c,stroke:b.bd||null,lineWidth:b.bd?1.5:0,opacity:b.open?.75:1}}},
      encode:{x:[0,1],y:2},data:bars.map(b=>({value:[ts(b.s),ts(b.e),b.lane],t:b.t})),z:2},
     {type:'scatter',data:pts.map(p=>({value:[ts(p.d),LANES[p.lane]],t:p.t,symbol:p.sym,symbolSize:p.sz,itemStyle:{color:p.sym==='emptyCircle'?'#fff':p.c,borderColor:p.c,borderWidth:1.5}})),z:3},
     {type:'line',data:[],markLine:{symbol:'none',silent:true,label:{fontSize:10,color:'#B86400'},lineStyle:{color:'#FF9900',type:'solid',width:1},data:[d.fd?{xAxis:ts(clip(d.fd)),label:{formatter:'D1'}}:null,d.ld?{xAxis:ts(clip(d.ld)),label:{formatter:'末次给药',color:'#64676B'},lineStyle:{color:'#C9CCD1'}}:null].filter(Boolean)}}]});
  const c=echarts.getInstanceByDom(el);c.off('click');c.on('click',p=>{const x=p.seriesIndex===0?bars[p.dataIndex]:p.seriesIndex===1?pts[p.dataIndex]:null;if(x&&x.go)x.go()})};   /* V6：给药/访视/AE/合并用药条也可下钻原始行 */
/* ---- 检验热力矩阵：行＝曾超出参考范围或判 CS 的指标（按最大偏离排序，最多 30 项），列＝访视（按日期）；
 * 色＝偏离参考范围的相对幅度（偏低蓝/范围内灰/偏高红，±100% 封顶），格内「CS」＝研究者判有临床意义。点格看该指标全程与原始行。 */
K.labDev=r=>{const v=r[2],lo=r[5],hi=r[6];if(v==null||isNaN(v))return null;if(hi!=null&&v>hi)return hi?Math.min(1,(v-hi)/Math.abs(hi)):1;if(lo!=null&&v<lo)return lo?-Math.min(1,(lo-v)/Math.abs(lo)):-1;return 0};
K.labHeat=(el,labs,{onPick}={})=>{if(!el||!window.echarts)return 0;
  const tests=Object.entries(labs).map(([t,rows])=>{const devs=rows.map(K.labDev).filter(x=>x!=null),cs=rows.some(r=>r[7]===2);return [t,rows,Math.max(0,...devs.map(Math.abs)),cs]})
    .filter(x=>x[2]>0||x[3]).sort((a,b)=>(b[3]-a[3])||(b[2]-a[2])).slice(0,30);
  if(!tests.length){el.style.display='none';return 0}
  const vis=[...new Map(tests.flatMap(x=>x[1]).filter(r=>r[1]).sort((a,b)=>String(a[0]).localeCompare(String(b[0]))).map(r=>[r[1],1])).keys()];
  const data=[];tests.forEach(([t,rows],yi)=>vis.forEach((v,xi)=>{const rs=rows.filter(r=>r[1]===v);if(!rs.length)return;
    const r=rs.reduce((a,b)=>Math.abs(K.labDev(b)||0)>Math.abs(K.labDev(a)||0)?b:a);const dv=K.labDev(r);
    data.push({value:[xi,yi,dv==null?0:dv],r,t,cs:rs.some(x=>x[7]===2),label:{color:Math.abs(dv||0)>0.45?'#fff':'#3A3D41'}})}));
  el.style.height=Math.max(160,40+tests.length*20)+'px';
  K.chart(el,{grid:{left:150,right:70,top:8,bottom:30},
    tooltip:{trigger:'item',formatter:p=>{const r=p.data.r;return `${K.esc(p.data.t)} · ${K.esc(r[1]||'')} ${K.esc(String(r[0]||'').slice(0,10))}<br><b>${K.esc(r[3]??'')} ${K.esc(r[4]||'')}</b>（参考 ${K.rng(r[5],r[6])}）${r[7]===2?' · CS':r[7]===1?' · NCS':''}${r[17]?' · '+r[17]+'级':''}`}},
    xAxis:{type:'category',data:vis,...K.axis,splitLine:{show:false},axisLabel:{color:'#64676B',fontSize:10,interval:0,rotate:vis.length>10?30:0}},
    yAxis:{type:'category',data:tests.map(x=>x[0]),inverse:true,...K.axis,axisLabel:{color:'#3A3D41',fontSize:11,width:140,overflow:'truncate'}},
    visualMap:{type:'continuous',min:-1,max:1,dimension:2,orient:'vertical',right:0,top:'middle',itemHeight:90,text:['偏高','偏低'],textStyle:{fontSize:10,color:'#64676B'},calculable:false,
      inRange:{color:['#2F6DA3','#9DBEDB','#EEF0F2','#F2B8A2','#B3261E']}},
    series:[{type:'heatmap',data,itemStyle:{borderColor:'#fff',borderWidth:2},label:{show:true,fontSize:9,color:'#fff',formatter:p=>p.data.cs?'CS':''},emphasis:{itemStyle:{borderColor:'#333',borderWidth:1}}}]});
  const c=echarts.getInstanceByDom(el);c.off('click');c.on('click',p=>{if(onPick&&p.data)onPick(p.data.t)});
  return tests.length};
/* ---- 受试者风险构成（中心页）：横向堆叠条，一行一名受试者；同一套类别顺序与颜色（状态色＝风险，蓝＝AE 身份） */
K.roster=(el,sids)=>{if(!el||!window.echarts)return;const Dd=D();
  const C=[['CS 未关联','#8B0000',s=>(K.lab||[]).filter(g=>g.sid===s&&g.risk==='CSX').length],['专项（需核实+）','#E67E00',s=>(Dd.others||[]).filter(o=>o.sid===s&&o.pr>=3).length],
    ['质疑','#E8C300',s=>(Dd.queries||[]).filter(q=>q.sid===s).length],['TEAE','#407AAA',s=>(Dd.aes||[]).filter(a=>a.sid===s&&a.te!==false).length],['SAE','#1F3B57',s=>(Dd.aes||[]).filter(a=>a.sid===s&&a.sae&&a.te!==false&&!a.dup).length]];   /* F4①：与总览「SAE 例次」同口径（TEAE、完全重复导出第 2 份起不计） */
  const rows=sids.map(s=>[s,C.map(c=>c[2](s))]).sort((a,b)=>b[1].slice(0,3).reduce((x,y)=>x+y,0)-a[1].slice(0,3).reduce((x,y)=>x+y,0)||b[1][3]-a[1][3]).slice(0,40);
  if(!rows.length){el.innerHTML='<div class="empty">本中心无已给药受试者</div>';return}
  el.style.height=Math.max(140,50+rows.length*18)+'px';
  K.chart(el,{grid:{left:70,right:20,top:26,bottom:20},legend:{top:0,itemWidth:10,itemHeight:10,textStyle:{fontSize:11,color:'#3A3D41'}},
    tooltip:{trigger:'axis',axisPointer:{type:'shadow'}},xAxis:{type:'value',minInterval:1,...K.axis},yAxis:{type:'category',data:rows.map(r=>r[0]),inverse:true,...K.axis},
    series:C.map((c,i)=>({name:c[0],type:'bar',stack:'r',barMaxWidth:12,itemStyle:{color:c[1],borderColor:'#fff',borderWidth:1},data:rows.map(r=>r[1][i]||null)}))});
  const ch=echarts.getInstanceByDom(el);ch.off('click');ch.on('click',p=>{location.href='subjects.html#s='+encodeURIComponent(p.name)})};
/* ---- KPI 数字短时计数到真值（康哲 CHART-04：从 0 起、不用随机数、终值写入 aria-label；减少动态时直接显示真值；只在首次载入时） */
K.countUpAll=root=>{if(K.RM)return;(root||document).querySelectorAll('.kpi .v,.facts .f b').forEach(el=>{const tn=[...el.childNodes].find(n=>n.nodeType===3&&/\d/.test(n.nodeValue));if(!tn||el.dataset.cu)return;
  const m=tn.nodeValue.match(/^(\s*)(\d+(?:\.\d+)?)(.*)$/s);if(!m)return;const end=parseFloat(m[2]),dec=(m[2].split('.')[1]||'').length;if(!(end>0))return;
  el.dataset.cu='1';el.setAttribute('aria-label',el.textContent.trim());const t0=performance.now(),dur=520;
  const step=now=>{const k=Math.min(1,(now-t0)/dur),e=1-Math.pow(1-k,3);tn.nodeValue=m[1]+(end*e).toFixed(dec)+m[3];if(k<1)requestAnimationFrame(step);else tn.nodeValue=m[1]+m[2]+m[3]};requestAnimationFrame(step)})};
if(typeof window.addEventListener==='function')window.addEventListener('load',()=>setTimeout(()=>K.countUpAll(),30));
/* ---- 信号聚合：同受试者 × 同日期 × 同类别 × 同表单 → 一组（风险排名） */
/* 检验项标题＝「指标 · 类别」→ 按类别聚合（指标进明细）；其余（专项/偏离…）标题本身就是类别 */
const catOf=o=>o.kind==='lab'?(o.title||'').replace(/^.*? · /,''):(o.title||'');
const itemOf=o=>o.kind==='lab'?(o.title||'').split(' · ')[0]:(String(o.x&&o.x.test||'')||String(o.why||'').slice(0,24));
K.groupKey=o=>[o.kind||'',o.sid||'',(o.x&&(o.x.d||((o.x.pts||[])[0]||[])[1]))||'',catOf(o),(o.x&&(o.x.sh||((o.x.pts||[])[0]||[])[7]))||''].join('|');
K.groupSig=list=>{const m=new Map();list.forEach(o=>{if(!o.sid){m.set(Symbol(),[o]);return}const k=K.groupKey(o);(m.get(k)||m.set(k,[]).get(k)).push(o)});
  return [...m.values()].map(g=>g.length===1?g[0]:{...g[0],group:g,score:Math.max(...g.map(x=>x.score||0)),
    title:`${catOf(g[0])} · ${g.length} 项`,why:[...new Set(g.map(itemOf).filter(Boolean))].slice(0,6).join('、')+(g.length>6?'…':''),
    open:()=>{const b=K.drawer(`${g[0].sid} · ${K.esc(catOf(g[0]))}`,`<div class="small muted mb">同一受试者同一日期同类信号 ${g.length} 项（已合并为一条风险项）</div>${g.map((x,i)=>`<div class="drow click" data-i="${i}" style="padding:7px 0;border-bottom:1px solid #F0F1F4"><b>${K.esc(itemOf(x))}</b> <span class="small muted">${K.esc(String(x.why||'').slice(0,90))}</span></div>`).join('')}<div class="rawg mt"></div>`);
      b.querySelectorAll('[data-i]').forEach(d=>d.onclick=()=>g[+d.dataset.i].open());
      const ev=g.flatMap(x=>x.x&&x.x.pts?x.x.pts.map(p=>[shKey(p[11],p[7]),p[8]]):x.x&&x.x.sh?[[shKey(x.x.wb,x.x.sh),x.x.row]]:[]);K.rawBox(b.querySelector('.rawg'),g[0].sid,ev)}})};
})();

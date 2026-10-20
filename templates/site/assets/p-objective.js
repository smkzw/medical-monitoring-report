K.init(()=>{
const D=KZ,T=KZT,app=document.getElementById('app'),H=K.hash();
const CF=K.cfg(),VL=K.VIS,D1I=VL.indexOf((CF.visits||{}).d1||'D1');
const SJ=T.subjects;const dosed=i=>SJ[i][3]===1;
const LRk={};D.labrows.forEach(g=>{LRk[g.sid+'|'+g.test]=g});
const vk=r=>VL[r[5]]+(r[5]===D1I&&r[16]===1||(r[17]&&/后/.test(r[17]))?'·后':'');
const ORDER=VL.filter(K.isAgg).flatMap(v=>[v,v+'·后']);
const AGG=r=>K.isAgg(VL[r[5]]); // 中心/全试验层面不含计划外/提前退出访视
const TH=[30,50];
// abnormal post counts per metric
const FX0=CF.fixedRanges||{};
// 指标专项规则：cfg.metricRules=[{match:regex,note,flags:[{on:'val'|'chg'|'pct'|'uln',op:'>='|'>'|'<='|'<',v,why}],lines:{val:[[y,label]],chg:[],pct:[]},uln:[k]}]
const MRF=id=>(CF.metricRules||[]).filter(x=>new RegExp(x.match).test(id));
const CMP=(op,a,b)=>a!=null&&(op==='>='?a>=b:op==='>'?a>b:op==='<='?a<=b:a<b);
const abn=m=>{const f=FX0[m.id];const s=new Set();(T.obs[m.id]||[]).forEach(r=>{const lo=f?f[0]:r[12],hi=f?f[1]:r[13];if(dosed(r[0])&&AGG(r)&&r[16]===1&&r[8]&&r[3]!=null&&((hi!=null&&r[3]>hi)||(lo!=null&&r[3]<lo)))s.add(r[0])});return s.size};
T.metrics.forEach(m=>m.nab=abn(m));
const groups=[...new Set(T.metrics.map(m=>m.group))];
app.innerHTML=`<div class="flex mb"><h1 style="font-size:18px">检验检查趋势</h1><span class="muted small">${T.metrics.length} 项定量指标${(T.qual&&T.qual.tests&&T.qual.tests.length)?' + 定性':''} · 仅给药参与者 · 基线按方案定义</span><span class="sp"></span>${(K.cfg().blind||{}).on?K.p('盲态合并','blu'):''}</div>
<div class="grid" style="grid-template-columns:230px 1fr;gap:14px;align-items:start">
 <div class="card" style="padding:8px 0;position:sticky;top:66px"><div style="padding:0 10px 6px"><input class="s" id="ms" placeholder="搜索指标" style="width:100%"></div><div class="subj-list" id="ml" style="max-height:calc(100vh - 150px)"></div></div>
 <div id="mn"></div></div>`;
let cur=H.m&&H.m.startsWith('q:')?{qual:H.m.slice(2),id:H.m}:T.metrics.find(m=>m.id===H.m)||T.metrics[0],mode=H.v||'val',hc=H.c||'';
function mlist(){const q=document.getElementById('ms').value.trim();
  document.getElementById('ml').innerHTML=groups.map(g=>{const ms=T.metrics.filter(m=>m.group===g&&(!q||m.label.includes(q)));if(!ms.length)return '';return `<div class="xs muted" style="padding:6px 10px 2px;font-weight:600">${g}</div>`+ms.map(m=>`<div class="it ${m.id===cur.id?'on':''}" data-id="${K.esc(m.id)}" style="padding:4px 10px"><span class="small" style="flex:1;color:var(--ink)">${K.esc(m.label.replace(/（(.*)）/,' $1'))}</span>${m.nab?`<span class="xs ${m.nab>=10?'':'faint'}" style="color:${m.nab>=10?'var(--brand-d)':''}" title="给药后超范围人数">${m.nab}</span>`:''}</div>`).join('')}).join('')+
   `<div class="xs muted" style="padding:6px 10px 2px;font-weight:600">定性（尿检/白带）</div>`+T.qual.tests.filter(t=>!q||t.includes(q)).map(t=>`<div class="it ${cur.qual===t?'on':''}" data-q="${K.esc(t)}" style="padding:4px 10px"><span class="small" style="color:var(--ink)">${K.esc(t)}</span></div>`).join('');
  document.querySelectorAll('#ml .it').forEach(it=>it.onclick=()=>{if(it.dataset.id){cur=T.metrics.find(m=>m.id===it.dataset.id)}else cur={qual:it.dataset.q,id:'q:'+it.dataset.q};mlist();draw()})}
document.getElementById('ms').oninput=mlist;mlist();
const mn=document.getElementById('mn');
function draw(){
  K.setHash({m:cur.id,v:mode,c:hc});
  if(cur.qual)return qual();
  const rows=(T.obs[cur.id]||[]).filter(r=>dosed(r[0])&&AGG(r)&&r[8]&&r[3]!=null);
  const unit=(cur.units[0]||[])[0]||'';
  const lo=K.median(rows.map(r=>r[12]).filter(x=>x!=null)),hi=K.median(rows.map(r=>r[13]).filter(x=>x!=null));
  const MR=MRF(cur.id);
  const vfn=r=>mode==='val'?r[3]:mode==='chg'?r[10]:r[11];
  const pts=rows.filter(r=>vfn(r)!=null);
  const cats=ORDER.filter(v=>pts.some(r=>vk(r)===v));
  const by=cats.map(v=>pts.filter(r=>vk(r)===v));
  const bx=by.map(a=>{const x=a.map(vfn);return x.length?[Math.min(...x),K.q(x,.25),K.q(x,.5),K.q(x,.75),Math.max(...x)]:[]});
  // subject-level worst post
  const subj={};rows.forEach(r=>{(subj[r[0]]=subj[r[0]]||{b:null,post:[]});if(r[9])subj[r[0]].b=r;if(r[16]===1)subj[r[0]].post.push(r)});
  (T.obs[cur.id]||[]).forEach(r=>{if(r[9]&&r[3]!=null&&subj[r[0]]&&!subj[r[0]].b)subj[r[0]].b=r});
  const FIX=FX0;
  const rg=r=>FIX[cur.id]||[r[12],r[13]];
  const cls=r=>{const [a,b]=rg(r);return b!=null&&r[3]>b?'H':a!=null&&r[3]<a?'L':'N'};
  // outliers: robust z of change within visit
  const outl=[];cats.forEach((v,i)=>{const a=by[i].filter(r=>r[16]===1&&r[10]!=null);if(a.length<8)return;const ch=a.map(r=>r[10]);const md=K.median(ch);const mad=K.median(ch.map(x=>Math.abs(x-md)))||1e-9;a.forEach(r=>{const z=.6745*(r[10]-md)/mad;if(Math.abs(z)>=3.5)outl.push({r,z,v})})});
  const thr=[];MR.forEach(x=>(x.flags||[]).forEach(f=>rows.forEach(r=>{if(r[16]!==1||thr.some(t=>t.r===r))return;const v=f.on==='chg'?r[10]:f.on==='pct'?r[11]:f.on==='uln'?(r[13]?r[3]/r[13]:null):r[3];if(CMP(f.op,v,f.v))thr.push({r,z:null,v:vk(r),why:f.why||(f.op+f.v)})})));
  const OL=[...thr,...outl.filter(o=>!thr.some(t=>t.r===o.r))].sort((a,b)=>(b.why?1:0)-(a.why?1:0)||Math.abs(b.z||0)-Math.abs(a.z||0));
  // ---- Shift（基线 → 基线后最差）：CTCAE 指标按等级；无 CTCAE 按较基线变化%阈值 ----
  const isCT=!!(window.CTC&&CTC.has(cur.id));
  const BS=T.base[cur.id]||{},ALL=T.obs[cur.id]||[];
  const bInfo=i=>{const b=BS[i];if(!b||b[1]==null)return null;const r=ALL.find(x=>x[0]==+i&&x[6]===b[4]&&x[7]===b[5]);return {v:b[1],l:r?r[12]:lo,u:r?r[13]:hi,date:b[0],type:b[3],r}};
  const gr=(v,l,u,b,isB)=>CTC.grade(cur.id,v,l,u,b,isB)||{g:0,t:''};
  const bcls=b=>{const f=FIX[cur.id];const a=f?f[0]:b.l,c=f?f[1]:b.u;return c!=null&&b.v>c?'H':a!=null&&b.v<a?'L':'N'};
  const SH=[];
  Object.keys(subj).forEach(i=>{const s=subj[i],b=bInfo(i);if(!b||!s.post.length)return;let o;
    if(isCT){const bg=gr(b.v,b.l,b.u,null,true);let w=null;s.post.forEach(r=>{const g=gr(r[3],r[12],r[13],b.v);if(!w||g.g>w.g.g||(g.g===w.g.g&&r[11]!=null&&Math.abs(r[11])>Math.abs(w.r[11]||0)))w={r,g}});
      const B=bg.g,W=w.g.g;o={bl:B,wl:W,term:w.g.t||bg.t,c1:W>=1&&W>B,c2:(B===0&&W>=3)||(B>=1&&W>=B+2),w:w.r}}
    else{let w=null;s.post.forEach(r=>{if(r[11]!=null&&(!w||Math.abs(r[11])>Math.abs(w[11])))w=r});if(!w)return;const p=Math.abs(w[11]);const W=p>=TH[1]?2:p>=TH[0]?1:0;
      o={bl:['L','N','H'].indexOf(bcls(b)),wl:W,c1:W>=1,c2:W>=2,w}}
    SH.push({i,sid:SJ[i][0],site:SJ[i][1],b,...o})});
  const RL=isCT?['0 级（正常）','1 级','2 级','3 级','4 级']:['&lt;LLN','正常','&gt;ULN'];
  const CL=isCT?['0','1','2','3','4']:[`&lt;${TH[0]}%`,`${TH[0]}–&lt;${TH[1]}%`,`≥${TH[1]}%`];
  const cellC=(a,b)=>isCT?((a===0&&b>=3)||(a>=1&&b>=a+2)?2:b>=1&&b>a?1:0):(b>=2?2:b>=1?1:0);
  const SHc=hc?SH.filter(x=>x.site===hc):SH;
  const shiftHTML=()=>`<div class="flex wrap" style="gap:6px;align-items:center"><b style="color:var(--ink)">基线 → 基线后最差</b>${isCT?K.p(CTC.label()+' 等级','blu'):K.p('无 '+CTC.label()+' 数值分级 · 按较基线变化%','line')}${hc?K.p(hc+' 中心','org'):''}
   ${isCT?'':`<span class="xs muted" style="margin-left:auto">阈值 ① <input id="th1" type="number" min="1" step="5" value="${TH[0]}" class="s" style="width:56px;padding:2px 4px">% ② <input id="th2" type="number" min="1" step="5" value="${TH[1]}" class="s" style="width:56px;padding:2px 4px">%</span>`}</div>
   <table class="t mt shift" style="text-align:center"><thead><tr><th style="text-align:left">基线 \\ 基线后最差</th>${CL.map(c=>`<th style="text-align:center">${c}</th>`).join('')}</tr></thead><tbody>${RL.map((rl,a)=>`<tr><td style="text-align:left"><b>${rl}</b></td>${CL.map((c,b)=>{const n=SHc.filter(x=>x.bl===a&&x.wl===b).length,na=SH.filter(x=>x.bl===a&&x.wl===b).length,k=cellC(a,b);
     return `<td class="${k&&n?'hit':''}" data-a="${a}" data-b="${b}" style="${k===2?'background:#F3E0E0;color:var(--risk)':k===1?'background:#FFF4E2;color:#B86400':''};${k&&n?'font-weight:700;cursor:pointer;text-decoration:underline dotted':''}">${n}${hc?`<span class="xs faint" style="font-weight:400">/${na}</span>`:''}</td>`}).join('')}</tr>`).join('')}</tbody></table>
   <div class="flex wrap mt" style="gap:6px">${[['c1','①',isCT?'基线正常→≥1级，或基线异常→升级≥1级':`|Δ%| ≥ ${TH[0]}%`,'org'],['c2','②',isCT?'基线正常→≥3级，或基线异常→升级≥2级':`|Δ%| ≥ ${TH[1]}%`,'red']].map(([k,n,t,c])=>{const m=SHc.filter(x=>x[k]).length;return `<span class="p ${c}" data-k="${k}" style="cursor:pointer" title="点击查看受试者">${n} ${t}：${m} 人${SHc.length?'（'+(m/SHc.length*100).toFixed(0)+'%）':''}</span>`}).join('')}<span class="xs faint">n=${SHc.length}${hc?' / 整体 '+SH.length:''} · 不含 USV / ET</span></div>`;
  // center stats：给药后个体均值（当前口径）均值漏斗 + 给药后超范围比例漏斗
  const inC=(i,s)=>!s||SJ[i][1]===s;
  const sMean=i=>{const a=subj[i].post.map(vfn).filter(x=>x!=null);return a.length?K.mean(a):null};
  const isAb=i=>subj[i].post.some(r=>cls(r)!=='N');
  const CEN=D.centers.filter(c=>c.dosed).map(c=>({site:c.site,name:c.name,ids:Object.keys(subj).filter(i=>SJ[i][1]===c.site)})).filter(c=>c.ids.length);
  const FM=K.funnel(CEN.map(c=>({site:c.site,v:c.ids.map(sMean).filter(x=>x!=null)})));
  const withPost=c=>c.ids.filter(i=>subj[i].post.length);
  const FP=K.funnelP(CEN.map(c=>{const w=withPost(c);return {site:c.site,x:w.filter(isAb).length,n:w.length}}));
  const C=CEN.map(c=>{const m=FM.rows.find(r=>r.site===c.site),p=FP.rows.find(r=>r.site===c.site);const flag=[];
    if(m&&m.flag)flag.push([`均值${m.z>0?'偏高':'偏低'}·${K.FL[m.flag][0]}`,m.flag]);if(p&&p.flag)flag.push([`超范围比例${p.z>0?'偏高':'偏低'}·${K.FL[p.flag][0]}`,p.flag]);
    return {site:c.site,name:c.name,n:c.ids.length,m,p,ab:p?p.x:0,np:p?p.n:0,pab:p?p.m:0,flag,sev:flag.some(f=>f[1]==='red')?2:flag.length?1:0}});
  const CN={};C.forEach(c=>CN[c.site]=c.name);
  const totAb=FP.mu;
  const ids=Object.keys(subj),cid=ids.filter(i=>inC(i,hc));
  const nAb=a=>a.filter(isAb).length,OLc=OL.filter(o=>inC(o.r[0],hc));
  const hcC=C.find(c=>c.site===hc);
  const modeL={val:'原值',chg:'较基线Δ',pct:'Δ%'}[mode];
  const kp=[K.kpiCS('给药参与者',cid.length,ids.length+' 人',{sel:!!hc,unit:'人',note:'选择中心后显示该中心值'}),
    K.kpiCS('给药后超范围',`${nAb(cid)}`,`${nAb(ids)} 人（${(totAb*100).toFixed(0)}%）`,{sel:!!hc,unit:`人${cid.length?' · '+(hcC?(hcC.pab*100).toFixed(0):(totAb*100).toFixed(0))+'%':''}`,flag:hcC&&hcC.p?K.flagPill(hcC.p):''}),
    K.kpiCS('离群 / 方案阈值',OLc.length,OL.length+' 条',{sel:!!hc,unit:'条'}),
    hc?K.kpiCS(`给药后均值（${modeL}）`,hcC&&hcC.m?K.fmt(hcC.m.m):'—',K.fmt(FM.mu),{sel:true,unit:unit&&mode!=='pct'?unit:mode==='pct'?'%':'',flag:hcC&&hcC.m?K.flagPill(hcC.m):''})
      :K.kpiCS('中心偏离提示',C.filter(c=>c.flag.length).length,'',{unit:'个中心',note:`其中明显偏离 ${C.filter(c=>c.sev===2).length} 个`})];
  mn.innerHTML=`<div class="card mb"><div class="flex wrap" style="gap:8px"><b style="font-size:16px;color:var(--ink)">${K.esc(cur.label)}</b>${K.p(unit,'line')}${K.p(cur.baseline.replace('规定基线：','基线 '),'blu')}${lo!=null||hi!=null?K.p(`参考 ${K.rng(lo,hi)}`,''):''}${FIX[cur.id]?K.p('分类阈值 '+K.rng(FIX[cur.id][0],FIX[cur.id][1]),'org'):''}${cur.note?`<span class="xs muted" title="${K.esc(cur.note)}">ⓘ 单位换算/口径</span>`:''}<span class="sp"></span><div class="seg" id="md"></div><span class="small muted">选择中心</span><select class="s" id="hc"><option value="">全部中心（整体）</option>${C.map(c=>`<option value="${c.site}" ${c.site===hc?'selected':''}>${c.site} ${K.esc(c.name)}</option>`).join('')}</select></div>
   <div class="kpis mt" style="margin-top:10px">${kp.join('')}</div></div>
  <div class="grid g12 mb"><div class="card"><div class="xs muted">按访视分布（${modeL}）· 线 = 中位数，色带 = 四分位间距，点 = 受试者，深红点 = 个体离群/方案阈值${hc?` · <b style="color:#E67E00">橙 = ${hc} 中心</b>，灰 = 整体；横轴 n = 中心/整体`:''} <span id="b1n" style="color:var(--risk)"></span></div><div class="chart" id="b1" style="height:300px"></div></div>
   <div class="card"><div id="sh">${shiftHTML()}</div>
   <div class="xs muted mt">点击着色单元格查看受试者；①含②。CS 判定与 AE 记录在明细中核对</div><div class="xs muted mt">各访视超范围比例${hc?`（实线 = ${hc} 中心，虚线 = 整体）`:''}</div><div class="chart" id="b3" style="height:150px"></div></div></div>
  <div class="card mb"><div class="xs muted">个体轨迹（研究日）· ${hc?`橙色加粗 = ${hc} 中心，其余淡化`:'选择中心后加粗显示该中心'} · 深红 = 离群/阈值受试者 · 点击线查看参与者</div><div class="chart" id="b2" style="height:260px"></div></div>
  <div class="card mb"><div class="sec-t" style="margin-top:0"><h2>中心偏离</h2><span class="muted small">漏斗图：中心值与整体比较，虚线 ±2SE = 需关注，点线 ±3SE = 明显偏离；n&lt;2 不判 · 点击中心切换选择</span></div>
   <div class="grid g12"><div><div class="xs muted">给药后个体均值（${modeL}）· 整体 ${K.fmt(FM.mu)} · n=${FM.N}</div><div class="chart" id="f1" style="height:260px"></div></div><div><div class="xs muted">给药后超范围比例 · 整体 ${(totAb*100).toFixed(0)}% · n=${FP.N}</div><div class="chart" id="f2" style="height:260px"></div></div></div></div>
  <div class="grid g2"><div class="card"><div class="sec-t" style="margin-top:0"><h2>受试者离群 / 方案阈值</h2><span class="muted small">${MR.map(x=>K.esc(x.note||'')).filter(Boolean).join('；')}${MR.some(x=>x.note)?' · ':''}同访视变化量稳健 z≥3.5${hc?` · 仅 ${hc} 中心`:''}</span></div><div id="ot"></div></div>
   <div class="card"><div class="sec-t" style="margin-top:0"><h2>中心对比</h2><span class="muted small">给药后均值 · 超范围比例（整体 ${(totAb*100).toFixed(0)}%）· 点击行选择中心</span></div><div id="ct"></div></div></div>`;
  K.seg(document.getElementById('md'),[['val','原值'],['chg','较基线Δ'],['pct','Δ%']],mode,v=>{mode=v;draw()});
  const pick=s=>{hc=hc===s?'':s;draw()};
  document.getElementById('hc').onchange=e=>{hc=e.target.value;draw()};
  const ml=[];if(mode==='val'){if(lo!=null)ml.push({yAxis:lo,label:{formatter:'LLN'}});if(hi!=null)ml.push({yAxis:hi,label:{formatter:'ULN'}});MR.forEach(x=>{((x.lines||{}).val||[]).forEach(([y,l])=>ml.push({yAxis:y,label:{formatter:l||String(y)},lineStyle:{color:'#8B0000'}}));if(hi)(x.uln||[]).forEach(k=>ml.push({yAxis:k*hi,label:{formatter:k+'×ULN'},lineStyle:{color:'#8B0000'}}))})}else{ml.push({yAxis:0});MR.forEach(x=>((x.lines||{})[mode]||[]).forEach(([y,l])=>ml.push({yAxis:y,label:{formatter:l||String(y)},lineStyle:{color:'#8B0000'}})))}
  const olSet=new Set(OL.map(o=>o.r));const go=sid=>location.href='subjects.html#s='+sid+'&t=lab';
  const P=a=>a.map(r=>({v:vfn(r),sid:SJ[r[0]][0]}));
  const BRo=K.yb(pts.map(vfn),ml.map(m=>m.yAxis));
  const olPts={type:'scatter',z:8,symbolSize:6,data:pts.filter(r=>olSet.has(r)&&(!hc||SJ[r[0]][1]===hc)).map(r=>({value:[cats.indexOf(vk(r))+K.jit(SJ[r[0]][0]),K.ycl(BRo,vfn(r))],sid:SJ[r[0]][0],raw:vfn(r),vis:vk(r),...K.ysym(BRo,vfn(r))})),itemStyle:{color:'#8B0000',opacity:.85}};
  document.getElementById('b1n').innerHTML=BRo.on?'远端异常值以断轴 / 边缘三角显示（悬停看原值，点击断轴可展开）':'';
  K.distLine('#b1',{yr:BRo,V:cats,all:by.map(P),sel:hc?by.map(a=>P(a.filter(r=>SJ[r[0]][1]===hc))):null,ml,selName:hc+' 中心',allName:'整体',left:50,onClick:go,extra:[olPts]});
  // spaghetti by study day
  const ser={};pts.forEach(r=>(ser[r[0]]=ser[r[0]]||[]).push(r));
  const oS=new Set(OL.map(o=>o.r[0]));
  K.chart('#b2',{grid:{left:48,right:44,top:10,bottom:26},tooltip:{trigger:'item',formatter:p=>`${p.seriesName} D${p.value[0]>=0?Math.floor(p.value[0])+1:p.value[0]} ${K.fmt(p.data&&p.data.raw!=null?p.data.raw:p.value[1])}`},xAxis:{type:'value',...K.axis,axisLabel:{formatter:v=>'D'+(v>=0?v+1:v),color:'#64676B'}},yAxis:{type:'value',scale:true,...K.axis,...K.ybOpt(BRo)},
   series:Object.entries(ser).map(([i,a])=>{const h=hc&&SJ[i][1]===hc,o=oS.has(+i),dim=hc&&!h;const col=h?'#FF9900':o?'#8B0000':dim?'#D5D8DD':'#E6C9A0';a.sort((x,y)=>x[2]-y[2]);return {type:'line',name:SJ[i][0],data:a.map(r=>({value:[r[2]+(r[16]===1&&r[5]===3?.3:0),K.ycl(BRo,vfn(r))],raw:vfn(r),...K.ysym(BRo,vfn(r))})),symbolSize:h?5:o&&!dim?4:0,lineStyle:{width:h?2.4:o&&!dim?1.3:1,color:col,opacity:h?.95:dim?(o?.45:.3):o?.9:.35},itemStyle:{color:col},z:h?4:o?3:1,emphasis:{focus:'series'}}}).concat([{type:'line',data:[],markLine:{symbol:'none',silent:true,lineStyle:{color:'#9A9DA3',type:'dashed'},label:{fontSize:10},data:[...ml,{xAxis:0,lineStyle:{color:'#407AAA',type:'solid'},label:{formatter:'D1'}}]}}])}).off('click');
  echarts.getInstanceByDom(document.getElementById('b2')).on('click',p=>{if(p.seriesName&&/^\d{5}$/.test(p.seriesName))go(p.seriesName)});
  // b3: % abnormal by visit（折线；选中中心实线，整体虚线）
  const pr=(a,k)=>a.length?+(a.filter(r=>cls(r)===k).length/a.length*100).toFixed(1):null;
  const b3s=[];[['H','>ULN','#8B0000'],['L','<LLN','#407AAA']].forEach(([k,n,c])=>{
    b3s.push({type:'line',name:(hc?'整体 ':'')+n,data:by.map(a=>pr(a,k)),symbol:'circle',symbolSize:hc?3:5,connectNulls:true,lineStyle:{color:c,width:hc?1.2:2,type:hc?'dashed':'solid',opacity:hc?.55:1},itemStyle:{color:c,opacity:hc?.55:1}});
    if(hc)b3s.push({type:'line',name:hc+' '+n,data:by.map(a=>pr(a.filter(r=>SJ[r[0]][1]===hc),k)),symbol:'circle',symbolSize:6,connectNulls:true,lineStyle:{color:c,width:2.6},itemStyle:{color:c}})});
  K.chart('#b3',{grid:{left:36,right:10,top:20,bottom:22},tooltip:{trigger:'axis',valueFormatter:v=>v==null?'—':v+'%'},legend:{top:0,itemWidth:12,itemHeight:6,textStyle:{fontSize:9}},xAxis:{type:'category',data:cats,...K.axis,axisLabel:{fontSize:9,color:'#64676B'}},yAxis:{type:'value',min:0,...K.axis,axisLabel:{formatter:'{value}%',color:'#64676B'}},series:b3s});
  // funnels
  K.funnelChart('#f1',FM,{hc,names:CN,onPick:pick,left:52});
  K.funnelChart('#f2',FP,{hc,names:CN,onPick:pick,kind:'p',fmt:v=>(v*100).toFixed(0)+'%',ymin:0,ymax:1});
  // ---- 受试者列表弹窗 + 个体历史 ----
  const LBL=cur.label,UN=unit;
  const showList=(list,title)=>{
    const lv=x=>isCT?`${x.wl} 级${x.term?' <span class="xs muted">'+K.esc(x.term)+'</span>':''}`:K.pct(x.w[11]);
    const b=K.drawer(`${K.esc(LBL)} · ${title}`,`<div class="xs muted mb">${list.length} 人 · 点击受试者展开整个研究过程的变化图与明细（含 USV / ET）</div><table class="t" id="dl"><thead><tr><th>受试者</th><th>基线</th><th>基线后最差</th><th>${isCT?'最差等级':'Δ%'}</th><th>判定/关联</th></tr></thead><tbody>${list.map((x,j)=>{const g=LRk[x.sid+'|'+LBL];return `<tr class="click" data-j="${j}"><td><b style="color:var(--blue)">▸ ${x.sid}</b> <span class="xs faint">${x.site}</span></td><td>${K.fmt(x.b.v)} <span class="xs faint">${isCT?gr(x.b.v,x.b.l,x.b.u,null,true).g+'级':RL[x.bl]}</span></td><td>${K.fmt(x.w[3])} <span class="xs faint">${UN}</span> ${K.p(vk(x.w),'blu')}</td><td>${lv(x)}</td><td>${g?K.risk(g.risk):''}</td></tr>`}).join('')}</tbody></table>`,isCT?CTC.label()+' · 基线按方案定义':'较基线变化% · 阈值 '+TH.join(' / ')+'%');
    b.querySelectorAll('#dl tr[data-j]').forEach(tr=>tr.onclick=()=>{const nx=tr.nextElementSibling;if(nx&&nx.classList.contains('dx')){nx.remove();tr.querySelector('b').innerHTML='▸ '+list[+tr.dataset.j].sid;return}
      tr.querySelector('b').innerHTML='▾ '+list[+tr.dataset.j].sid;const x=list[+tr.dataset.j];const d=document.createElement('tr');d.className='dx';d.innerHTML=`<td colspan="5" style="background:#FAFAFB;padding:8px"><div class="chart" style="height:220px"></div><div class="hx"></div><div class="mt"><a class="p click blu" href="subjects.html#s=${x.sid}&t=lab">参与者资料 →</a></div></td>`;tr.after(d);hist(x,d.querySelector('.chart'),d.querySelector('.hx'))})};
  const hist=(x,el,tb)=>{const rs=ALL.filter(r=>r[0]==+x.i&&r[3]!=null).sort((a,b)=>a[2]-b[2]||a[5]-b[5]);const g=LRk[x.sid+'|'+LBL];const csm={};if(g)g.pts.forEach(p=>csm[p[7]+'|'+p[8]]=p);
    const G=r=>isCT?gr(r[3],r[12],r[13],r[9]?null:x.b.v,!!r[9]).g:null;const GC=['#9A9DA3','#FFCC00','#FF9900','#8B0000','#5A0000'];
    const l0=rs.find(r=>r[12]!=null),u0=rs.find(r=>r[13]!=null);const ml=[];if(l0)ml.push({yAxis:l0[12],label:{formatter:'LLN'}});if(u0)ml.push({yAxis:u0[13],label:{formatter:'ULN'}});MR.forEach(m=>((m.lines||{}).val||[]).forEach(([y,l])=>ml.push({yAxis:y,label:{formatter:l||String(y)},lineStyle:{color:'#8B0000'}})));
    ml.push({yAxis:x.b.v,label:{formatter:'基线'},lineStyle:{color:'#407AAA',type:'dotted'}});
    K.chart(el,{grid:{left:48,right:46,top:14,bottom:28},tooltip:{trigger:'item',formatter:p=>{const r=p.data.r;return `${VL[r[5]]}${r[17]?' '+K.esc(r[17]):''} · ${r[1]}<br>${K.esc(r[14])} ${K.esc(r[15]||'')}${r[10]!=null?' · Δ '+(r[10]>0?'+':'')+K.fmt(r[10])+'（'+K.pct(r[11])+'）':''}${isCT?'<br>CTCAE '+G(r)+' 级':''}`}},
      xAxis:{type:'value',...K.axis,axisLabel:{color:'#64676B',formatter:v=>'D'+(v>=0?v+1:v)}},yAxis:{type:'value',scale:true,...K.axis},
      series:[{type:'line',data:rs.map(r=>({value:[r[2],r[3]],r,itemStyle:{color:isCT?GC[Math.min(4,G(r))]:(r[9]?'#407AAA':'#FF9900')},symbolSize:r===x.w?11:7,symbol:!K.isAgg(VL[r[5]])?'diamond':'circle'})),lineStyle:{color:'#C9CCD1'},markLine:{symbol:'none',silent:true,lineStyle:{color:'#9A9DA3',type:'dashed'},label:{fontSize:10,position:'insideEndTop'},data:[...ml,{xAxis:0,lineStyle:{color:'#407AAA',type:'solid'},label:{formatter:'D1'}}]}}]});
    tb.innerHTML=`<table class="t mt" style="font-size:12px"><thead><tr><th>访视</th><th>日期</th><th>研究日</th><th>结果</th><th>参考范围</th><th>Δ / Δ%</th>${isCT?'<th>分级</th>':''}<th>CS 判定</th></tr></thead><tbody>${rs.map(r=>{const p=csm[r[6]+'|'+r[7]];const isB=r[6]===x.b.r?.[6]&&r[7]===x.b.r?.[7];return `<tr style="${r===x.w?'background:#FFF4E2':''}"><td>${K.p(VL[r[5]]+(r[17]&&/后/.test(r[17])?'·后':''),r[5]>=9?'line':'blu')}${isB?' '+K.p('基线','blu'):''}${r===x.w?' '+K.p('最差','org'):''}</td><td class="xs">${r[1]}</td><td class="xs">D${r[2]>=0?r[2]+1:r[2]}</td><td><b>${K.esc(r[14])}</b> <span class="xs faint">${K.esc(r[15]||'')}</span></td><td class="xs muted">${r[12]!=null||r[13]!=null?K.fmt(r[12])+'–'+K.fmt(r[13]):'—'}</td><td class="xs">${r[10]!=null?(r[10]>0?'+':'')+K.fmt(r[10])+' · '+K.pct(r[11]):'—'}</td>${isCT?`<td>${G(r)?K.p(G(r)+'级',G(r)>=3?'red':G(r)>=2?'org':'yel'):'<span class="faint">0</span>'}</td>`:''}<td>${p?K.clin(p[5]):''}</td></tr>`}).join('')}</tbody></table>`};
  const wire=()=>{document.querySelectorAll('#sh td.hit').forEach(td=>td.onclick=()=>{const a=+td.dataset.a,b=+td.dataset.b;showList(SHc.filter(x=>x.bl===a&&x.wl===b),`基线 ${RL[a].replace(/&lt;/g,'<').replace(/&gt;/g,'>')} → 最差 ${CL[b].replace(/&lt;/g,'<')}`)});
    document.querySelectorAll('#sh [data-k]').forEach(p=>p.onclick=()=>showList(SHc.filter(x=>x[p.dataset.k]),p.dataset.k==='c1'?'① 标准':'② 标准'));
    ['th1','th2'].forEach((id,k)=>{const e=document.getElementById(id);if(e)e.onchange=()=>{const v=+e.value;if(v>0){TH[k]=v;if(TH[1]<TH[0])TH[1]=TH[0];draw()}}})};
  wire();
  // tables
  K.table(document.getElementById('ot'),{rows:OLc,pageSize:12,h:'360px',onRow:o=>go(SJ[o.r[0]][0]),cols:[
    {k:'sid',t:'受试者',s:o=>SJ[o.r[0]][0],f:o=>`<b style="color:var(--blue)">${SJ[o.r[0]][0]}</b> <span class="faint xs">${SJ[o.r[0]][1]}</span>`},{k:'v',t:'访视',f:o=>K.p(o.v,'blu')},
    {k:'val',t:'值',s:o=>o.r[3],f:o=>`<b>${K.esc(o.r[14])}</b> <span class="xs faint">${K.esc(o.r[15]||'')}</span>`},{k:'chg',t:'Δ / Δ%',s:o=>o.r[10],f:o=>`${o.r[10]!=null?(o.r[10]>0?'+':'')+K.fmt(o.r[10]):'—'} <span class="xs muted">${K.pct(o.r[11])}</span>`},
    {k:'why',t:'依据',s:o=>o.why?1e9:Math.abs(o.z||0),f:o=>o.why?K.p(o.why,'red'):K.p('z '+(o.z>0?'+':'')+o.z.toFixed(1),'yel')},
    {k:'lr',t:'判定/关联',ns:1,f:o=>{const g=LRk[SJ[o.r[0]][0]+'|'+cur.label];return g?K.risk(g.risk):''}}]});
  K.table(document.getElementById('ct'),{rows:C.slice().sort((a,b)=>(b.site===hc)-(a.site===hc)||b.sev-a.sev||b.flag.length-a.flag.length||b.pab-a.pab),pageSize:12,h:'360px',onRow:c=>pick(c.site),cols:[{k:'site',t:'中心',f:c=>`<b style="${c.site===hc?'color:#E67E00':''}">${c.site}</b> <span class="xs muted">${K.esc(c.name.slice(0,10))}</span>`},{k:'n',t:'n'},{k:'mm',t:'给药后均值',s:c=>c.m?c.m.m:-1e9,f:c=>c.m?K.fmt(c.m.m):'—'},{k:'pab',t:'超范围',f:c=>`<div class="flex" style="gap:6px"><div class="bar-in" style="width:60px"><i style="width:${c.pab*100}%;background:${c.p&&c.p.flag==='red'&&c.p.z>0?'#8B0000':'#FF9900'}"></i></div><span class="xs">${c.ab}/${c.np}</span></div>`},{k:'flag',t:'提示',s:c=>c.sev*10+c.flag.length,f:c=>c.flag.map(f=>K.p(f[0],f[1])).join(' ')}]});
}
function qual(){
  const t=cur.qual;const rows=(T.qual.obs[t]||[]).filter(r=>dosed(r[0]));
  const norm=v=>{v=String(v||'').replace(/\s/g,'');if(/清洁度|^[ⅠⅡⅢⅣIV]+[度°+]?$/.test(v)){const m=v.match(/Ⅳ|IV|Ⅲ|III|Ⅱ|II|Ⅰ|I/);return m?{Ⅰ:'Ⅰ',I:'Ⅰ',Ⅱ:'Ⅱ',II:'Ⅱ',Ⅲ:'Ⅲ',III:'Ⅲ',Ⅳ:'Ⅳ',IV:'Ⅳ'}[m[0]]:'其他'}
    if(/^(阴性|-|未检出|未见|未找到|未测出|未查见|未检到|无|Normal|normal|Normai|正常|阴性（-）|阴性\(-\)|阴性（-\)|未检出霉菌|未见滴虫|0|0\.00)$/.test(v))return '阴性';
    if(/4\+/.test(v))return '4+';if(/3\+|\+\+\+/.test(v))return '3+';if(/2\+|\+\+/.test(v))return '2+';if(/±|\+-|\+—|弱阳|微量|Trace|TRACE|0\.1|0\.2|0\.3/.test(v))return '±';if(/1\+|\+|阳性|检出|查见|找到|查到|偶见|少许/.test(v))return '1+';return '其他'};
  const L=/清洁度/.test(t)?['Ⅰ','Ⅱ','Ⅲ','Ⅳ','其他']:['阴性','±','1+','2+','3+','4+','其他'];const COL=/清洁度/.test(t)?['#DCE9C8','#FFE7B8','#FF9900','#8B0000','#D5D8DD']:['#DCE9C8','#FFF3D1','#FFCC00','#FF9900','#8B0000','#5A0000','#D5D8DD'];
  const vs=VL.map((_,i)=>i).filter(i=>rows.some(r=>r[2]===i));
  const cnt=vs.map(i=>{const a=rows.filter(r=>r[2]===i);return L.map(l=>a.filter(r=>norm(r[3])===l).length)});
  const subj={};rows.forEach(r=>{(subj[r[0]]=subj[r[0]]||[]).push(r)});
  const rk=l=>L.indexOf(l);
  const inc=Object.entries(subj).map(([i,a])=>{const pre=a.filter(r=>r[2]<=D1I),post=a.filter(r=>r[2]>D1I);const b=Math.max(-1,...pre.map(r=>rk(norm(r[3]))).filter(x=>x<L.length-1));const w=post.reduce((m,r)=>{const k=rk(norm(r[3]));return k<L.length-1&&k>m.k?{k,r}:m},{k:-1});return {i,b,w}}).filter(x=>x.w.k>=Math.max(2,x.b+2));
  mn.innerHTML=`<div class="card mb"><div class="flex"><b style="font-size:16px;color:var(--ink)">${K.esc(t)}</b>${K.p('定性','line')}<span class="xs muted">原始写法已归一（如 “80(2+)”“阳性（2+）”→2+）${CF.qualNote?'；'+K.esc(CF.qualNote):''}</span></div><div class="chart" id="q1" style="height:300px"></div></div>
  <div class="card"><div class="sec-t" style="margin-top:0"><h2>给药后较基线升高 ≥2 级</h2><span class="muted small">${inc.length} 人</span></div><div id="qt"></div></div>`;
  K.chart('#q1',{grid:{left:40,right:16,top:28,bottom:24},legend:{top:0,itemWidth:10,itemHeight:8,textStyle:{fontSize:10}},tooltip:{trigger:'axis'},xAxis:{type:'category',data:vs.map(i=>VL[i]),...K.axis},yAxis:{type:'value',...K.axis},series:L.map((l,j)=>({type:'bar',stack:'a',name:l,data:cnt.map(c=>c[j]),itemStyle:{color:COL[j]},barWidth:22}))});
  K.table(document.getElementById('qt'),{rows:inc,noPage:true,max:false,onRow:x=>location.href='subjects.html#s='+SJ[x.i][0]+'&t=lab',cols:[{k:'i',t:'受试者',f:x=>`<b style="color:var(--blue)">${SJ[x.i][0]}</b>`},{k:'b',t:'基线最高',f:x=>x.b>=0?L[x.b]:'—'},{k:'w',t:'给药后最高',f:x=>`${K.p(L[x.w.k],x.w.k>=4?'red':'org')} ${K.p(VL[x.w.r[2]],'blu')} <span class="xs faint">${x.w.r[1]} · ${K.esc(x.w.r[3])}</span>`},{k:'lr',t:'判定/关联',ns:1,f:x=>{const g=LRk[SJ[x.i][0]+'|'+t];return g?K.risk(g.risk)+' '+K.ctxTags(g.ctx):''}}]});
}
draw();
});

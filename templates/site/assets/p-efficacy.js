K.init(()=>{
const D=KZ,app=document.getElementById('app'),H=K.hash();
/* KZ.eff（engine 按方案终点生成，不在前端硬编码）:
   metrics:[{id,label,unit,kind:'continuous'|'ordinal',visits:[..],keyVisit,refLines:[[y,label]],categories:[[v,label]],note,clip,kpi}]
   data:[{sid,site,v:{metricId:{visit:value}}}]  anomalies:[{sid,site,k,c,v,t,st,rec:[[label,cls]]}]  rulesText */
const EF=D.eff||{metrics:[],data:[],anomalies:[]},CF=K.cfg(),BLD=CF.blind||{};
const E=EF.data||[];
const M=(EF.metrics||[]).map(m=>[m.id,m.label,m.unit||'',m.kind||'continuous',m,m.note||'']);
const val=(e,m,v)=>{const x=((e.v||{})[m[0]]||{})[v];return x==null?null:x};
const visits=m=>m[4].visits||[];
const AN=(EF.anomalies||[]).slice();
const KV=m=>m[4].keyVisit||visits(m)[visits(m).length-1];
/* KPIs + 中心对比 */
const CN={};D.centers.forEach(c=>CN[c.site]=c.name);
const clipOf=m=>m[4].clip!=null?m[4].clip:null;
const atV=(m,v,site)=>E.filter(e=>!site||e.site===site).map(e=>val(e,m,v)).filter(x=>x!=null);
const funnelOf=(m,v)=>{const cl=clipOf(m);return K.funnel(D.centers.filter(c=>c.dosed).map(c=>({site:c.site,v:atV(m,v,c.site).map(x=>cl!=null?Math.min(x,cl):x)})))};
const kp=(M.filter(m=>m[4].kpi).length?M.filter(m=>m[4].kpi):M).slice(0,6);
const fmtM=(m,x)=>x==null?'—':m[4].signed?(x>0?'+':'')+K.fmt(x):m[2]==='%'?K.pct(x):K.fmt(x);
app.innerHTML=`<div class="flex mb"><h1 style="font-size:18px">有效性趋势</h1><span class="muted small">${M.map(m=>K.esc(m[1])).join(' · ')}</span><span class="sp"></span>${BLD.on?K.p('盲态汇总 · 不分组','blu'):''}${(BLD.hidden||[]).length?K.p(BLD.hidden.map(K.esc).join(' / ')+' 按约定不展示','line'):''}</div>
<div class="kpis mb" id="kp"></div>
<div class="card mb"><div class="tbar"><div class="chips" id="mc"></div><span class="sp"></span><span class="small muted">选择中心</span><select class="s" id="cs"><option value="">全部中心（整体）</option>${D.centers.filter(c=>c.dosed).map(c=>`<option value="${c.site}">${c.site} ${K.esc(c.name)}</option>`).join('')}</select></div>
 <div class="dev" id="dv"></div>
 <div class="grid g12"><div><div class="xs muted" id="t1"></div><div class="chart" id="c1" style="height:310px"></div></div><div><div class="xs muted" id="t2"></div><div class="chart" id="c2" style="height:310px"></div></div></div>
 <div id="w3"><div class="xs muted mt" id="t3"></div><div class="chart" id="c3" style="height:260px"></div></div></div>
<div class="card"><div class="sec-t" style="margin-top:0"><h2>受试者层面异常</h2><span class="muted small">${K.esc(EF.rulesText||'规则见「审阅要点」')}</span></div><div class="tbar"><div class="chips" id="ac"></div></div><div id="at"></div></div>`;
let cur=M.find(m=>m[0]===H.m)||M[0],hc=H.c||'';
if(!M.length){document.getElementById('kp').innerHTML='<div class="card empty">未配置有效性指标</div>';return}
const csel=document.getElementById('cs');
const pick=s=>{hc=hc===s?'':s;csel.value=hc;draw()};
K.chips(document.getElementById('mc'),M.map(m=>[m[0],m[1]]),v=>{cur=M.find(m=>m[0]===v)||M[0];draw()},{all:null,value:cur[0]});
csel.value=hc;csel.onchange=e=>{hc=e.target.value;draw()};
function kpis(){
  document.getElementById('kp').innerHTML=kp.map(m=>{const kv=KV(m),a=atV(m,kv),c=hc?atV(m,kv,hc):a;const F=hc?funnelOf(m,kv):null,r=F&&F.rows.find(x=>x.site===hc);
    return K.kpiCS(`${m[1]} · ${kv} 中位`,c.length?fmtM(m,K.median(c)):'—',`${fmtM(m,K.median(a))} · n=${a.length}`,{sel:!!hc,unit:`${m[2]==='%'?'':m[2]+' · '}n=${c.length}`,flag:r?K.flagPill(r):'',note:'选择中心后显示该中心值'})}).join('');
}
function draw(){
  K.setHash({m:cur[0],c:hc});kpis();
  const V=visits(cur),cl=clipOf(cur);
  const pts=site=>V.map(v=>E.filter(e=>!site||e.site===site).map(e=>({v:val(e,cur,v),sid:e.sid})).filter(p=>p.v!=null));
  const lastV=KV(cur);
  const F=funnelOf(cur,lastV),fr=F.rows.filter(r=>r.flag).sort((a,b)=>Math.abs(b.z)-Math.abs(a.z));
  document.getElementById('dv').innerHTML=`<b>${cur[1]} · ${lastV} 中心偏离：</b>${fr.length?fr.map(r=>`<span class="p ${r.flag}" style="cursor:pointer" data-site="${r.site}" title="${K.esc(CN[r.site]||'')}">${r.site} ${K.FL[r.flag][0]} · 均值 ${fmtM(cur,r.m)}（n=${r.n}）</span>`).join(''):'<span>无中心超出 ±2SE</span>'}<span class="faint">整体均值 ${fmtM(cur,F.mu)} · n=${F.N}${cl!=null?' · 按 '+cl+' 截断后计算':''}</span>`;
  document.querySelectorAll('#dv [data-site]').forEach(x=>x.onclick=()=>pick(x.dataset.site));
  const ml=(cur[4].refLines||[]).map(([y,l])=>({yAxis:y,label:l?{formatter:l}:undefined}));
  const go=sid=>location.href='subjects.html#s='+sid+'&t=eff';
  const all=pts(''),sel=hc?pts(hc):null;
  const ORD=cur[3]==='ordinal';const BR=ORD?null:K.yb(all.flat().map(p=>p.v),ml.map(m=>m.yAxis));
  if(ORD){
    const CT=cur[4].categories||[...new Set(all.flat().map(p=>p.v))].sort((a,b)=>a-b).map(v=>[v,String(v)]);const cat=CT.map(c=>c[0]),lab=CT.map(c=>c[1]);const li=V.indexOf(lastV)>=0?V.indexOf(lastV):V.length-1;all[0]=all[li];if(sel)sel[0]=sel[li];
    const dist=a=>cat.map(k=>a.length?a.filter(p=>p.v===k).length/a.length*100:0);
    document.getElementById('t1').innerHTML=`<b style="color:var(--ink)">${K.esc(cur[1])} · ${lastV} 分布</b> · 有序分类，按各等级占比展示${hc?` · 橙 = ${hc} 中心（n=${sel[0].length}），灰 = 整体（n=${all[0].length}）`:` · n=${all[0].length}`}`;
    const ser=[{type:'bar',name:'整体',data:dist(all[0]),barGap:'10%',itemStyle:{color:hc?'#D5D8DD':'#FF9900'},barMaxWidth:hc?18:34}];
    if(hc)ser.push({type:'bar',name:hc+' 中心',data:dist(sel[0]),itemStyle:{color:'#FF9900'},barMaxWidth:18});
    K.chart('#c1',{grid:{left:40,right:16,top:hc?26:16,bottom:40},legend:hc?{top:0,right:0,itemWidth:10,itemHeight:8,textStyle:{fontSize:10}}:undefined,tooltip:{trigger:'axis',valueFormatter:v=>v.toFixed(1)+'%'},
      xAxis:{type:'category',data:lab,...K.axis,axisLabel:{fontSize:9,interval:0,color:'#64676B',formatter:v=>v.replace(' ','\n')}},yAxis:{type:'value',...K.axis,axisLabel:{color:'#64676B',formatter:'{value}%'}},series:ser});
  }else{
    document.getElementById('t1').innerHTML=`<b style="color:var(--ink)">${cur[1]}</b> · 按访视：线 = 中位数，色带 = 四分位间距，点 = 受试者 · ${cur[5]}${hc?` · <b style="color:#E67E00">橙 = ${hc} 中心</b>，灰 = 整体；横轴 n = 中心/整体`:''}`;
    if(BR&&BR.on)document.getElementById('t1').innerHTML+=` · <span style="color:var(--risk)">远端异常值以断轴 / 边缘三角显示（悬停看原值，点击断轴可展开）</span>`;
    K.distLine('#c1',{V,all,sel,clip:null,yr:BR,ml,selName:hc?hc+' 中心':'',allName:'整体',fmt:v=>fmtM(cur,v),onClick:go});
  }
  document.getElementById('t2').innerHTML=`<b style="color:var(--ink)">中心偏离 · ${lastV} 均值漏斗图</b> · 实线 = 整体均值，虚线 = ±2SE（需关注），点线 = ±3SE（明显偏离）· 点击中心切换选择`;
  K.funnelChart('#c2',F,{hc,fmt:v=>fmtM(cur,v),names:CN,onPick:pick});
  const w3=document.getElementById('w3');w3.style.display=ORD?'none':'';
  if(ORD)return;
  document.getElementById('t3').innerHTML=`<b style="color:var(--ink)">个体轨迹</b> · ${hc?`橙色加粗 = ${hc} 中心，其余淡化`:'选择中心后加粗显示该中心'} · 深红 = 异常列表受试者 · 点击线进入参与者资料`;
  const anS=new Set(AN.filter(a=>a.c==='red'||a.c==='org').map(a=>a.sid));
  K.chart('#c3',{grid:{left:44,right:20,top:12,bottom:24},tooltip:{trigger:'item',formatter:p=>`${p.seriesName} · ${V[p.dataIndex]||''} ${fmtM(cur,p.data&&p.data.raw!=null?p.data.raw:p.value)}`},xAxis:{type:'category',data:V,...K.axis,boundaryGap:false},yAxis:{type:'value',scale:true,...K.axis,...K.ybOpt(BR)},
   series:E.map(e=>{const h=hc&&e.site===hc,a=anS.has(e.sid),dim=hc&&!h;const col=h?'#FF9900':a?'#8B0000':dim?'#D5D8DD':'#E6C9A0';return {type:'line',name:e.sid,data:V.map(v=>{const x=val(e,cur,v);return x==null?null:{value:K.ycl(BR,x),raw:x,...K.ysym(BR,x)}}),connectNulls:true,symbol:'circle',symbolSize:h?5:a&&!dim?4:0,lineStyle:{width:h?2.4:a&&!dim?1.4:1,color:col,opacity:h?.95:dim?(a?.5:.3):a?.9:.45},itemStyle:{color:col},z:h?4:a?3:1,emphasis:{focus:'series',lineStyle:{width:3}}}})}).off('click');
  echarts.getInstanceByDom(document.getElementById('c3')).on('click',p=>go(p.seriesName));
}
draw();
const kinds=[...new Set(AN.map(a=>a.k))];
const rec=a=>{const out=(a.rec||[]).map(r=>K.p(r[0],r[1]||'line'));D.queries.filter(q=>q.sid===a.sid&&(a.qcat?a.qcat.includes(q.cat):false)).forEach(q=>out.push(K.qPill(q.id)));return out.join(' ')||(a.norec?K.p(a.norec,a.norecC||''):'')};
const tb=K.table(document.getElementById('at'),{rows:AN,noPage:true,cols:[{k:'k',t:'类型',f:a=>K.p(a.k,a.c)},{k:'sid',t:'受试者',f:a=>K.sid(a.sid,'&t=eff')},{k:'site',t:'中心',f:a=>`<span class="faint">${a.site||''}</span>`},{k:'v',t:'访视',f:a=>K.p(a.v,'blu')},{k:'t',t:'数据',f:a=>K.hlNum(a.t)},{k:'rec',t:'已有 AE / 质疑 / CRO',ns:1,f:rec},{k:'st',t:'处理',f:a=>`<span class="small muted">${K.esc(a.st)}</span>`}]});
K.chips(document.getElementById('ac'),kinds.map(k=>[k,k,AN.filter(a=>a.k===k).length]),v=>tb.set(v?AN.filter(a=>a.k===v):AN));
});

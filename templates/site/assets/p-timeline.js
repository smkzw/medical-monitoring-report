K.init(()=>{
const CF=K.cfg(),HL=CF.cmHighlight||null,hlRe=HL?new RegExp(HL.re):null;
const D=KZ,app=document.getElementById('app'),H=K.hash();
const subs=K.subs().filter(s=>s.fd);
const LR={};D.labrows.forEach(g=>(LR[g.sid]=LR[g.sid]||[]).push(g));
const OT={};D.others.forEach(g=>(OT[g.sid]=OT[g.sid]||[]).push(g));
const QS={};D.queries.forEach(q=>(QS[q.sid]=QS[q.sid]||[]).push(q));
const T=s=>{if(!s)return null;s=String(s).slice(0,10);let m;if(/^\d{4}-\d{2}-\d{2}$/.test(s))return Date.parse(s);if(m=s.match(/^(\d{4})-(\d{2})-uk/))return Date.parse(`${m[1]}-${m[2]}-15`);if(m=s.match(/^(\d{4})-uk/))return Date.parse(`${m[1]}-07-01`);return null};
const part=s=>/uk/.test(s||'');
const GC={1:'#FFCC00',2:'#FF9900',3:'#8B0000',4:'#5A0000',5:'#000'};
const sites=[...new Set(subs.map(s=>s.site))].sort();
app.innerHTML=`<div class="flex mb"><h1 style="font-size:18px">参与者时间线</h1><span class="muted small">访视 · 给药 · AE · 合并用药 · 病史 · 检验异常 · ECG/VS · 专项检查 · 质疑</span><span class="sp"></span><div class="seg" id="mode"></div></div><div id="pane"></div>`;
const pane=document.getElementById('pane');
let mode=H.c&&!H.s?'c':'s';
K.seg(document.getElementById('mode'),[['s','单受试者'],['c','中心概览']],mode,v=>{mode=v;v==='s'?one(H.s||subs[0].id):center(H.c||'03')});
mode==='s'&&subs.length?one(H.s||subs[0].id):center(H.c||'03');
/* ---------------- single subject */
async function one(id){
  H.s=id;K.setHash({s:id});
  pane.innerHTML=`<div class="card mb"><div class="tbar"><select class="s" id="sp">${subs.map(s=>`<option value="${s.id}" ${s.id===id?'selected':''}>${s.id} · ${s.site} ${K.esc(K.center(s.site))}</option>`).join('')}</select><span id="hd" class="flex wrap" style="gap:4px"></span><span class="sp"></span><a class="p click blu" href="subjects.html#s=${id}">参与者资料 →</a></div>
   <div class="flex wrap xs muted" style="gap:10px;margin:2px 0 4px"><span><span class="dot" style="background:#FFCC00"></span> AE 1级</span><span><span class="dot" style="background:#FF9900"></span> 2级</span><span><span class="dot red"></span> ≥3级</span><span>◆ AESI</span><span><span class="dot" style="background:#407AAA"></span> 给药</span>${HL?`<span><span class="dot" style="background:#8B0000;border-radius:2px"></span> ${K.esc(HL.label)}</span>`:''}<span>检验异常按风险标签分行：<b style="color:#8B0000">▲ CS未关联</b> · <span style="color:#FF9900">● CS仅关联MH</span> · <span style="color:#587B3B">● 已关联AE</span> · <span style="color:#C9A800">● NCS≥2级</span> · <span style="color:#9A9DA3">● NCS</span></span><span><span class="p org sq mono" style="font-size:10px">Q</span> 质疑</span>${((CF.blind||{}).hidden||[]).length?`<span>${CF.blind.hidden.map(K.esc).join('/')} 按约定不展示</span>`:''}</div>
   <div class="chart" id="tl" style="height:420px"></div></div>
   <div class="card"><div class="tbar"><b style="color:var(--ink)">检验/检查趋势</b><select class="s" id="tsel"></select><span class="note">与上方时间轴同步缩放</span></div><div class="chart" id="tr" style="height:230px"></div></div>`;
  document.getElementById('sp').onchange=e=>one(e.target.value);
  const d=await K.sub(id);if(!d)return;
  const s=K.subBy(id),lr=LR[id]||[],ot=OT[id]||[],qs=QS[id]||[];
  document.getElementById('hd').innerHTML=`${K.status(d.status)}${K.p('D1 '+d.fd,'blu')}${d.ld?K.p('末次给药 '+d.ld,'line'):''}${d.eot?K.p('EOT '+d.eot.why,'brn'):''}${lr.filter(g=>g.risk==='CSX').length?K.p('CS未关联 '+lr.filter(g=>g.risk==='CSX').length,'solid-red'):''}${qs.length?K.p('质疑 '+qs.length,'org'):''}`;
  const lanes=[],bars=[],pts=[];
  const lane=(name,grp)=>{lanes.push({name,grp});return lanes.length-1};
  // visits
  const PRE=((CF.timeline||{}).preDays)??30; // long-standing CM/MH bars are clipped to ICF−PRE days (true start in tooltip)
  const yv=lane('访视','A');d.visits.forEach(v=>{const t=T(v[2]);if(t)pts.push({y:yv,t,sym:'rect',size:9,c:'#64676B',lab:v[0],tip:`${v[1]} ${v[2]}`})});
  const ye=lane('研究药物','A');d.ec.forEach(e=>{const a=T(e.s),b=T(e.e)||a;if(a)bars.push({y:ye,a,b:b+864e5,c:'#407AAA',tip:`给药 ${e.s} → ${e.e} · ${e.n}${e.pause==='是'?' · 暂停':''}`,lab:''})});
  // AE
  d.ae.slice().sort((x,y)=>(x.s||'').localeCompare(y.s||'')).forEach(a=>{const y=lane(`${a.t} ${a.g.replace('级','')}`,'AE');const st=T(a.s),en=a.e?T(a.e):T(d.lo)||Date.now();const g=+a.g[0]||1;if(st)bars.push({y,a:st,b:Math.max(en,st)+864e5,c:GC[g]||'#FF9900',tip:`AE ${a.t}｜${a.g}｜${a.rel}｜${a.act}｜${a.out}<br>${a.s} → ${a.e||'持续'}${a.sae?'｜SAE':''}${a.aesi?'｜AESI':''}`,lab:'',aesi:a.aesi,open:!a.e})});
  // CM (non-iron condensed, iron each)
  d.cm.slice().sort((x,y)=>(x.s||'').localeCompare(y.s||'')).forEach(c=>{const iron=hlRe&&hlRe.test(c.t);const nm=c.t.length>9?c.t.slice(0,9)+'…':c.t;let y=lanes.findIndex(l=>l.grp==='CM'&&l.name===nm);if(y<0)y=lane(nm,'CM');const a=Math.max(T(c.s)||T(d.icf),T(d.icf)-PRE*864e5),b=c.ong?(T(d.lo)||Date.now()):T(c.e)||a;bars.push({y,a,b:b+864e5,c:iron?'#8B0000':'#A85F34',op:iron?.85:.55,tip:`CM ${c.t}｜${c.dose} ${c.fq}<br>${c.s} → ${c.ong?'持续':c.e}<br>原因：${K.esc(c.why||'—')}`,open:c.ong})});
  // MH ongoing
  const mh=d.mh.filter(m=>m.ong==='是');if(mh.length){mh.forEach(m=>{const y=lane('MH '+(m.t.length>8?m.t.slice(0,8)+'…':m.t),'MH');const a=Math.max(T(m.s)||0,T(d.icf)-PRE*864e5);bars.push({y,a,b:T(d.lo)||Date.now(),c:'#C9CCD1',op:.6,tip:`MH ${m.t}｜开始 ${m.s}｜筛选期持续`})})}
  // lab abnormal markers：按风险标签分行
  const RC={CSX:['#8B0000','triangle',10],MH:['#FF9900','circle',10],AE:['#587B3B','circle',9],NCS2:['#E8C300','circle',9],NA2:['#E8C300','emptyCircle',9],NCS:['#C9CCD1','circle',6]};
  ['CSX','MH','AE','NCS2','NA2','NCS'].forEach(rk=>{const G=lr.filter(g=>g.risk===rk&&g.pts.some(p=>T(p[1])));if(!G.length)return;const y=lane('检验 · '+K.RISK[rk][0],'L');
    G.forEach(g=>g.pts.forEach(p=>{const t=T(p[1]);if(!t)return;pts.push({y,t,sym:RC[rk][1],size:RC[rk][2],c:RC[rk][0],tip:`${g.test} ${p[0]} ${p[2]}${p[3]||''}${p[4]?' G'+p[4]:''}｜${K.RISK[rk][0]}`,test:g.test})}))});
  // 专项提示点：engine 生成 d.tl=[{lane,pts:[[date,tip,level 0/1/2,symbol,test]]}]（QTc/血压/影像等，每类风险单独一行）
  (d.tl||[]).forEach(G=>{const ps=G.pts.filter(p=>T(p[0]));if(!ps.length)return;const y=lane(G.lane,'O');ps.forEach(p=>pts.push({y,t:T(p[0]),sym:p[3]||'diamond',size:p[2]>=2?11:p[2]?9:6,c:p[2]>=2?'#8B0000':p[2]?'#FF9900':'#587B3B',tip:p[1],test:p[4]}))});
  // 专项核查 / 质疑：分行
  const ox=ot.filter(o=>T(o.d));if(ox.length){const y=lane('专项核查','O');ox.forEach(o=>pts.push({y,t:T(o.d),sym:'circle',size:o.pr>=3?9:6,c:o.pr>=4?'#8B0000':o.pr>=3?'#FF9900':'#C9CCD1',tip:`${o.cat}<br>${K.esc(o.sum)}`}))}
  const qx=qs.filter(q=>T(q.d));if(qx.length){const y=lane('质疑','Q');qx.forEach(q=>pts.push({y,t:T(q.d),sym:'roundRect',size:[22,13],c:'#FF9900',lab:q.id.replace('Q',''),tip:`${q.id} ${q.cat}<br>${K.esc(q.text.slice(0,120))}…`,q:q.id}))}
  // build chart
  const n=lanes.length;const h=Math.max(300,n*20+90);document.getElementById('tl').style.height=h+'px';
  const fd=T(d.fd),ld=T(d.ld);
  const tmin=Math.min(...bars.map(b=>b.a),...pts.map(p=>p.t).filter(Boolean),T(d.icf))-5*864e5,tmax=Math.max(...bars.map(b=>b.b),...pts.map(p=>p.t).filter(Boolean))+5*864e5;
  const GCOL={A:'#407AAA',AE:'#FF9900',CM:'#A85F34',MH:'#9A9DA3',L:'#8B0000',O:'#0F1115',Q:'#E67E00'};
  const ch=K.chart('#tl',{grid:{left:172,right:20,top:24,bottom:50},
    tooltip:{trigger:'item',formatter:p=>p.data.tip||''},
    dataZoom:[{type:'inside',xAxisIndex:0,filterMode:'none'},{type:'slider',xAxisIndex:0,height:16,bottom:8,filterMode:'none'}],
    xAxis:{type:'time',min:tmin,max:tmax,position:'top',...K.axis,axisLabel:{color:'#64676B',formatter:v=>{const x=Math.round((v-fd)/864e5);return (x>=0?'D'+(x+1):'D'+x)+'\n'+echarts.time.format(v,'{MM}-{dd}')}},splitLine:{show:true,lineStyle:{color:'#F0F1F4'}}},
    yAxis:{type:'category',inverse:true,data:lanes.map(l=>l.name),...K.axis,axisLabel:{fontSize:11,width:162,overflow:'truncate',color:p=>'#404040',formatter:(v,i)=>`{${lanes[i].grp}|${v}}`,rich:Object.fromEntries(Object.entries(GCOL).map(([k,c])=>[k,{color:c,fontSize:11}]))},splitLine:{show:true,lineStyle:{color:'#F5F6F8'}}},
    series:[
     {type:'custom',renderItem:(params,api)=>{const y=api.value(0),a=api.coord([api.value(1),y]),b=api.coord([api.value(2),y]);const hh=api.size([0,1])[1]*.56;const it=bars[params.dataIndex];return {type:'group',children:[{type:'rect',shape:{x:a[0],y:a[1]-hh/2,width:Math.max(b[0]-a[0],3),height:hh,r:2},style:{fill:it.c,opacity:it.op||1}},...(it.aesi?[{type:'text',style:{text:'◆',x:a[0]-9,y:a[1]-6,fill:'#8B0000',font:'10px sans-serif'}}]:[]),...(it.open?[{type:'text',style:{text:'›',x:b[0]+1,y:a[1]-8,fill:it.c,font:'bold 13px sans-serif'}}]:[])]}},encode:{x:[1,2],y:0},data:bars.map(b=>({value:[b.y,b.a,b.b],tip:b.tip}))},
     {type:'scatter',data:pts.filter(p=>p.t).map(p=>({value:[p.t,p.y],symbol:p.sym,symbolSize:p.size,itemStyle:{color:p.c},tip:p.tip,label:p.lab?{show:true,formatter:p.lab,fontSize:9,color:p.q?'#fff':'#64676B',position:p.q?'inside':'top'}:undefined,q:p.q,test:p.test})),z:5,
      markLine:{symbol:'none',silent:true,label:{fontSize:10,color:'#407AAA',position:'end'},lineStyle:{color:'#407AAA',type:'solid',width:1},data:[{xAxis:fd,label:{formatter:'D1'}},...(ld?[{xAxis:ld,label:{formatter:'末次'},lineStyle:{type:'dashed'}}]:[])]}}]});
  ch.off('click');ch.on('click',p=>{if(p.data&&p.data.q)K.showQ(p.data.q);else if(p.data&&p.data.test){document.getElementById('tsel').value=p.data.test;trend()}});
  // trend
  const allT=[...Object.keys(d.labs).map(t=>['labs',t]),...Object.keys(d.ecg).map(t=>['ecg',t]),...Object.keys(d.vs).map(t=>['vs',t])].filter(([o,t])=>d[o][t].some(r=>r[2]!=null)&&d[o][t].filter(r=>r[2]!=null).length>1);
  const fl=new Set(lr.filter(g=>g.risk!=='NCS').map(g=>g.test));
  allT.sort((a,b)=>(fl.has(b[1])-fl.has(a[1])));
  const ts=document.getElementById('tsel');
  if(!allT.length){ts.innerHTML='<option value="">（该受试者无≥2 次数值检验）</option>';return;}   // 单次/定性-only 受试者不再崩溃
  ts.innerHTML=allT.map(([o,t])=>`<option value="${K.esc(t)}">${fl.has(t)?'● ':''}${K.esc(t)}</option>`).join('');
  const def=H.t&&allT.some(x=>x[1]===H.t)?H.t:(allT.find(x=>fl.has(x[1]))||allT.find(x=>x[1]===CF.defaultTest)||allT[0])[1];ts.value=def;
  ts.onchange=trend;
  function trend(){const t=ts.value;const o=allT.find(x=>x[1]===t)[0];const rows=d[o][t].filter(r=>r[2]!=null);
    const lo=rows.find(r=>r[5]!=null)?.[5],hi=rows.find(r=>r[6]!=null)?.[6];const ml=[];if(lo!=null)ml.push({yAxis:lo,label:{formatter:'LLN'}});if(hi!=null)ml.push({yAxis:hi,label:{formatter:'ULN'}});((CF.refLines||{})[t]||[]).forEach(([y,l])=>ml.push({yAxis:y,label:{formatter:l||String(y)}}));
    if(/AST|ALT/.test(t)&&hi)ml.push({yAxis:hi*3,label:{formatter:'3×ULN'},lineStyle:{color:'#8B0000'}});
    const z=ch.getOption().dataZoom[0];
    const c2=K.chart('#tr',{grid:{left:172,right:20,top:16,bottom:26},tooltip:{trigger:'axis'},xAxis:{type:'time',min:tmin,max:tmax,...K.axis,axisLabel:{color:'#64676B',formatter:v=>{const x=Math.round((v-fd)/864e5);return x>=0?'D'+(x+1):'D'+x}}},yAxis:{type:'value',scale:true,name:rows[0][4],...K.axis},dataZoom:[{type:'inside',filterMode:'none',start:z.start,end:z.end}],
     series:[{type:'line',name:t,data:rows.map(r=>({value:[T(r[0])+(r[12]?(+r[12].slice(0,2))*36e5:0),r[2]],itemStyle:{color:r[7]===2?'#8B0000':r[7]===1?'#E8C300':'#FF9900'}})),symbolSize:8,lineStyle:{color:'#FF9900'},markLine:{symbol:'none',silent:true,lineStyle:{color:'#9A9DA3',type:'dashed'},label:{fontSize:10,position:'insideEndTop'},data:[...ml,{xAxis:fd,lineStyle:{color:'#407AAA',type:'solid'},label:{formatter:'D1',color:'#407AAA'}}]}}]});
    ch.off('datazoom');ch.on('datazoom',()=>{const z=ch.getOption().dataZoom[0];c2.dispatchAction({type:'dataZoom',start:z.start,end:z.end})});
  }
  trend();
}
/* ---------------- center overview */
function center(site){
  H.c=site;K.setHash({c:site});
  const C=D.centers.filter(c=>c.dosed);
  pane.innerHTML=`<div class="card"><div class="tbar"><select class="s" id="cs">${C.map(c=>`<option value="${c.site}" ${c.site===site?'selected':''}>${c.site} ${K.esc(c.name)}（${c.dosed}例）</option>`).join('')}</select><span id="ck" class="flex wrap" style="gap:4px"></span><span class="sp"></span><span class="note">横轴 = 研究日（以 D1 为第 1 天）；每位受试者下方按风险标签分行（AE / CS未关联 / CS仅关联MH / 质疑）；点击受试者编号进入单人时间线</span></div><div class="chart" id="cg" style="height:400px"></div><div id="ctb" class="mt"></div></div>`;
  document.getElementById('cs').onchange=e=>center(e.target.value);
  const S=subs.filter(s=>s.site===site).sort((a,b)=>a.fd.localeCompare(b.fd));
  const c=C.find(x=>x.site===site);
  document.getElementById('ck').innerHTML=`${K.p('给药 '+c.dosed,'blu')}${K.p('AE '+c.ae,c.ae?'':'red')}${c.csx?K.p('CS未关联 '+c.csx,'solid-red'):''}${c.mhx?K.p('CS仅MH '+c.mhx,'org'):''}${K.p('质疑 '+c.q,'line')}`;
  const day=(x,fd)=>{const t=T(x);return t==null?null:Math.round((t-T(fd))/864e5)+1};
  // 每位受试者：主行（暴露）+ 各风险标签子行（AE / CS未关联 / CS仅关联MH / 质疑，仅在有记录时显示）
  const bars=[],pts=[],R=[];
  S.forEach((s,si)=>{const lr=LR[s.id]||[],ae=D.aes.filter(a=>a.sid===s.id&&a.s),qq=(QS[s.id]||[]).filter(q=>q.d);
    const i=R.push({sid:s.id,si,k:'S',lab:s.id})-1;
    bars.push({value:[i,day(s.icf,s.fd),0],c:'#E6E8EC'});bars.push({value:[i,1,day(s.ld||s.lo,s.fd)],c:'#407AAA'});if(s.lo&&s.ld&&s.lo>s.ld)bars.push({value:[i,day(s.ld,s.fd),day(s.lo,s.fd)],c:'#DCE6F2'});
    if(ae.length){const y=R.push({sid:s.id,si,k:'AE',lab:'AE'})-1;ae.forEach(a=>{const g=+a.g[0]||1;pts.push({value:[day(a.s,s.fd),y],symbol:a.aesi?'diamond':'circle',symbolSize:g>=3?12:g>=2?10:8,itemStyle:{color:GC[g]},tip:`${s.id} AE ${a.t} ${a.g} D${day(a.s,s.fd)}${a.aesi?'｜AESI':''}`})})}
    ['CSX','MH'].forEach(rk=>{const G=lr.filter(g=>g.risk===rk);if(!G.length)return;const y=R.push({sid:s.id,si,k:rk,lab:rk==='CSX'?'CS未关联':'CS仅MH'})-1;
      G.forEach(g=>g.pts.forEach(p=>{const x=day(p[1],s.fd);if(x!=null)pts.push({value:[x,y],symbol:rk==='CSX'?'triangle':'emptyCircle',symbolSize:10,itemStyle:{color:rk==='CSX'?'#8B0000':'#FF9900'},tip:`${s.id} ${g.test} ${p[0]} ${p[2]} ｜${K.RISK[rk][0]}`})}))});
    if(qq.length){const y=R.push({sid:s.id,si,k:'Q',lab:'质疑'})-1;qq.forEach(q=>pts.push({value:[day(q.d,s.fd),y],symbol:'roundRect',symbolSize:[18,11],itemStyle:{color:'#FF9900',opacity:.9},label:{show:true,formatter:q.id.slice(1),fontSize:8,color:'#fff'},tip:`${q.id} ${q.cat}`,q:q.id}))}
  });
  document.getElementById('cg').style.height=Math.max(260,R.length*21+70)+'px';
  const ch=K.chart('#cg',{grid:{left:92,right:20,top:30,bottom:20},tooltip:{trigger:'item',formatter:p=>p.data.tip||''},
    xAxis:{type:'value',position:'top',...K.axis,axisLabel:{formatter:v=>'D'+v,color:'#64676B'}},
    yAxis:{type:'category',inverse:true,data:R.map(r=>r.lab),...K.axis,axisTick:{show:false},
      axisLabel:{interval:0,formatter:(v,i)=>R[i].k==='S'?`{s|${v}}`:`{${R[i].k}|${v}}`,rich:{s:{color:'#407AAA',fontWeight:700,fontSize:12},AE:{color:'#E67E00',fontSize:10},CSX:{color:'#8B0000',fontSize:10},MH:{color:'#FF9900',fontSize:10},Q:{color:'#64676B',fontSize:10}}},
      splitLine:{show:true,interval:(i)=>i+1<R.length&&R[i+1].k==='S',lineStyle:{color:'#E6E8EC'}}},
    series:[{type:'custom',renderItem:(p,api)=>{const y=api.value(0),a=api.coord([api.value(1),y]),b=api.coord([api.value(2),y]);const hh=api.size([0,1])[1]*.5;return {type:'rect',shape:{x:a[0],y:a[1]-hh/2,width:Math.max(b[0]-a[0],2),height:hh,r:2},style:{fill:bars[p.dataIndex].c}}},encode:{x:[1,2],y:0},data:bars,silent:true},
     {type:'scatter',data:pts,z:5,markLine:{symbol:'none',silent:true,lineStyle:{color:'#407AAA'},label:{formatter:'D1',fontSize:10},data:[{xAxis:1},...(CF.keyDays||[]).map(([x,l])=>({xAxis:x,lineStyle:{type:'dashed',color:'#9A9DA3'},label:{formatter:l}}))]}}]});
  ch.on('click',p=>{if(p.data&&p.data.q)K.showQ(p.data.q)});
  K.table(document.getElementById('ctb'),{rows:S,noPage:true,max:false,onRow:r=>{mode='s';document.querySelectorAll('#mode button').forEach(b=>b.classList.toggle('on',b.dataset.v==='s'));one(r.id)},cols:[
   {k:'id',t:'受试者',f:r=>`<b style="color:var(--blue)">${r.id}</b>`},{k:'status',t:'状态',f:r=>K.status(r.status)},{k:'fd',t:'D1'},{k:'dur',t:'给药天数',s:r=>r.ld?K.days(r.ld,r.fd):0,f:r=>r.ld?K.days(r.ld,r.fd)+1:'—'},
   {k:'nae',t:'AE',f:r=>r.nae?`<b>${r.nae}</b>${r.maxg?' '+K.p('最高'+r.maxg+'级',r.maxg>=3?'solid-red':r.maxg>=2?'red':'yel'):''}`:K.p('0','red')},
   {k:'csx',t:'CS未关联',s:r=>(LR[r.id]||[]).filter(g=>g.risk==='CSX').length,f:r=>{const n=(LR[r.id]||[]).filter(g=>g.risk==='CSX');return n.length?n.map(g=>K.p(g.test.replace(/（.*）/,''),'solid-red')).join(' '):''}},
   {k:'mhx',t:'CS仅MH',s:r=>(LR[r.id]||[]).filter(g=>g.risk==='MH').length,f:r=>(LR[r.id]||[]).filter(g=>g.risk==='MH').map(g=>K.p(g.test.replace(/（.*）/,''),'org')).join(' ')},
   {k:'nq',t:'质疑',f:r=>(QS[r.id]||[]).map(q=>K.qPill(q.id)).join(' ')}]});
  ch.getZr().on('click',e=>{const pt=ch.convertFromPixel({gridIndex:0},[e.offsetX,e.offsetY]);if(!pt)return;if(e.offsetX<92){const i=Math.round(pt[1]);if(R[i]){mode='s';document.querySelectorAll('#mode button').forEach(b=>b.classList.toggle('on',b.dataset.v==='s'));one(R[i].sid)}}});
}
});

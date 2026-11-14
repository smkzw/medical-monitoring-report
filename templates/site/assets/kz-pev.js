/* 方案事件（PLAN §17.20）：方案规定的逐条事件（急性发作/复发/出血发作…）。KZ.pev = {types:[{type,n,subj,py,rate,hosp,er,ongoing,pre,preSubj,
   centers:[{site,n,subj,py,rate}],months:[[YYYY-MM,n]],endpoints:[[类型,原文]]}],rows:[[sid,site,type,start,end,ong,treat,hosp,pre,period]],missing:[[类型,原文]],cols}
   呈现按数据形态：事件 → 事件数/发生人数/暴露人年/年化发生率（盲态不分组）＋中心对比＋按月计数＋事件清单（可跳到参与者时间线）。 */
K.pevSection=function(el){
  const P=KZ.pev||{types:[],rows:[],missing:[]};
  if(!(P.types||[]).length&&!(P.missing||[]).length){el.remove();return}
  const SMALL=5;   /* 中心暴露人年 <5：发生率不稳，标「样本小」不着色 */
  const rate=r=>r==null?'—':K.fmt(r);
  const miss=(P.missing||[]).length?`<div class="box red small mb">方案事件型终点未找到数据来源 ${P.missing.length} 项：${P.missing.map(m=>`${K.esc(m[0])}「${K.esc(m[1])}」`).join('；')}——请确认是否在单独的表或文件中</div>`:'';
  el.innerHTML=`<div class="card mb"><div class="sec-t" style="margin-top:0"><h2>方案事件</h2><span class="muted small">按方案终点定义汇总；年化发生率＝研究期间事件数 ÷ 暴露人年（首剂至研究结束或数据截止）${(K.cfg().blind||{}).on?' · 盲态不分组':''}</span></div>${miss}<div id="pevT"></div></div>`;
  const box=el.querySelector('#pevT');
  (P.types||[]).forEach((t,i)=>{
    const ep=(t.endpoints||[]).map(e=>K.p(e[0],/主要/.test(e[0])?'solid-red':'blu')).join('');
    const d=document.createElement('div');d.className='mb';
    d.innerHTML=`<div class="flex wrap" style="gap:6px;align-items:center"><b style="color:var(--ink)">${K.esc(t.type)}</b>${ep}</div>
      <div class="grid g4 mt">${[['研究期间事件',t.n],['发生人数',t.subj],['暴露人年',K.fmt(t.py)],['年化发生率（次/人年）',rate(t.rate)]].map(x=>`<div class="kpi"><div class="xs muted">${x[0]}</div><div class="v">${x[1]}</div></div>`).join('')}</div>
      <div class="small muted mt">需住院 ${t.hosp} 次 · 急诊 ${t.er} 次 · 未结束 ${t.ongoing} 次${t.pre?` · 研究前记录 ${t.pre} 次（${t.preSubj} 人，不计入发生率）`:''}</div>
      <div class="grid g12 mt"><div><div class="xs muted">各中心年化发生率</div><div id="pevC${i}"></div></div><div><div class="xs muted">按月事件数</div><div class="chart" id="pevM${i}" style="height:220px"></div></div></div>`;
    box.appendChild(d);
    const cn=s=>K.center?K.center(s):s;
    K.table(d.querySelector(`#pevC${i}`),{sort:'rate',dir:-1,pageSize:10,filter:false,
      cols:[{t:'中心',k:'site',f:c=>`${K.esc(c.site)} ${K.esc(cn(c.site))}`},{t:'事件数',k:'n'},{t:'发生人数',k:'subj'},{t:'暴露人年',k:'py',f:c=>K.fmt(c.py)},
            {t:'年化发生率',k:'rate',s:c=>c.py<SMALL?null:c.rate,f:c=>c.py<SMALL?`${rate(c.rate)} <span class="xs muted">样本小</span>`:rate(c.rate)}],
      rows:(t.centers||[]).filter(c=>c.py>0)});
    const ms=t.months||[];
    K.chart(`#pevM${i}`,{grid:{left:36,right:10,top:16,bottom:40},tooltip:{trigger:'axis'},xAxis:{type:'category',data:ms.map(m=>m[0])},
      yAxis:{type:'value',minInterval:1},series:[{type:'bar',data:ms.map(m=>m[1]),itemStyle:{color:'#6A3D9A'},label:{show:ms.length<=24,position:'top',fontSize:10}}]});
  });
  if((P.rows||[]).length){
    const d=document.createElement('div');d.innerHTML='<div class="xs muted mt">事件清单（点击参与者跳到时间线）</div><div id="pevR"></div>';box.appendChild(d);
    const dd=x=>K.ukd?K.ukd(x||''):(x||'');
    K.table(d.querySelector('#pevR'),{sort:'s',dir:-1,pageSize:20,
      cols:[{t:'参与者',k:'sid',f:r=>`<a href="timeline.html#s=${encodeURIComponent(r.sid)}">${K.esc(r.sid)}</a>`},{t:'中心',k:'site'},{t:'事件类型',k:'type'},
            {t:'开始',k:'s',f:r=>K.esc(dd(r.s))},{t:'结束',k:'e',f:r=>K.esc(dd(r.e))},{t:'持续',k:'ong',f:r=>r.ong?'是':'否'},{t:'处理方式',k:'treat'},
            {t:'住院',k:'hosp',f:r=>r.hosp?'是':''},{t:'研究前',k:'pre',f:r=>r.pre?'是':''},{t:'阶段',k:'period'},{t:'亚型/判定',k:'sub'}],
      rows:P.rows.map(r=>({sid:r[0],site:r[1],type:r[2],s:r[3],e:r[4],ong:r[5],treat:r[6]||'',hosp:r[7],pre:r[8],period:r[9]||'',sub:r[10]||''}))});
  }
};

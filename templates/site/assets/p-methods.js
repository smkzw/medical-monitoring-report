K.init(()=>{
const D=KZ,X=KZX,app=document.getElementById('app'),H=K.hash();
const S=K.subs(),M=Object.fromEntries(D.methods.map(m=>[m.id,m]));
const qc=cats=>D.queries.filter(q=>cats.includes(q.cat));
const lr=f=>D.labrows.filter(f).length;
const ctrAE={};S.filter(s=>s.fd).forEach(s=>{const c=ctrAE[s.site]=ctrAE[s.site]||[0,0];c[0]++;c[1]+=s.nae});
const lowAE=Object.entries(ctrAE).filter(([k,v])=>v[0]>=2&&v[1]/v[0]<=0.5).sort((a,b)=>a[1][1]/a[1][0]-b[1][1]/b[1][0]);
const P=K.p,sid=K.sid;
/* line helpers */
const A=(pill,c,txt)=>`<div class="ab">${P(pill,c)}<span>${txt}</span></div>`;
const W=(sids,txt,tag='待判断')=>`<div class="ab">${P(tag,'yel')}<span>${sids.map(s=>sid(s)).join(' ')} ${txt}</span></div>`;
/* ---------------- tab definitions: KZ.review（engine 生成，可由 MM 在 review.json 中补写）----------------
 [{k,t,sh:[sheet],ib:[aeCat],f:[field],flow:[[step,desc]],ab:{个体:[[pill,cls,text]],中心:[..],全局:[..]},ex:[[exKey,look,noqText]],m:[methodId],r:[ruleId],todo:[[[sid..],text,tag]],go:[[href,label]]}] */
const T=(D.review||[]).map(t=>({k:t.k,t:t.t,sh:t.sh||[],ib:t.ib||[],f:t.f||[],flow:t.flow||[],r:t.r||[],go:t.go||[],m:(t.m||[]).filter(id=>M[id]),ex:t.ex||[],
  ab:Object.fromEntries(Object.entries(t.ab||{}).map(([k,v])=>[k,v.map(x=>A(x[0],x[1],x[2]))])),todo:(t.todo||[]).map(x=>W(x[0],x[1],x[2]))}));
if(!T.length){app.innerHTML='<div class="card empty">未生成审阅要点（KZ.review 为空）</div>';return}
/* ---------------- render ---------------- */
app.innerHTML=`<div class="flex mb"><h1 style="font-size:18px">审阅要点</h1><span class="muted small">按数据页组织：关注字段 · 判读路径 · 异常界定 · 实例（真实 listing）· 处理</span><span class="sp"></span>${D.methods.map(m=>`<span class="p sq mono click line" data-m="${m.id}" title="${K.esc(m.domain)}">${m.id}</span>`).join('')}</div>
<div class="tabs" id="tabs"></div><div id="pane"></div>`;
const pane=app.querySelector('#pane');
function exCard([key,look,noq]){const e=X.ex[key];if(!e)return '';const q=e.q&&K.qById(e.q);const s0=e.sid||(e.rows[0].f[(K.cfg().subjectField)||'受试者编号']);
 const out=q?`<div class="flex wrap" style="align-items:flex-start;gap:6px">${K.qPill(q.id)}${P(q.cat,'line')}${P(q.cro,q.cro==='冲突澄清'?'red':q.cro==='未见同问'?'grn':'yel')}</div><div class="small mt" style="margin-top:4px;line-height:1.65">${q.parts.filter(p=>!p[1]).map(p=>K.hlNum(p[0])).join(' ')}</div>`
  :`<div class="flex">${/确认/.test(noq||'')?P('未发 query · 待确认','yel'):P('不发 query','grn')}</div><div class="small" style="margin-top:4px;line-height:1.65">${K.esc((noq||'').replace(/^未(发新|重复发|发) query：/,''))}</div>`;
 const cro=(e.cro||[]).length?`<div class="xs muted mt">${K.esc(((K.cfg().query||{}).extLabel)||'外部质疑')}：${e.cro.map(c=>`${P(c.sheet.replace(/^\(\d+\)/,''),'sq')} 行${c.row}「${K.esc(c.text)}」`).join(' ')}</div>`:'';
 return `<div class="card ex"><div class="hd">${sid(s0)}<span class="small"><b>${K.esc(look)}</b></span><span class="sp"></span><a class="xs" href="timeline.html#s=${s0}">时间线 ›</a></div>
  <div class="grid" style="grid-template-columns:minmax(0,1.9fr) minmax(0,1fr);gap:12px"><div style="min-width:0">${K.listing(e.rows)}</div><div class="box ${q?'org':''}">${out}${cro}</div></div></div>`}
function draw(k){const t=T.find(x=>x.k===k)||T[0];K.setHash({t:t.k});
 const qs=qc(D.queries.filter(q=>t.ex.some(e=>X.ex[e[0]]&&X.ex[e[0]].q===q.id)).map(q=>q.cat));
 pane.innerHTML=`
 <div class="grid" style="grid-template-columns:minmax(0,1.35fr) minmax(0,1fr);gap:12px">
  <div class="card"><div class="hd"><h2>${t.t}</h2>${t.sh.map(s=>P(s,'sq mono')).join('')}<span class="sp"></span>${t.ib.map(c=>`<span class="xs muted" style="margin-left:6px">${K.esc(c)}</span>${K.ibTags(c)}`).join('')}</div>
   <div class="xs muted" style="margin-bottom:4px">关注字段</div><div class="flex wrap" style="gap:4px">${t.f.map(x=>P(x,'org')).join('')}</div>
   <div class="xs muted" style="margin:10px 0 4px">判读路径</div><div class="flow">${t.flow.map(([a,b],i)=>`<div class="st"><span class="n">${i+1}</span><b>${a}</b><span class="xs muted">${b}</span></div>`).join('')}</div>
   <div class="flex wrap mt" style="gap:4px"><span class="xs muted">依据</span>${t.r.map(r=>K.rp(r)).join('')}<span class="sp"></span>${t.go.map(([h,l])=>`<a class="small" href="${h}">${l} ›</a>`).join(' · ')}</div></div>
  <div class="card"><div class="hd"><h2>异常界定</h2><span class="sub">个体 · 中心 · 全局</span></div>
   ${Object.entries(t.ab).map(([lv,ls])=>`<div class="lv"><span class="lvt">${lv}</span><div class="lvb">${ls.join('')}</div></div>`).join('')}</div>
 </div>
 ${t.todo.length?`<div class="card mt"><div class="hd"><h2>本页待判断事项</h2><span class="sub">未写入 query，提交医学判断</span></div>${t.todo.join('')}</div>`:''}
 <div class="sec-t"><h2>实例</h2><span class="muted small">EDC 原始行，高亮为判读字段；右侧为处理结果</span></div>
 ${t.ex.length?t.ex.map(exCard).join(''):`<div class="card"><div class="empty">本页实例见 <a href="efficacy.html">有效性趋势</a> 的“受试者层面异常”表</div></div>`}
 <div class="sec-t"><h2>MM 规则</h2><span class="muted small">${t.m.join(' · ')}</span></div>
 <div class="grid g${Math.min(t.m.length,3)}">${t.m.map(id=>{const m=M[id];return `<div class="card"><div class="hd"><span class="p sq mono org">${id}</span><h3>${K.esc(m.domain)}</h3><span class="sp"></span><span class="xs faint">${K.esc(m.source)}</span></div>
  <div class="mr"><span>数据</span><div>${K.esc(m.data)}</div></div><div class="mr"><span>判读</span><div>${K.esc(m.principle)}</div></div><div class="mr"><span>处理</span><div>${K.esc(m.action)}</div></div></div>`}).join('')}</div>`;
}
K.tabs(app.querySelector('#tabs'),T.map(t=>[t.k,t.t,t.ex.length||null]),(T.find(t=>t.k===H.t)||T[0]).k,draw);
document.addEventListener('click',e=>{const a=e.target.closest('[data-m]');if(!a)return;const m=M[a.dataset.m];const tab=T.find(t=>t.m.includes(m.id));
 K.drawer(`${m.id} · ${K.esc(m.domain)}`,`<div class="mr"><span>数据</span><div>${K.esc(m.data)}</div></div><div class="mr"><span>判读</span><div>${K.esc(m.principle)}</div></div><div class="mr"><span>风险</span><div>${K.esc(m.risk)}</div></div><div class="mr"><span>处理</span><div>${K.esc(m.action)}</div></div><div class="mr"><span>来源</span><div class="muted">${K.esc(m.source)}</div></div>${tab?`<div class="mt"><a href="#t=${tab.k}" onclick="location.hash='t=${tab.k}';location.reload()">在「${tab.t}」页查看实例 ›</a></div>`:''}`)});
});

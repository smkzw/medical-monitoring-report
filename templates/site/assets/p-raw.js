/* V6 原始数据浏览器（研究/中心层面）：listing 全部表单（含未映射表单）按中心/受试者/关键词浏览原行；
 * 有风险或质疑的行加徽标，点行查看对应信号；受试者号跳个例页。数据：data/rawidx.js＋data/r/<sid>.js（按需载入）。 */
K.init(async()=>{
const D=KZ,app=document.getElementById('app'),H=K.hash();
app.innerHTML='<div class="card empty">载入原始数据目录…</div>';
const I=await K.rawIdx();
if(!I){app.innerHTML='<div class="card empty">本报告未包含原始数据。</div>';return}
const EV=K.allEvidence();
const sheetSig={};Object.entries(EV).forEach(([sid,es])=>es.forEach(e=>{const k=K.rawKey(I,e.sh);if(k)(sheetSig[k]=sheetSig[k]||new Set()).add(sid+'|'+e.row)}));
const SUB=Object.fromEntries(K.subs().map(s=>[s.id,s]));
const DN={subjects:'受试者',visits:'访视',exposure:'给药',ae:'不良事件',mh:'病史',cm:'合并用药',proc:'操作/手术',lab:'检验',vs:'生命体征',ecg:'心电图',pe:'体格检查',exam:'专项检查',efficacy:'有效性',pd:'方案偏离',sample:'样本',extq:'外部质疑'};
const keys=Object.keys(I.sheets).sort((a,b)=>{const A=I.sheets[a],B=I.sheets[b];return (A.mapped===B.mapped?0:A.mapped?-1:1)||String(DN[A.domain]||'').localeCompare(String(DN[B.domain]||''),'zh')||A.name.localeCompare(B.name,'zh')});
const st={k:H.k&&I.sheets[H.k]?H.k:(keys.find(k=>(sheetSig[k]||new Set()).size)||keys[0]),c:H.c||'',s:H.s||'',q:'',hit:false};
app.innerHTML=`<div class="grid" style="grid-template-columns:280px 1fr;gap:14px;align-items:start">
 <div class="card" style="padding:6px 0;position:sticky;top:66px;max-height:calc(100vh - 90px);overflow:auto">
  <div class="xs muted" style="padding:4px 12px 8px;line-height:1.6">listing 全部 ${keys.length} 张含受试者的表单（含 ${keys.filter(k=>!I.sheets[k].mapped).length} 张未映射）。数字＝行数；橙标＝有风险/质疑的行数。</div>
  <div id="shl"></div></div>
 <div style="min-width:0"><div class="card mb" style="padding:10px 14px"><div class="flex wrap" style="gap:8px;align-items:center"><b id="tt" style="color:var(--ink);font-size:15px"></b><span class="xs muted" id="tm"></span><span class="sp"></span>
   <select class="s" id="fc"><option value="">全部中心</option>${D.centers.filter(c=>c.n).map(c=>`<option value="${c.site}">${c.site} ${K.esc(c.name)}</option>`).join('')}</select>
   <input class="s" id="fs" placeholder="受试者编号" style="width:110px"><input class="s" id="fq" placeholder="关键词（任一列）" style="width:150px"><label class="xs muted"><input type="checkbox" id="fh"> 只看有信号的行</label></div>
   <div class="xs faint mt" id="tc"></div></div>
  <div class="card" style="min-width:0;overflow:hidden"><div id="tb"></div><div class="xs faint mt">已剔除姓名/缩写等隐私列${(I.dropped||[]).length?'（'+I.dropped.map(K.esc).join('、')+'）':''}；表头橙字为该表单与判定相关的列。</div></div></div></div>`;
document.getElementById('fc').value=st.c;document.getElementById('fs').value=st.s;
const grp={};keys.forEach(k=>{const m=I.sheets[k],g=m.mapped?(DN[m.domain]||m.domain||'其他'):'未映射';(grp[g]=grp[g]||[]).push(k)});
document.getElementById('shl').innerHTML=Object.entries(grp).map(([g,ks])=>`<div class="xs muted" style="padding:6px 12px 2px;font-weight:600">${K.esc(g)}</div>${ks.map(k=>{const m=I.sheets[k],n=(sheetSig[k]||new Set()).size;
  return `<div class="it rs" data-k="${K.esc(k)}" style="padding:5px 12px;cursor:pointer;display:flex;gap:6px;align-items:center"><span class="small" style="flex:1;color:var(--ink)">${K.esc(m.name)}</span><span class="xs faint">${m.n}</span>${n?`<span class="p org sq">${n}</span>`:''}</div>`}).join('')}`).join('');
let seq=0;
async function draw(){const my=++seq,m=I.sheets[st.k];K.setHash({k:st.k,c:st.c,s:st.s});
  document.querySelectorAll('.rs').forEach(x=>x.classList.toggle('on',x.dataset.k===st.k));
  document.getElementById('tt').textContent=m.name;
  document.getElementById('tm').textContent=`${m.mapped?(DN[m.domain]||m.domain||''):'未映射表单'} · ${m.n} 行 · ${m.nsub} 名受试者`;
  const cst=Object.entries(m.const||{});document.getElementById('tc').innerHTML=cst.length?'本表单固定值：'+cst.slice(0,8).map(([a,b])=>`${K.esc(a)}＝${K.esc(b)}`).join('；'):'';
  const sids=Object.keys(I.subs).filter(s=>I.subs[s].includes(st.k)&&(!st.c||(SUB[s]||{}).site===st.c)&&(!st.s||s.includes(st.s))).sort();
  const tb=document.getElementById('tb');tb.innerHTML=`<div class="empty">载入表单原始数据…</div>`;
  const rows=[],hit=new Set(),want=new Set(sids);
  if(m.f!=null){const all=await K.rawSheet(st.k);if(my!==seq)return;   /* 按表单一次载入（工程审阅 P2-7） */
    (all||[]).forEach(r=>{if(!want.has(r[0]))return;rows.push(r);if((sheetSig[st.k]||new Set()).has(r[0]+'|'+r[1]))hit.add(rows.length-1)})}
  else{let done=0;                                                     /* 旧版构建无按表单文件：回退按受试者载入 */
    for(let i=0;i<sids.length;i+=16){const batch=sids.slice(i,i+16),Rs=await Promise.all(batch.map(s=>K.raw(s)));if(my!==seq)return;
      done+=batch.length;tb.innerHTML=`<div class="empty">载入中 ${done}/${sids.length}…</div>`;
      batch.forEach((s,bi)=>((Rs[bi]||{})[st.k]||[]).forEach(r=>{const key=s+'|'+r[0];rows.push([s,...r]);if((sheetSig[st.k]||new Set()).has(key))hit.add(rows.length-1)}))}}
  const kw=st.q;let idx=rows.map((_,i)=>i);
  if(st.hit)idx=idx.filter(i=>hit.has(i));if(kw)idx=idx.filter(i=>rows[i].some(v=>String(v).includes(kw)));
  const hl=new Set(m.hl||[]),ord=K.rawOrder(m),cols=ord.map(j=>m.cols[j]),MAX=1500;
  tb.innerHTML=idx.length?`<div class="xs muted mb">${idx.length} 行${idx.length>MAX?`（显示前 ${MAX} 行，请用中心/受试者/关键词缩小范围）`:''} · 有信号 ${[...hit].filter(i=>idx.includes(i)).length} 行</div><div class="listing tw" style="max-height:72vh;overflow:auto;max-width:100%"><table><thead><tr><th>受试者</th><th>中心</th><th>行</th>${cols.map(c=>`<th${hl.has(c)?' class="hlc"':''}>${K.esc(c)}</th>`).join('')}</tr></thead><tbody>${idx.slice(0,MAX).map(i=>{const r=rows[i],h=hit.has(i);
    return `<tr class="${h?'hit':''}" data-i="${i}"><td><a class="sid" href="subjects.html#s=${encodeURIComponent(r[0])}&t=raw">${K.esc(r[0])}</a></td><td class="faint">${K.esc((SUB[r[0]]||{}).site||'')}</td><td class="faint">${r[1]}</td>${ord.map(j=>{const c=m.cols[j];return `<td class="${h&&hl.has(c)?'on':''}" title="${K.esc(r[j+2])}">${K.esc(r[j+2])}</td>`}).join('')}</tr>`}).join('')}</tbody></table></div>`:'<div class="empty">无匹配行</div>';
  tb.querySelectorAll('tr.hit').forEach(tr=>{tr.style.cursor='pointer';tr.onclick=e=>{if(e.target.closest('a'))return;const r=rows[+tr.dataset.i],its=(EV[r[0]]||[]).filter(x=>K.rawKey(I,x.sh)===st.k&&+x.row===+r[1]);
    if(its.length===1)return its[0].open();
    const b=K.drawer(`${K.esc(r[0])} · ${K.esc(m.name)} 第 ${r[1]} 行`,`<div class="small muted mb">本行涉及 ${its.length} 条风险/质疑</div>${its.map((x,i)=>`<div class="drow click" data-i="${i}" style="padding:6px 0;border-bottom:1px solid #F0F1F4">${K.p({lab:'检验',oth:'专项',q:'质疑'}[x.kind],x.kind==='q'?'org':'line')} ${K.esc(x.label)}</div>`).join('')}`);
    b.querySelectorAll('[data-i]').forEach(d=>d.onclick=()=>its[+d.dataset.i].open())}})}
document.querySelectorAll('.rs').forEach(x=>x.onclick=()=>{st.k=x.dataset.k;draw()});
document.getElementById('fc').onchange=e=>{st.c=e.target.value;draw()};
let tmr;const deb=f=>{clearTimeout(tmr);tmr=setTimeout(f,250)};
document.getElementById('fs').oninput=e=>{st.s=e.target.value.trim();deb(draw)};
document.getElementById('fq').oninput=e=>{st.q=e.target.value.trim();deb(draw)};
document.getElementById('fh').onchange=e=>{st.hit=e.target.checked;draw()};
draw();
});

/* mm5 安全性概况页：顶部切换 全试验 / 中心 / 参与者（#c=中心 / #s=参与者），内容由 profile.js 的 K.profile 渲染 */
K.init(()=>{
const D=KZ,app=document.getElementById("app"),S=K.subs();
app.innerHTML=`<div class="flex mb"><h1 style="font-size:18px">安全性概览</h1><span class="muted small">全试验 · 中心 · 参与者三级，中心对照整体、参与者对照所在中心与整体</span><span class="sp"></span>
 <span class="small muted">中心</span><select class="s" id="pc"><option value="">全试验</option>${D.centers.filter(c=>c.dosed).map(c=>`<option value="${c.site}">${c.site} ${K.esc(c.name)}（${c.dosed} 例）</option>`).join('')}</select>
 <span class="small muted" style="margin-left:8px">参与者</span><input class="s" id="ps" list="psl" placeholder="编号" style="width:110px"><datalist id="psl">${S.filter(s=>s.fd).map(s=>`<option value="${s.id}">`).join('')}</datalist></div><div id="pf"></div>`;
const pc=document.getElementById('pc'),ps=document.getElementById('ps');
const go=()=>{const sid=ps.value.trim(),sub=sid?K.subBy(sid):null,site=sub?sub.site:pc.value;if(sub)pc.value=sub.site;K.setHash(sub?{s:sub.id}:site?{c:site}:{});K.profile(document.getElementById('pf'),{site,sid:sub?sub.id:''})};
const fromHash=()=>{const h=K.hash();pc.value=h.c||'';ps.value=h.s||''};
fromHash();
pc.onchange=()=>{ps.value='';go()};ps.onchange=go;
window.addEventListener('hashchange',()=>{const h=K.hash();if((h.c||'')===pc.value&&(h.s||'')===ps.value.trim())return;fromHash();go()});
go();
});

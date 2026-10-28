/* 阈值档位（T_base 20/30/50%）：构建时每档各算一遍分析（data/core.b20.js 等，只含与默认档不同的数据），
 * 这里在页面脚本之前按所选档位同步载入；kz.js 再把它覆盖进 KZ。所选档位存于 localStorage（按研究编号区分）。 */
(function(){var c=(window.KZ||{}).cfg||{},f=c.thrTiers||{},s=null;
  try{s=JSON.parse(localStorage.getItem('kz.thr:'+((c.study||{}).code||''))||'null')}catch(e){}
  var b=s&&s.base!=null?String(s.base):null;if(b&&f[b])document.write('<script src="data/'+f[b]+'"><\/script>');})();

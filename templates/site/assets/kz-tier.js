/* 阈值档位（T_base 20/30/50%）：构建时每档各算一遍分析（data/core.b20.js 等，只含与默认档不同的数据），
 * 这里在页面脚本之前按所选档位同步载入；kz.js 再把它覆盖进 KZ。所选档位存于 localStorage（按研究编号区分；用户自选或工作台项目阈值的副本）。
 * F5（V6 RUX）：研究编号缺失时键回退项目 id／报告路径——不再退化成全局键（跨项目/跨报告互相改写档位）；
 * 与 kz.js K.thrKey 同一表达式（两处必须一致，否则档位数据载不进）。 */
(function(){var c=(window.KZ||{}).cfg||{},f=c.thrTiers||{},s=null;
  var key='kz.thr:'+((c.study||{}).code||((window.KZS||{}).project||{}).id||(typeof location!=='undefined'?location.pathname.replace(/\/[^\/]*$/,'').replace(/[^0-9A-Za-z_-]+/g,'').slice(-48):'')||'report');
  try{s=JSON.parse(localStorage.getItem(key)||'null')}catch(e){}
  var b=s&&s.base!=null?String(s.base):null;if(b&&f[b])document.write('<script src="data/'+f[b]+'"><\/script>'); })();

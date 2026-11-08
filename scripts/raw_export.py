"""V6 原始数据层（审阅者 2026-11-02，用户：风险/质疑/异常旁边要能直接看原始数据，不再另开 Excel）。

把 listing 全部工作簿中「含受试者编号列」的表单（含未映射表单——如 D002 主要终点所在的「月经周期及出血情况」）
按受试者导出为 data/r/<sid>.js（按需载入），表单目录写 data/rawidx.js：
  window.KZRI = {sheets: {<表单id>: {name, wb, mapped, domain, cols:[列名…], const:{列名: 值}, hl:[高亮列], n, nsub}},
                 subs: {<sid>: [表单id…]}, dropped: [被剔除的隐私列名…]}
  KZ_RAW("<sid>", {<表单id>: [[原始行号, 值1, 值2…], …]})
- 表单 id 与 normalize _source.json 的 sheets 键同口径（「工作簿别名:表单名」），证据 [sh,row] 可直接定位；
- 剔除隐私列（姓名/缩写/身份证/电话/住址类）；整列为空的列丢弃；对全部导出行取值相同的列上提为 const；
- 只导出受试者编号属于本研究受试者的行（目录页、空行、汇总行自然排除）。
"""
import datetime as _dt
import json
import re
from collections import defaultdict
from pathlib import Path

from common import open_workbook_lenient, pii_column   # H1（第 3 轮 SAR）：隐私列判定收口 common.pii_column，摘录/导出出口共用
SID_HDR = re.compile(r'^(受试者(筛选)?(编号|号|代码)?|参与者(编号|号)?|筛选号|SUBJID|USUBJID|Subject\s*ID|Participant\s*ID)$', re.I)
MAX_CELL = 300
FLAG_HDR = re.compile(r'^(Flag|变更标记|数据状态|记录状态)$', re.I)
DELETED = re.compile(r'delet|删除|作废', re.I)
# 盲态（V6 工程审阅 P0：RUX 受试者报表无表头的「列8」带着全部受试者的治疗组/安慰剂组，原始数据页可见）：
# 分组列按表头或取值形态识别，盲态构建整列不导出（只记列名，不记取值）
ARM_HDR = re.compile(r'分组|组别|治疗组|随机(分)?组|\bARMC?D?\b|ACTARM|TRT0?1[AP]|TRTP|RANDG|treatment\s*(arm|group)', re.I)
ARM_VAL = re.compile(r'(安慰剂|placebo|对照组|治疗组|试验组|剂量组|低剂量|高剂量|\barm\s*[A-Z0-9]\b)', re.I)


def arm_column(label, vals, extra=()):
    """分组列判定：表头像分组；或取值 2–8 种、≥80% 非空值像组名（含安慰剂/对照组/治疗组…或等于项目分组名）。"""
    if ARM_HDR.search(label or ''):
        return True
    v = [x for x in vals if x]
    d = set(v)
    if not v or not (2 <= len(d) <= 8):
        return False
    ex = {e for e in extra if e}
    hit = sum(1 for x in v if ARM_VAL.search(x) or x in ex)
    return hit >= 0.8 * len(v)


def _cell(v):
    if v is None:
        return ''
    if isinstance(v, _dt.datetime):
        return v.date().isoformat() if (v.hour, v.minute, v.second) == (0, 0, 0) else v.strftime('%Y-%m-%d %H:%M')
    if isinstance(v, _dt.date):
        return v.isoformat()
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    s = str(v).strip()
    return s if len(s) <= MAX_CELL else s[:MAX_CELL] + '…'


def _locate(rows, subj, hint=None):
    """→ (表头行下标, 受试者列下标) 或 None。表头取受试者列表头所在行；hint＝已映射表单的受试者列名。"""
    head = rows[:6]
    sample = rows[:3000]
    best = None
    ncol = max((len(r) for r in head), default=0)
    for j in range(min(ncol, 80)):
        vals = [_cell(r[j]) for r in sample if j < len(r) and r[j] not in (None, '')]
        if not vals:
            continue
        hit = sum(v in subj for v in vals)
        if hit < 1 or hit / len(vals) < 0.5:
            continue
        hdr = next((i for i, r in enumerate(head) if j < len(r) and (
            (hint and _cell(r[j]) == hint) or SID_HDR.search(_cell(r[j])))), None)
        if hdr is None:
            hdr = next((i for i, r in enumerate(head) if j < len(r) and _cell(r[j]) not in subj and _cell(r[j])), 0)
        cand = (hit, -j, hdr, j)
        if best is None or cand > best:
            best = cand
    return (best[2], best[3]) if best else None


def export_raw(C, out):
    out = Path(out)
    (out / 'r').mkdir(parents=True, exist_ok=True)
    subj = set(C.subj)
    src = C.src or {}
    sheets_meta = src.get('sheets') or {}
    by_name = {(m.get('wb'), m.get('sheet')): (k, m) for k, m in sheets_meta.items()}
    idx = {'sheets': {}, 'subs': defaultdict(list), 'dropped': []}
    per_sub = defaultdict(dict)
    dropped = set()
    bd = (C.cfg.get('blind') or {}) if isinstance(getattr(C, 'cfg', None), dict) else {}
    blind_on, arm_names = bool(bd.get('on')), list(bd.get('groupNames') or bd.get('terms') or [])
    for alias, path in (src.get('workbooks') or {}).items():
        try:
            wb = open_workbook_lenient(path)[0]
        except Exception:  # noqa: BLE001 打不开的工作簿跳过（normalize 已报告）
            continue
        for ws in wb.worksheets:
            rows = list(ws.iter_rows(values_only=True))
            if len(rows) < 2:
                continue
            key, meta = by_name.get((alias, ws.title), (f'{alias}:{ws.title}', None))
            loc = _locate(rows, subj, (meta or {}).get('sid'))
            if not loc:
                continue
            h, sc = loc
            labels = [_cell(x) or f'列{j + 1}' for j, x in enumerate(rows[h])]
            fl = [j for j, lab in enumerate(labels) if FLAG_HDR.search(lab)]   # 差异导出的变更标记列：已删除的行不展示
            data = []
            for i in range(h + 1, len(rows)):
                r = rows[i]
                sid = _cell(r[sc]) if sc < len(r) else ''
                if fl and any(j < len(r) and DELETED.search(_cell(r[j])) for j in fl):
                    continue
                if sid in subj:
                    data.append((sid, i + 1, [_cell(r[j]) if j < len(r) else '' for j in range(len(labels))]))
            if not data:
                continue
            keep = []
            const = {}
            hl = set((meta or {}).get('hl') or [])
            # V6 第 8 轮医学审阅（SAR：分组表按组别排序，第 2–88 行安慰剂、89–176 行试验组）：盲态下含分组列的表，
            # 只剔除分组列不够——原始行号（行序）本身就能还原分组。整表不进原始数据层；剔除记录不写列名（列名本身是分组用语）
            if blind_on and any(arm_column(lab, [d[2][j] for d in data], arm_names) for j, lab in enumerate(labels) if j != sc):
                dropped.add(f"表单「{ws.title}」整表（盲态：含分组信息，行序可推断分组）")
                continue
            for j, lab in enumerate(labels):
                if j == sc:
                    continue
                if pii_column(lab):
                    dropped.add(lab)
                    continue
                vals = {d[2][j] for d in data}
                if vals == {''}:
                    continue
                if len(vals) == 1 and len(data) > 1 and lab not in hl:
                    const[lab] = next(iter(vals))
                    continue
                keep.append(j)
            # V6（MY008 运营审阅：原始数据页目录只有 LB1/DS3 代码）：有表单目录时显示「中文名（代码）」
            fnm = (src.get('formNames') or {}).get(ws.title)
            idx['sheets'][key] = {'name': f"{fnm}（{ws.title}）" if fnm and fnm != ws.title else ws.title, 'sheet': ws.title, 'wb': alias, 'mapped': meta is not None, 'domain': (meta or {}).get('domain') or '',
                                  'cols': [labels[j] for j in keep], 'const': const, 'hl': [c for c in dict.fromkeys(labels) if c in hl],
                                  'n': len(data), 'nsub': len({d[0] for d in data})}
            for sid, rn, vals in data:
                per_sub[sid].setdefault(key, []).append([rn] + [vals[j] for j in keep])
    for sid, shs in per_sub.items():
        idx['subs'][sid] = sorted(shs)
        (out / 'r' / f'{sid}.js').write_text('KZ_RAW(' + json.dumps(sid, ensure_ascii=False) + ',' +
                                             json.dumps(shs, ensure_ascii=False, separators=(',', ':')) + ');', encoding='utf-8')
    # V6 工程审阅 P2-7：原始数据页按表单浏览——另出按表单的 data/rs/<序号>.js（行＝[受试者, 行号, …值]），
    # 页面只载入当前表单（此前要把全部受试者文件 RUX 约 39 MB 逐个载入）；个例页仍读按受试者的 data/r/<sid>.js
    (out / 'rs').mkdir(parents=True, exist_ok=True)
    by_sheet = defaultdict(list)
    for sid in sorted(per_sub):
        for key, rows_ in per_sub[sid].items():
            by_sheet[key] += [[sid] + r_ for r_ in rows_]
    for i, key in enumerate(sorted(idx['sheets'])):
        idx['sheets'][key]['f'] = i
        (out / 'rs' / f'{i}.js').write_text('KZ_RAWS(' + json.dumps(key, ensure_ascii=False) + ',' +
                                            json.dumps(by_sheet.get(key, []), ensure_ascii=False, separators=(',', ':')) + ');', encoding='utf-8')
    idx['dropped'] = sorted(dropped)
    idx['subs'] = dict(idx['subs'])
    (out / 'rawidx.js').write_text('window.KZRI=' + json.dumps(idx, ensure_ascii=False, separators=(',', ':')) + ';', encoding='utf-8')
    return idx

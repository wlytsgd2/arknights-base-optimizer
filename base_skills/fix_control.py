"""修复 layer2_control 的候选构建"""
import json, re, os
from itertools import combinations

DIR = os.path.dirname(os.path.abspath(__file__))

with open(os.path.join(DIR, 'all_facility_skills.json'), 'r', encoding='utf-8') as f:
    data = json.load(f)
with open(os.path.join(DIR, '..', 'char_table.json'), 'r', encoding='utf-8') as f:
    ct = json.load(f)

def cn(cid):
    if cid in ct and isinstance(ct[cid], dict):
        return ct[cid].get('name', cid)
    return cid

buffs = data['buffs']
ops_raw = data['operators']

# === 简化但正确的候选构建 ===
candidates = []
for cid, info in ops_raw.items():
    for elite in [0, 1, 2]:
        trade_bonus = 0.0
        mfg_bonus = 0.0
        gold_bonus = 0.0
        all_inter = []
        details = []

        for slot in info.get('slots', []):
            best_score = 0
            best_t = 0; best_m = 0; best_g = 0
            best_name = ''; best_inter = []

            for sk in slot['skills']:
                if sk['elite'] > elite:
                    continue
                b = buffs.get(sk['buffId'], {})
                if b.get('roomType', '') != 'CONTROL':
                    continue

                desc = b.get('description', '')
                name = b.get('name', '')
                t = 0; m = 0; g = 0; inter = []

                # 贸易全局
                if '所有贸易站' in desc and '订单效率' in desc:
                    pm = re.search(r'\+(\d+)%', desc)
                    if pm: t = float(pm.group(1))

                # 制造站 (排除红松: 贵金属-10%)
                if '制造站' in desc and '生产力' in desc:
                    if '红松' not in name:
                        if '贵金属' in desc:
                            pm = re.search(r'\+(\d+\.?\d*)%', desc)
                            if pm: g = float(pm.group(1))
                        else:
                            pm = re.search(r'\+(\d+)%', desc)
                            if pm: m = float(pm.group(1))

                # 中间产物
                for ip in ['人间烟火', '热情值', '感知信息', '木天蓼', '乌萨斯特饮', '情报储备']:
                    if ip in desc:
                        inter.append(ip)

                slot_score = t + m + g + len(inter) * 50
                if slot_score > best_score:
                    best_score = slot_score
                    best_t, best_m, best_g = t, m, g
                    best_name = name
                    best_inter = inter

            if best_name:
                trade_bonus = max(trade_bonus, best_t)
                mfg_bonus = max(mfg_bonus, best_m)
                gold_bonus = max(gold_bonus, best_g)
                all_inter.extend(best_inter)
                details.append('S{}:{} t{} m{} g{} i{}'.format(
                    slot['slotIndex'], best_name, best_t, best_m, best_g, ','.join(best_inter)))

        if trade_bonus > 0 or mfg_bonus > 0 or gold_bonus > 0 or all_inter:
            candidates.append({
                'charId': cid, 'elite': elite,
                'trade_bonus': trade_bonus, 'mfg_bonus': mfg_bonus, 'gold_bonus': gold_bonus,
                'intermediates': list(set(all_inter)),
                'details': ' | '.join(details),
            })

# 去重
best_op = {}
for c in candidates:
    k = c['charId']
    s = c['trade_bonus'] * 100 + c['mfg_bonus'] * 10 + c['gold_bonus'] * 5 + len(c['intermediates']) * 150
    if k not in best_op or s > best_op[k][0]:
        best_op[k] = (s, c)
operators = sorted(best_op.values(), key=lambda x: -x[0])

print('Total candidates:', len(operators))
for rank, (s, c) in enumerate(operators, 1):
    n = cn(c['charId'])
    inter = c.get('intermediates', [])
    print('{:2d}. {:8s} score={:4d} trade={:.0f} mfg={:.0f} gold={:.0f} inter={}'.format(
        rank, n, int(s), c['trade_bonus'], c['mfg_bonus'], c['gold_bonus'], inter))

# 全量枚举
best_set = None
best_val = 0
best_products = set()
for quint in combinations([o[1] for o in operators], 5):
    ol = list(quint)
    tt = max(o['trade_bonus'] for o in ol)
    tm = max(o['mfg_bonus'] for o in ol)
    tg = max(o['gold_bonus'] for o in ol)
    ai = set()
    for o in ol:
        for ip in o.get('intermediates', []):
            ai.add(ip)
    v = tt * 100 + tm * 10 + tg * 5 + len(ai) * 150
    if v > best_val:
        best_val = v
        best_set = ol
        best_products = ai

print('\nBest value:', best_val)
print('Products:', best_products)
for op in best_set:
    print('  {}(E{}): trade={} mfg={} gold={} inter={}'.format(
        cn(op['charId']), op['elite'],
        op['trade_bonus'], op['mfg_bonus'], op['gold_bonus'],
        op['intermediates']))

"""
控制中枢求解器 — 5人选, 全局buff
评分: 按优先级 贸易buff × 制造buff
"""
import json, re, os
from itertools import combinations

DIR = os.path.dirname(os.path.abspath(__file__))

with open(os.path.join(DIR, 'all_facility_skills.json'), 'r', encoding='utf-8') as f:
    data = json.load(f)
with open(os.path.join(DIR, '..', 'char_table.json'), 'r', encoding='utf-8') as f:
    char_table = json.load(f)

buffs = data['buffs']
ops = data['operators']

def cn(cid):
    if cid in char_table and isinstance(char_table[cid], dict):
        return char_table[cid].get('name', cid)
    return cid

# === 解析每个干员的中枢贡献 ===
candidates = []
for cid, info in ops.items():
    for elite in [0, 1, 2]:
        mfg_bonus = 0.0    # 制造站生产力加成
        trade_bonus = 0.0  # 贸易站效率加成
        trade_cond = []    # 贸易站条件加成(不计入基础)
        intermediates = [] # 中间产物
        details = []

        for slot in info.get('slots', []):
            best_mfg = 0; best_trade = 0; best_name = ''
            best_inter = []
            for sk in slot['skills']:
                if sk['elite'] > elite: continue
                b = buffs.get(sk['buffId'], {})
                if b.get('roomType', '') != 'CONTROL': continue
                desc = re.sub(r'<[^>]+>', '', b.get('description', ''))
                name = b.get('name', '')

                m = 0; t = 0; inter = []

                # 制造站buff (仅正向, 排除贵金属惩罚)
                if '贵金属' in desc and '制造站' in desc and '生产力' in desc:
                    pm = re.search(r'生产力\+(\d+\.?\d*)%', desc)
                    if pm and '红松' not in name: m = float(pm.group(1))  # 排除红松(-10%贵金属)
                elif '制造站' in desc and '生产力' in desc:
                    if '红松' not in name:  # 红松对贵金属是-10%
                        pm = re.search(r'生产力\+(\d+)%', desc)
                        if pm: m = float(pm.group(1))

                # 贸易站buff (全局, 排除负效率)
                if '所有贸易站' in desc and '订单效率' in desc:
                    tm = re.search(r'\+(\d+)%', desc)
                    if tm: t = float(tm.group(1))

                # 中间产物
                for ip in ['人间烟火', '热情值', '感知信息', '乌萨斯特饮', '情报储备', '木天蓼']:
                    if ip in desc: inter.append(ip)

                score = m + t  # 简单评分
                best_score = best_mfg + best_trade
                if score > best_score:
                    best_mfg, best_trade, best_name, best_inter = m, t, name, inter

            if best_name:
                mfg_bonus = max(mfg_bonus, best_mfg)  # 同种取最高
                trade_bonus = max(trade_bonus, best_trade)
                intermediates.extend(best_inter)
                tags = []
                if best_mfg > 0: tags.append('制+{:.0f}%'.format(best_mfg))
                if best_trade > 0: tags.append('贸+{:.0f}%'.format(best_trade))
                if best_inter: tags.append('中:' + ','.join(best_inter))
                details.append('S{}:{}('.format(slot['slotIndex'], best_name) + ','.join(tags) + ')')

        if details:
            candidates.append({
                'charId': cid, 'elite': elite,
                'mfg_bonus': mfg_bonus, 'trade_bonus': trade_bonus,
                'intermediates': intermediates,
                'details': ' + '.join(details),
            })

# 去重
best_op = {}
for c in candidates:
    k = c['charId']
    score = c['mfg_bonus'] * 5 + c['trade_bonus'] * 10  # 贸易权重大
    if k not in best_op: best_op[k] = (score, c)
    elif score > best_op[k][0]: best_op[k] = (score, c)
operators = sorted(best_op.values(), key=lambda x: -(x[1]['mfg_bonus']*5 + x[1]['trade_bonus']*10))

# === 选5人 ===
n_ops = len(operators)
print('中枢候选: {} 人'.format(n_ops))
print()
print('候选干员 (按贡献排序):')
for i, (_, op) in enumerate(operators[:15], 1):
    print('  {:2d}. {}(E{}) 制+{:.0f}% 贸+{:.0f}%  [{}]'.format(i, cn(op['charId']), op['elite'], op['mfg_bonus'], op['trade_bonus'], op['details']))

# 枚举5人组 — 同种取最高, 覆盖不同类别即可
# 简单策略: 选最好的1个贸易buff + 最好的1个制造buff + 其余选中间产物
best_trade_op = max(operators, key=lambda x: (x[1]['trade_bonus'], x[1]['mfg_bonus']))
best_mfg_op = max(operators, key=lambda x: (x[1]['mfg_bonus'], x[1]['trade_bonus']))

# 如果同一人能覆盖两样更好
used = set()
best_set = []

# 1st: 最好的双修(贸易+制造)
dual_ops = [(s, op) for s, op in operators if op['mfg_bonus'] > 0 and op['trade_bonus'] > 0]
if dual_ops:
    best_dual = max(dual_ops, key=lambda x: x[1]['trade_bonus'] * 10 + x[1]['mfg_bonus'])
    best_set.append(best_dual[1])
    used.add(best_dual[1]['charId'])

# 2nd-5th: 补漏 + 中间产物
for s, op in operators:
    if op['charId'] in used: continue
    if len(best_set) >= 5: break
    best_set.append(op)

max_mfg = max(op['mfg_bonus'] for op in best_set)
max_trade = max(op['trade_bonus'] for op in best_set)

print()
print('=== 最优5人中权 (同种取最高, 不堆叠) ===')
print('制造站总加成: +{:.0f}%'.format(max_mfg))
print('贸易站总加成: +{:.0f}%'.format(max_trade))
print('注: 多个+7%贸易buff只生效一个, 其余位置可放中间产物/心情管理')
for op in best_set:
    print('  {}(E{}) [{}]'.format(cn(op['charId']), op['elite'], op['details']))

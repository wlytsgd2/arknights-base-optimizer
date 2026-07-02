"""
赤金最高生产力三人组 — 通用求解器

基于解包双槽位模型 (building_data.json → operator_skills_raw.json)
版本参数控制已实现技能类别。
"""
import json, re, os, sys
from itertools import combinations

DIR = os.path.dirname(os.path.abspath(__file__))

# ============================================================
# 配置
# ============================================================
VERSION = 2                    # 当前版本号
HOURS = float(sys.argv[1]) if len(sys.argv) > 1 else 12.0

# 各版本已实现的技能类别
CATEGORIES = {
    1: {'纯数值'},
    2: {'纯数值', '渐进加成'},
    # 3: {'纯数值', '渐进加成', '设施数量'},
    # ...以此类推
}

IMPLEMENTED = CATEGORIES.get(VERSION, set())

# ============================================================
# 加载数据
# ============================================================
with open(os.path.join(DIR, 'operator_skills_raw.json'), 'r', encoding='utf-8') as f:
    ops_raw = json.load(f)

with open(os.path.join(DIR, 'manufacturing_skills.json'), 'r', encoding='utf-8') as f:
    mfg_skills = json.load(f)

skill_meta = {}
for s in mfg_skills:
    skill_meta[s['name']] = {
        'category': s['category'],
        'recipe': s['recipe'],
        'id': s['id'],
        'desc': s['desc'],
    }

# ============================================================
# 产能计算
# ============================================================
def extract_prod(desc):
    """从描述中提取生产力百分比 (兼容 <@cc.*></> 标记)"""
    m = re.search(r'([+-]\d+(?:\.\d+)?%)', desc)
    return float(m.group(1).replace('%', '').replace('+', '')) if m else None

def calc_ramp_avg(desc, hours):
    """计算渐进加成的时段平均产能。描述含 <@cc.*></> 标记。"""
    t = int(hours)

    # 模式1: 首小时+X%，此后每小时+Y%，最终达到+Z%
    m1 = re.search(r'首小时.*?([+-]\d+)%.*?此后每小时.*?([+-]\d+)%.*?最终达到.*?([+-]\d+)%', desc)
    if m1:
        start = float(m1.group(1))
        step = float(m1.group(2))
        cap = float(m1.group(3))
        total = sum(min(start + step * (h - 1), cap) for h in range(1, t + 1))
        return total / t

    # 模式2: 每小时+X%，最终达到+Z%（无首小时优惠）
    m2 = re.search(r'每小时.*?([+-]\d+)%.*?最终达到.*?([+-]\d+)%', desc)
    if m2:
        step = float(m2.group(1))
        cap = float(m2.group(2))
        total = sum(min(step * h, cap) for h in range(1, t + 1))
        return total / t

    return None

def calc_slot_prod(slot_skills, elite, hours):
    """计算某个槽位在指定精英阶段下的有效产能"""
    best = None
    for sk in slot_skills:
        if sk['elite'] > elite:
            continue
        if sk['roomType'] not in ('MANUFACTURE', 'NONE', ''):
            continue

        name = sk['buffName']
        meta = skill_meta.get(name, {})
        cat = meta.get('category', '')
        recipe = meta.get('recipe', '')
        desc = sk['description']

        if cat not in IMPLEMENTED:
            continue
        if recipe not in ('gold', 'any'):
            continue

        # 计算产能
        if cat == '纯数值':
            prod = extract_prod(desc)
        elif cat == '渐进加成':
            prod = calc_ramp_avg(desc, hours)
        else:
            prod = None  # 未实现的类别

        if prod is None or prod <= 0:
            continue

        if best is None or sk['elite'] >= best['elite']:
            best = {**sk, 'prod': prod, 'recipe': recipe, 'category': cat}

    return best

# ============================================================
# 汇总所有干员
# ============================================================
candidates = []

for char_id, info in ops_raw.items():
    slots = info.get('slots', [])
    for elite in [0, 1, 2]:
        total_prod = 0.0
        details = []
        for slot in slots:
            best = calc_slot_prod(slot['skills'], elite, HOURS)
            if best:
                total_prod += best['prod']
                details.append(f'S{slot["slotIndex"]}:{best["buffName"]}({best["prod"]:+.0f}%)')
        if total_prod > 0:
            candidates.append({
                'charId': char_id, 'elite': elite,
                'total_prod': total_prod,
                'details': ' + '.join(details),
            })

# 去重
best_op = {}
for c in candidates:
    k = c['charId']
    if k not in best_op or c['total_prod'] > best_op[k]['total_prod']:
        best_op[k] = c
operators = sorted(best_op.values(), key=lambda x: -x['total_prod'])

# 枚举
results = []
for trio in combinations(operators, 3):
    total = sum(op['total_prod'] for op in trio)
    results.append({'total': total, 'ops': trio})
results.sort(key=lambda x: -x['total'])

# ============================================================
# 输出
# ============================================================
dual_ops = [op for op in operators if ' + ' in op['details']]

out = []
out.append('=' * 70)
out.append(f'  赤金最高生产力三人组 — V{VERSION}  {", ".join(sorted(IMPLEMENTED))}')
out.append(f'  在岗 {HOURS:.0f}h  |  双槽位模型')
out.append('=' * 70)
out.append('')

if '渐进加成' in IMPLEMENTED:
    out.append(f'渐进加成技能 ({HOURS:.0f}h 平均):')
    for op in operators:
        if any('渐进加成' in str(s) for s in [op]):
            pass
    # List all ramp-up operators
    for op in operators:
        for c in candidates:
            if c['charId'] == op['charId'] and c['elite'] == op['elite']:
                if '渐进加成' in str(c):
                    pass

out.append(f'候选干员: {len(operators)} 人')
if dual_ops:
    out.append(f'其中双槽叠加: {len(dual_ops)} 人')
out.append(f'三人组总数: {len(results)}')
out.append('')

if dual_ops:
    out.append('双槽位叠加干员:')
    for op in dual_ops:
        out.append(f'  {op["charId"]:30s} E{op["elite"]}  {op["total_prod"]:+.0f}%  [{op["details"]}]')
    out.append('')

out.append('-' * 70)
out.append(f'{"排名":<5} {"总产能":<8} {"组合"}')
out.append('-' * 70)

for rank, r in enumerate(results[:20], 1):
    names = ' + '.join(f'{op["charId"]}(E{op["elite"]})' for op in r['ops'])
    detail = ' | '.join(f'{op["details"]} = {op["total_prod"]:+.0f}%' for op in r['ops'])
    out.append(f'{rank:<5} {r["total"]:+.0f}%     {names}')
    out.append(f'       → {detail}')

out.append('')
# Compare with previous version
prev_versions = [v for v in sorted(CATEGORIES.keys()) if v < VERSION]
if prev_versions:
    prev_v = prev_versions[-1]
    out.append(f'对比 V{prev_v} ({", ".join(sorted(CATEGORIES[prev_v]))}):')
    if results[0]['total'] > 95:  # V1 baseline
        out.append(f'  ⬆ 突破 V{prev_v} 上限')
    else:
        out.append(f'  — 未突破')

out.append('')
out.append('-' * 70)
out.append('所有候选干员 (按产能排序):')
for i, op in enumerate(operators, 1):
    out.append(f'  {i:3d}. {op["charId"]:30s} E{op["elite"]}  {op["total_prod"]:+.0f}%  [{op["details"]}]')

result = '\n'.join(out)
output_path = os.path.join(DIR, f'output_v{VERSION}_{int(HOURS)}h.txt')
with open(output_path, 'w', encoding='utf-8') as f:
    f.write(result)

print(f'V{VERSION}  H={HOURS:.0f}h  candidates={len(operators)}  combos={len(results)}  Top1={results[0]["total"]:+.0f}%')
print(f'Output: {output_path}')

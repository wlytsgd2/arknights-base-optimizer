"""
赤金最高生产力三人组 — V2 纯数值 + 渐进加成

新增 5 条渐进技能，默认在岗时间 12h。
"""
import json, re, os, sys
from itertools import combinations

DIR = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(DIR, 'manufacturing_skills.json')

HOURS = float(sys.argv[1]) if len(sys.argv) > 1 else 12.0

with open(DATA, 'r', encoding='utf-8') as f:
    all_skills = json.load(f)

# ============================================================
# 1. 计算有效产能
# ============================================================
def calc_effective_prod(skill, hours):
    """根据技能描述和在岗时间，计算有效生产力"""
    d = skill['desc']
    cat = skill['category']

    # 纯数值：固定值
    if cat == '纯数值':
        m = re.search(r'生产力([+-]\d+(?:\.\d+)?%)', d)
        if m:
            return float(m.group(1).replace('%', '').replace('+', ''))
        return None

    # 渐进加成：按小时积分，取全时段平均值
    if cat == '渐进加成':
        t = int(hours)
        # 模式1: 首小时+X%，此后每小时+Y%，最终达到+Z%
        m1 = re.search(r'首小时([+-]\d+)%.*此后每小时([+-]\d+)%.*最终达到([+-]\d+)%', d)
        if m1:
            start = float(m1.group(1))
            step = float(m1.group(2))
            cap = float(m1.group(3))
            total = 0.0
            for h in range(1, t + 1):
                prod_h = min(start + step * (h - 1), cap)
                total += prod_h
            return total / t

        # 模式2: 每小时+X%，最终达到+Z%  (无首小时优惠，从0开始)
        m2 = re.search(r'每小时([+-]\d+)%.*最终达到([+-]\d+)%', d)
        if m2:
            step = float(m2.group(1))
            cap = float(m2.group(2))
            total = 0.0
            for h in range(1, t + 1):
                prod_h = min(step * h, cap)
                total += prod_h
            return total / t

        return None

    return None


# ============================================================
# 2. 筛选：纯数值 + 渐进加成，赤金/通用
# ============================================================
implemented = {'纯数值', '渐进加成'}

candidates = []
skipped = []

for s in all_skills:
    if s['category'] not in implemented:
        continue
    if s['recipe'] not in ('gold', 'any'):
        continue

    prod = calc_effective_prod(s, HOURS)
    if prod is None or prod <= 0:
        skipped.append(s)
        continue

    for op in s['operators']:
        candidates.append({
            'operator': op['name'],
            'elite': op['elite'],
            'skill_id': s['id'],
            'skill_name': s['name'],
            'prod': prod,
            'category': s['category'],
            'recipe': s['recipe'],
        })

# ============================================================
# 3. 去重：每名干员取最优技能
# ============================================================
best = {}
for c in candidates:
    key = c['operator']
    if key not in best or c['prod'] > best[key]['prod']:
        best[key] = c
operators = list(best.values())

# ============================================================
# 4. 枚举三人组
# ============================================================
results = []
for trio in combinations(operators, 3):
    names = [op['operator'] for op in trio]
    if len(names) != len(set(names)):
        continue
    total = sum(op['prod'] for op in trio)
    results.append({'total': total, 'ops': trio})
results.sort(key=lambda x: -x['total'])

# ============================================================
# 5. 输出
# ============================================================
OUTPUT = os.path.join(DIR, f'output_v2_{int(HOURS)}h.txt')
out = []
out.append('=' * 70)
out.append(f'  赤金最高生产力三人组 — V2 纯数值 + 渐进加成  (在岗 {HOURS:.0f}h)')
out.append('=' * 70)
out.append('')

# 列出所有渐进技能的有效产能
out.append('渐进加成技能 ({}h):'.format(HOURS))
for s in all_skills:
    if s['category'] == '渐进加成' and s['recipe'] in ('gold', 'any'):
        eff = calc_effective_prod(s, HOURS)
        ops = ', '.join(f'{o["name"]}(精{o["elite"]})' for o in s['operators'])
        out.append(f'  #{s["id"]} {s["name"]:10s} → 有效产能 {eff:+.0f}%  ({ops})')
out.append('')

out.append(f'候选干员: {len(operators)} 人')
out.append(f'三人组总数: {len(results)}')
out.append('')
out.append('-' * 70)
out.append(f'{"排名":<5} {"总产能":<8} {"组合"}')
out.append('-' * 70)

for rank, r in enumerate(results[:20], 1):
    names = ' + '.join(f'{op["operator"]}(精{op["elite"]})' for op in r['ops'])
    details = ' | '.join(f'{op["skill_name"]}[{op["category"]}] {op["prod"]:+.0f}%' for op in r['ops'])
    out.append(f'{rank:<5} {r["total"]:+.0f}%     {names}')
    out.append(f'       → {details}')

out.append('')
# Check if top changed
v1_top = '+95%'
if results[0]['total'] > 95:
    out.append(f'⬆ 突破V1上限(+95%) → 新上限 {results[0]["total"]:+.0f}%')
else:
    out.append(f'— 未突破V1上限(+95%)')

result = '\n'.join(out)
with open(OUTPUT, 'w', encoding='utf-8') as f:
    f.write(result)

print(f'Hours={HOURS:.0f}  候选: {len(operators)}人  Top1: {results[0]["total"]:+.0f}%')
print(f'Output: {OUTPUT}')

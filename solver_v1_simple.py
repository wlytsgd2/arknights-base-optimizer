"""
V1: 仅考虑简单技能 — 纯数值加成，无条件，无特殊机制
"""
import json, sys, os
from itertools import combinations

DIR = os.path.dirname(os.path.abspath(__file__))

with open(os.path.join(DIR, 'manufacturing_skills.json'), 'r', encoding='utf-8') as f:
    all_skills = json.load(f)

out = []

# === 严格筛选: 无条件 + 贵金属/通用 + 正向生产力 ===
candidates = []
for s in all_skills:
    if s['recipe'] not in ('gold', 'any'):
        continue
    if not s['prod_flat']:
        continue
    prod_val = float(s['prod_flat'].replace('%', '').replace('+', ''))
    if prod_val <= 0:
        continue
    has_any_condition = any([
        s['coop_with'], s['prod_per_facility'], s['prod_per_dorm'],
        s['prod_per_training'], s['prod_per_faction'], s['prod_per_same_op'],
        s['prod_per_skill_class'], s['zero_out'], s['mood_gap'], s['skill_merge'],
        s['wh_to_prod'], s['intermediates'], s['external_cond'],
        s['prod_ramp'], s['eliminate_mood'], s['wh_per_skill_class'],
    ])
    if has_any_condition:
        continue
    if '每有' in s['desc']:
        continue

    for op in s['operators']:
        candidates.append({
            'name': op['name'], 'elite': op['elite'],
            'skill_name': s['name'], 'skill_id': s['id'],
            'prod': prod_val, 'mood': s['mood'], 'warehouse': s['warehouse'],
        })

out.append(f'候选干员-技能组合: {len(candidates)} 条')
for c in sorted(candidates, key=lambda x: -x['prod']):
    out.append(f'  {c["name"]:12s}(精{c["elite"]}) prod={c["prod"]:+.0f}%  [{c["skill_name"]}]')

# === 去重 ===
best_skill = {}
for c in candidates:
    key = c['name']
    if key not in best_skill or c['prod'] > best_skill[key]['prod']:
        best_skill[key] = c
operators = list(best_skill.values())
out.append(f'\n去重后干员: {len(operators)} 人')

# === 枚举三人组 ===
results = []
for trio in combinations(operators, 3):
    names = [op['name'] for op in trio]
    if len(names) != len(set(names)):
        continue
    total_prod = sum(op['prod'] for op in trio)
    results.append({
        'total_prod': total_prod,
        'names': ' + '.join(f'{op["name"]:8s}(精{op["elite"]})' for op in trio),
        'details': ' | '.join(f'{op["skill_name"]}({op["prod"]:+.0f}%)' for op in trio),
    })
results.sort(key=lambda x: x['total_prod'], reverse=True)

# === 输出 ===
out.append(f'\n===== TOP 20 赤金三人组 (仅简单技能, {len(operators)}人选3) =====')
out.append(f'{"排名":<4} {"生产力":<8} {"组合"}')
out.append('-' * 90)
for i, r in enumerate(results[:20], 1):
    out.append(f'{i:<4} {r["total_prod"]:+.0f}%    {r["names"]}')
    out.append(f'      → {r["details"]}')

output = '\n'.join(out)
with open(os.path.join(DIR, 'output_v1.txt'), 'w', encoding='utf-8') as f:
    f.write(output)
print('Done! Output saved to output_v1.txt')
print(f'Top result: {results[0]["total_prod"]:+.0f}% — {results[0]["names"]}')

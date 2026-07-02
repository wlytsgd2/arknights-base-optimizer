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
VERSION = 6                    # 当前版本号
HOURS = float(sys.argv[1]) if len(sys.argv) > 1 else 12.0

# 基建配置
TRADING_POSTS = 2
POWER_PLANTS = 3
DORMS = 4
DORM_LEVEL = 5       # 每间宿舍等级(满级5000氛围=5级)
TRAINING_LEVEL = 3   # 训练室等级

# 各版本已实现的技能类别
CATEGORIES = {
    1: {'纯数值'},
    2: {'纯数值', '渐进加成'},
    3: {'纯数值', '渐进加成', '设施数量'},
    4: {'纯数值', '渐进加成', '设施数量', 'COOP同站'},
    5: {'纯数值', '渐进加成', '设施数量', 'COOP同站', '小队加成'},
    6: {'纯数值', '渐进加成', '设施数量', 'COOP同站', '小队加成', '技能联动'},
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
        'prod_per_facility': s.get('prod_per_facility'),
        'prod_per_dorm': s.get('prod_per_dorm'),
        'prod_per_training': s.get('prod_per_training'),
        'coop_with': s.get('coop_with'),
    }

# 建立 buffName → 中文名 的映射 (用于COOP判定)
buff_to_cn = {}
for s in mfg_skills:
    for op in s['operators']:
        if s['name'] not in buff_to_cn:
            buff_to_cn[s['name']] = []
        buff_to_cn[s['name']].append(op['name'])

# 建立 charId → {elite: [buffNames]} 的完整技能表 (用于COOP反向查找)
char_skills = {}
for char_id, info in ops_raw.items():
    char_skills[char_id] = {}
    for slot in info['slots']:
        for sk in slot['skills']:
            e = sk['elite']
            if e not in char_skills[char_id]:
                char_skills[char_id][e] = []
            char_skills[char_id][e].append(sk['buffName'])

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

def calc_facility_prod(meta):
    """计算设施数量类技能的产能。优先用元数据，否则解析描述。"""
    pf = meta.get('prod_per_facility')
    if pf:
        count = TRADING_POSTS if pf['type'] == 'trading_post' else POWER_PLANTS
        return float(pf['value'].replace('%', '').replace('+', '')) * count

    pd = meta.get('prod_per_dorm')
    if pd:
        return float(pd['value'].replace('%', '').replace('+', '')) * DORMS * DORM_LEVEL

    pt = meta.get('prod_per_training')
    if pt:
        raw = float(pt['value'].replace('%', '').replace('+', '')) * TRAINING_LEVEL
        cap = float(pt['max'].replace('%', '')) if pt.get('max') else raw
        return min(raw, cap)

    # 回退: 从描述中解析
    desc = meta.get('desc', '')
    if '训练室每级' in desc:
        m = re.search(r'([+-]\d+)%.*?生产力', desc)
        if not m: m = re.search(r'生产力.*?([+-]\d+)%', desc)
        if m:
            raw = float(m.group(1).replace('+', '')) * TRAINING_LEVEL
            max_m = re.search(r'最多(\d+)%', desc)
            cap = float(max_m.group(1)) if max_m else raw
            return min(raw, cap)

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
        coop_requires = None
        skill_class = meta.get('skill_class', 'other')
        is_dynamic = False   # 需要枚举时计算的技能
        dynamic_type = None

        if cat == '纯数值':
            prod = extract_prod(desc)
        elif cat == '渐进加成':
            prod = calc_ramp_avg(desc, hours)
        elif cat == '设施数量':
            prod = calc_facility_prod(meta)
        elif cat == 'COOP同站':
            prod = extract_prod(desc)
            if prod:
                coop_match = re.search(r'当与(.+?)在同一个制造站', desc)
                if coop_match:
                    coop_requires = coop_match.group(1).strip()
        elif cat == '小队加成':
            # #74 重聚时光: 每个A1小队干员+10%, 包括自身
            is_dynamic = True
            dynamic_type = 'a1_squad'
            prod = 0  # 基础为0, 枚举时计算
        elif cat == '技能联动':
            if '配合意识' in name or '每5%生产力' in desc:
                # #46: 其他干员每5%产能→+5%, max+40%
                is_dynamic = True
                dynamic_type = 'synergy_multiply'
                prod = 0
            elif '每个' in desc and '类技能' in desc:
                # #27 #69 #70: 每个X类技能+5%
                is_dynamic = True
                dynamic_type = 'per_skill_class'
                prod = 0
            else:
                prod = extract_prod(desc)  # fallback
        else:
            prod = None

        if prod is None:
            continue
        if prod <= 0 and not is_dynamic:  # 动态技能允许prod=0
            continue

        if best is None or sk['elite'] >= best['elite']:
            best = {**sk, 'prod': prod, 'recipe': recipe, 'category': cat,
                    'coop_requires': coop_requires, 'skill_class': skill_class,
                    'is_dynamic': is_dynamic, 'dynamic_type': dynamic_type}

    return best

# ============================================================
# 汇总所有干员
# ============================================================
# A1小队成员
A1_SQUAD = {'芬', '克洛丝', '米格鲁', '炎熔', '芙蓉', '历阵锐枪芬', '寒芒克洛丝'}
char_cn = {}
for char_id, info in ops_raw.items():
    for slot in info['slots']:
        for sk in slot['skills']:
            names = buff_to_cn.get(sk['buffName'], [])
            if names:
                char_cn[char_id] = names[0]
                break
        if char_id in char_cn:
            break

candidates = []

for char_id, info in ops_raw.items():
    cn_name = char_cn.get(char_id, char_id)
    slots = info.get('slots', [])
    for elite in [0, 1, 2]:
        total_prod = 0.0
        non_fac_prod = 0.0  # 不含设施加成的产能(用于配合意识)
        details = []
        coop_needs = []
        skill_classes = []
        dynamic_slots = []
        for slot in slots:
            best = calc_slot_prod(slot['skills'], elite, HOURS)
            if best:
                if best.get('is_dynamic'):
                    dynamic_slots.append(best)
                    details.append(f'S{slot["slotIndex"]}:{best["buffName"]}(动态)')
                else:
                    total_prod += best['prod']
                    is_fac = best.get('category') == '设施数量'
                    if not is_fac:
                        non_fac_prod += best['prod']
                    tag = '[设]' if is_fac else ''
                    details.append(f'S{slot["slotIndex"]}:{best["buffName"]}{tag}({best["prod"]:+.0f}%)')
                if best.get('coop_requires'):
                    coop_needs.append(best['coop_requires'])
                if best.get('skill_class') and best['skill_class'] != 'other':
                    skill_classes.append(best['skill_class'])
        if total_prod > 0 or coop_needs or dynamic_slots:
            candidates.append({
                'charId': char_id, 'cn_name': cn_name, 'elite': elite,
                'total_prod': total_prod,
                'base_prod': total_prod,
                'non_fac_prod': non_fac_prod,
                'details': ' + '.join(details) if details else f'(需COOP)',
                'coop_needs': coop_needs,
                'skill_classes': skill_classes,
                'dynamic_slots': dynamic_slots,
                'is_a1': cn_name in A1_SQUAD,
            })

# 去重: 每干员取最高产能, 平局时取高精英(动态技能多)
best_op = {}
for c in candidates:
    k = c['charId']
    if k not in best_op:
        best_op[k] = c
    elif c['total_prod'] > best_op[k]['total_prod']:
        best_op[k] = c
    elif c['total_prod'] == best_op[k]['total_prod']:
        # 平局时: 选精英更高或有动态技能的
        if c['elite'] > best_op[k]['elite']:
            best_op[k] = c
        elif c.get('dynamic_slots') and not best_op[k].get('dynamic_slots'):
            best_op[k] = c
operators = sorted(best_op.values(), key=lambda x: -x['total_prod'])

# ============================================================
# 枚举 + 动态技能判定
# ============================================================
def resolve_trio(trio):
    """给定三人组, 解析所有动态技能, 返回总产能"""
    trio_names = {op['cn_name'] for op in trio}

    # 先解析COOP
    resolved_prod = []
    for op in trio:
        prod = op['base_prod']
        for need in op.get('coop_needs', []):
            if need not in trio_names:
                prod = 0  # COOP失败, 基础产能归零
                break
        resolved_prod.append(prod)

    # 统计 A1 人数 (用于重聚时光)
    a1_count = sum(1 for op in trio if op.get('is_a1'))

    # 统计各类技能数量 (用于技能联动)
    class_counts = {}
    for op in trio:
        for sc in op.get('skill_classes', []):
            class_counts[sc] = class_counts.get(sc, 0) + 1

    # 解析动态技能
    final_prods = list(resolved_prod)
    for i, op in enumerate(trio):
        for ds in op.get('dynamic_slots', []):
            dtype = ds.get('dynamic_type')
            bonus = 0
            if dtype == 'a1_squad':
                bonus = a1_count * 10.0  # 每个A1成员+10%
            elif dtype == 'per_skill_class':
                # 从描述中提取目标技能类别
                desc = ds.get('description', '')
                target_class = None
                if '金属工艺' in desc:
                    target_class = 'metal'
                elif '莱茵科技' in desc:
                    target_class = 'rhine'
                elif '标准化' in desc:
                    target_class = 'standard'
                if target_class:
                    count = class_counts.get(target_class, 0)
                    bonus = count * 5.0
            elif dtype == 'synergy_multiply':
                # #46 配合意识: 其他干员每5%非设施产能→+5%, max+40%
                other_non_fac = 0
                for j, other in enumerate(trio):
                    if j == i:
                        continue
                    other_non_fac += other.get('non_fac_prod', 0)
                bonus = min(int(other_non_fac / 5) * 5, 40)
            final_prods[i] += bonus

    return sum(final_prods), final_prods

results = []
for trio in combinations(operators, 3):
    total, _ = resolve_trio(trio)
    if total > 0:
        results.append({'total': total, 'ops': trio})
results.sort(key=lambda x: -x['total'])

# ============================================================
# 输出
# ============================================================
dual_ops = [op for op in operators if ' + ' in op['details']]

out = []
out.append('=' * 70)
out.append(f'  赤金最高生产力三人组 — V{VERSION}  {", ".join(sorted(IMPLEMENTED))}')
out.append(f'  在岗 {HOURS:.0f}h  |  基建: {TRADING_POSTS}贸易站 {POWER_PLANTS}发电站 {DORMS}宿舍x{DORM_LEVEL}级 训练室{TRAINING_LEVEL}级')
out.append('=' * 70)
out.append('')

if '设施数量' in IMPLEMENTED:
    out.append('设施数量技能:')
    for s in mfg_skills:
        if s.get('category') == '设施数量' and s['recipe'] in ('gold', 'any'):
            prod = calc_facility_prod(s) or 0
            ops = ', '.join(f'{o["name"]}(精{o["elite"]})' for o in s['operators'])
            out.append(f'  #{s["id"]} {s["name"]:12s} → {prod:+.0f}%  ({ops})')
    out.append('')

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
    total, resolved = resolve_trio(r['ops'])
    cn = lambda op: op.get('cn_name', op['charId'])
    names = ' + '.join(f'{cn(op)}(E{op["elite"]})' for op in r['ops'])
    parts = []
    for i, op in enumerate(r['ops']):
        bonus = resolved[i] - op['base_prod']
        if bonus > 0:
            parts.append(f'{cn(op)}:{op["base_prod"]:+.0f}%+{bonus:+.0f}%')
        else:
            parts.append(f'{cn(op)}:{resolved[i]:+.0f}%')
    detail = ' | '.join(parts)
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

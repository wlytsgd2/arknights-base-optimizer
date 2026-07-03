"""
通用求解器核心 — 支持任意设施类型

用法:
  from solver_core import solve
  result = solve(room='MANUFACTURE', recipe='gold', hours=12)
"""
import json, re, os, sys
from itertools import combinations

DIR = os.path.dirname(os.path.abspath(__file__))

# 基建配置
TRADING_POSTS = 2
POWER_PLANTS = 3
DORMS = 4
DORM_LEVEL = 5
TRAINING_LEVEL = 3
ROBOTS = 64

# A1小队
A1_SQUAD = {'芬', '克洛丝', '米格鲁', '炎熔', '芙蓉', '历阵锐枪芬', '寒芒克洛丝'}

# ============================================================
# 数据加载
# ============================================================
def load_data():
    with open(os.path.join(DIR, 'all_facility_skills.json'), 'r', encoding='utf-8') as f:
        return json.load(f)

# ============================================================
# 产能提取工具
# ============================================================
def extract_pct(desc):
    """从描述中提取百分比数值"""
    m = re.search(r'([+-]\d+(?:\.\d+)?%)', desc)
    return float(m.group(1).replace('%', '').replace('+', '')) if m else None

def calc_ramp_avg(desc, hours):
    """渐进加成平均产能"""
    t = int(hours)
    m1 = re.search(r'首小时.*?([+-]\d+)%.*?此后每小时.*?([+-]\d+)%.*?最终达到.*?([+-]\d+)%', desc)
    if m1:
        s, step, cap = float(m1.group(1)), float(m1.group(2)), float(m1.group(3))
        return sum(min(s + step * (h - 1), cap) for h in range(1, t + 1)) / t
    m2 = re.search(r'每小时.*?([+-]\d+)%.*?最终达到.*?([+-]\d+)%', desc)
    if m2:
        step, cap = float(m2.group(1)), float(m2.group(2))
        return sum(min(step * h, cap) for h in range(1, t + 1)) / t
    return None

# ============================================================
# 干员产能计算
# ============================================================
def build_candidates(data, room, recipe, hours, categories):
    """构建候选干员列表"""
    ops_raw = data['operators']
    candidates = []

    for char_id, info in ops_raw.items():
        cn_name = _get_cn_name(info, data)
        slots = info.get('slots', [])
        for elite in [0, 1, 2]:
            total_prod = 0.0
            non_fac_prod = 0.0
            total_wh = 0
            details = []
            dynamic_slots = []
            skill_classes = []
            coop_needs = []

            for slot in slots:
                best = _slot_best(slot['skills'], elite, room, recipe, hours, categories, data)
                if not best:
                    continue
                if best['is_dynamic']:
                    dynamic_slots.append(best)
                    details.append(f'S{slot["slotIndex"]}:{best["buffName"]}(动态)')
                else:
                    total_prod += best['prod']
                    total_wh += best['warehouse']
                    is_fac = best.get('category') == '设施数量'
                    if not is_fac:
                        non_fac_prod += best['prod']
                    tag = '[设]' if is_fac else ''
                    details.append(f'S{slot["slotIndex"]}:{best["buffName"]}{tag}({best["prod"]:+.0f}%)')
                if best.get('coop_requires'):
                    coop_needs.append(best['coop_requires'])
                if best.get('skill_class') and best['skill_class'] != 'other':
                    skill_classes.append(best['skill_class'])

            if total_prod > 0 or dynamic_slots:
                candidates.append({
                    'charId': char_id, 'cn_name': cn_name, 'elite': elite,
                    'base_prod': total_prod, 'non_fac_prod': non_fac_prod,
                    'total_wh': total_wh, 'details': ' + '.join(details),
                    'coop_needs': coop_needs, 'skill_classes': skill_classes,
                    'dynamic_slots': dynamic_slots,
                    'is_a1': cn_name in A1_SQUAD,
                })

    # 去重
    best_op = {}
    for c in candidates:
        k = c['charId']
        if k not in best_op: best_op[k] = c
        elif c['base_prod'] > best_op[k]['base_prod']: best_op[k] = c
        elif c['base_prod'] == best_op[k]['base_prod'] and c['elite'] > best_op[k]['elite']:
            best_op[k] = c
    return sorted(best_op.values(), key=lambda x: -x['base_prod'])

# ============================================================
# 三人组解析
# ============================================================
def resolve_trio(trio, data):
    """解析三人组的动态技能, 返回(总产能, 各人产能)"""
    trio_names = {op['cn_name'] for op in trio}

    # COOP
    resolved = []
    for op in trio:
        prod = op['base_prod']
        for need in op.get('coop_needs', []):
            if need not in trio_names: prod = 0; break
        resolved.append(prod)

    # 归零
    zero_idx = None
    for i, op in enumerate(trio):
        for ds in op.get('dynamic_slots', []):
            if ds.get('dynamic_type') == 'zero_out_per_op': zero_idx = i; break
    if zero_idx is not None:
        for i in range(3):
            if i != zero_idx:
                resolved[i] = trio[i].get('non_fac_prod', 0)

    # 统计
    a1_count = sum(1 for op in trio if op.get('is_a1'))
    class_counts = {}
    for op in trio:
        for sc in op.get('skill_classes', []):
            class_counts[sc] = class_counts.get(sc, 0) + 1

    # 动态技能
    final = list(resolved)
    for i, op in enumerate(trio):
        for ds in op.get('dynamic_slots', []):
            dtype = ds.get('dynamic_type', '')
            bonus = 0
            if dtype == 'a1_squad':
                bonus = a1_count * 10.0
            elif dtype == 'per_skill_class':
                desc = ds.get('description', '')
                tc = None
                if '金属工艺' in desc: tc = 'metal'
                elif '莱茵科技' in desc: tc = 'rhine'
                elif '标准化' in desc: tc = 'standard'
                if tc: bonus = class_counts.get(tc, 0) * 5.0
            elif dtype == 'synergy_multiply':
                if zero_idx is not None and zero_idx != i: bonus = 0
                else:
                    onf = 0
                    for j, other in enumerate(trio):
                        if j == i: continue
                        if zero_idx is not None and j != zero_idx: continue
                        onf += other.get('non_fac_prod', 0)
                    bonus = min(int(onf / 5) * 5, 40)
            elif dtype == 'zero_out_per_op':
                bonus = 3 * 10.0
            elif dtype == 'wh_to_prod_2pct':
                has_tiered = any(
                    ds2.get('dynamic_type') == 'wh_to_prod_tiered'
                    for other in trio for ds2 in other.get('dynamic_slots', []))
                if not has_tiered:
                    bonus = sum(o.get('total_wh', 0) for o in trio) * 2.0
            elif dtype == 'wh_to_prod_tiered':
                for other in trio:
                    wh = other.get('total_wh', 0)
                    bonus += wh * 1 if wh <= 16 else 16 * 1 + (wh - 16) * 3
            elif dtype == 'robot_to_prod':
                m = re.search(r'每.*?(\d+).*?个.*?机器人.*?([+-]\d+)%', ds.get('description', ''))
                if m: bonus = (ROBOTS // int(m.group(1))) * float(m.group(2))
            final[i] += bonus

    return sum(final), final

# ============================================================
# 主求解
# ============================================================
def solve(room='MANUFACTURE', recipe='gold', hours=12, categories=None):
    """求解指定设施的最优三人组"""
    if categories is None:
        categories = {'纯数值', '渐进加成', '设施数量', 'COOP同站', '小队加成',
                      '技能联动', '归零', '仓库→产能', '中间产物'}

    data = load_data()
    operators = build_candidates(data, room, recipe, hours, categories)
    results = []
    for trio in combinations(operators, 3):
        total, _ = resolve_trio(trio, data)
        if total > 0:
            results.append({'total': total, 'ops': trio})
    results.sort(key=lambda x: -x['total'])
    return results, operators, data

# ============================================================
# 内部辅助
# ============================================================
def _get_cn_name(info, data):
    for slot in info.get('slots', []):
        for sk in slot['skills']:
            buff = data['buffs'].get(sk['buffId'], {})
            # 无法直接从 buff 获取中文名, 用 charId 代替
            pass
    return info['charId']

def _slot_best(slot_skills, elite, room, recipe, hours, categories, data):
    """取某个槽位在指定条件下的最优技能"""
    buffs = data['buffs']
    best = None
    for sk in slot_skills:
        if sk['elite'] > elite: continue
        rt = sk['roomType']
        if rt not in (room, 'NONE', ''): continue

        bid = sk['buffId']
        buff = buffs.get(bid, {})
        name = buff.get('name', sk['buffName'])
        desc = buff.get('description', sk.get('description', ''))

        # 解析技能属性
        cat, rec, sc, is_dyn, dtype, coop, prod, wh = _classify_skill(
            name, desc, room, recipe, hours, categories)

        if cat not in categories: continue
        if recipe and rec not in (recipe, 'any'): continue
        if prod is None: continue
        if prod <= 0 and not is_dyn: continue

        if best is None or sk['elite'] >= best['elite']:
            best = {**sk, 'prod': prod, 'recipe': rec, 'category': cat,
                    'coop_requires': coop, 'skill_class': sc, 'warehouse': wh,
                    'is_dynamic': is_dyn, 'dynamic_type': dtype,
                    'buffName': name, 'description': desc}
    return best

def _classify_skill(name, desc, room, recipe, hours, categories):
    """分类技能并返回(类别, 配方, 技能类, 是否动态, 动态类型, COOP需求, 产能, 仓库)"""
    cat = '纯数值'
    rec = recipe if recipe else 'any'
    sc = 'other'
    is_dyn = False
    dtype = None
    coop = None
    wh = 0

    # 识别配方
    if '作战记录' in desc: rec = 'combat_record'
    elif '贵金属' in desc: rec = 'gold'
    elif '源石' in desc: rec = 'orundum'

    # 提取仓库
    whm = re.search(r'仓库容量上限([+-]\d+)', desc)
    if whm: wh = int(whm.group(1))

    # 识别技能类别
    if '标准化' in name: sc = 'standard'
    elif '莱茵科技' in name: sc = 'rhine'
    elif '红松骑士团' in name: sc = 'redpine'
    elif '金属工艺' in name: sc = 'metal'
    elif '自动化' in name or '仿生海龙' in name: sc = 'automation'
    elif '工匠精神' in name: sc = 'craftsman'

    prod = extract_pct(desc)

    # 识别类别和动态技能
    if '心情落差' in desc:
        cat = '心情落差'
        if '每有' in desc: is_dyn, dtype, prod = True, 'mood_gap', 0
    elif '消除' in desc and '心情' in desc:
        cat, prod = '心情消除', 0
    elif '全部归零' in desc:
        cat = '归零'
        if '每个' in desc and '干员' in desc and '生产力' in desc:
            is_dyn, dtype, prod = True, 'zero_out_per_op', 0
    elif '每格仓库' in desc and '生产力' in desc:
        cat = '仓库→产能'
        is_dyn, dtype, prod = True, 'wh_to_prod_2pct', 0
    elif '16格' in desc:
        cat = '仓库→产能'
        is_dyn, dtype, prod = True, 'wh_to_prod_tiered', 0
    elif '工程机器人' in desc and '生产力' in desc:
        cat = '中间产物'
        is_dyn, dtype, prod = True, 'robot_to_prod', 0
    elif '工程机器人' in desc:
        cat, prod = '中间产物', 0
    elif '配合意识' in name or '每5%生产力' in desc:
        cat = '技能联动'
        is_dyn, dtype, prod = True, 'synergy_multiply', 0
    elif '每个' in desc and '类技能' in desc:
        cat = '技能联动'
        if '仓库' in desc: prod = 0
        else: is_dyn, dtype, prod = True, 'per_skill_class', 0
    elif '当与' in desc and '在同一个' in desc:
        cat = 'COOP同站'
        cm = re.search(r'当与(.+?)在同一个', desc)
        if cm: coop = cm.group(1).strip()
    elif '每个A1' in desc:
        cat = '小队加成'
        is_dyn, dtype, prod = True, 'a1_squad', 0
    elif '贸易站' in desc and '生产力' in desc and '每' in desc:
        cat = '设施数量'
        prod = _calc_facility_prod(desc)
    elif '每间宿舍每级' in desc or '训练室每级' in desc:
        cat = '设施数量'
        prod = _calc_facility_prod(desc)
    elif '首小时' in desc and '最终达到' in desc:
        cat = '渐进加成'
        prod = calc_ramp_avg(desc, hours)
    elif '每小时' in desc and '最终达到' in desc and '首小时' not in desc:
        cat = '渐进加成'
        prod = calc_ramp_avg(desc, hours)

    return cat, rec, sc, is_dyn, dtype, coop, prod, wh

def _calc_facility_prod(desc):
    """计算设施数量类产能"""
    if '贸易站' in desc and '每' in desc:
        m = re.search(r'([+-]\d+)%', desc)
        if m: return float(m.group(1).replace('+', '')) * TRADING_POSTS
    if '宿舍每级' in desc:
        m = re.search(r'([+-]\d+)%', desc)
        if m: return float(m.group(1).replace('+', '')) * DORMS * DORM_LEVEL
    if '训练室每级' in desc:
        nums = re.findall(r'([+-]?\d+)%', desc)
        if len(nums) >= 1:
            raw = float(nums[0].replace('+', '')) * TRAINING_LEVEL
            cap = float(nums[1]) if len(nums) > 1 else raw
            return min(raw, cap)
    return None

# ============================================================
# CLI
# ============================================================
if __name__ == '__main__':
    room = sys.argv[1] if len(sys.argv) > 1 else 'MANUFACTURE'
    recipe = sys.argv[2] if len(sys.argv) > 2 else 'gold'
    hours = float(sys.argv[3]) if len(sys.argv) > 3 else 12
    results, ops, data = solve(room, recipe, hours)

    cn = lambda op: op.get('cn_name', op['charId'])
    print(f'{room} {recipe} ({hours}h): {len(ops)} candidates, Top1={results[0]["total"]:+.0f}%')
    for rank, r in enumerate(results[:5], 1):
        total, resolved = resolve_trio(r['ops'], data)
        names = ' + '.join(f'{cn(op)}(E{op["elite"]})' for op in r['ops'])
        print(f'  {rank}. {total:+.0f}%  {names}')

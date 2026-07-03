"""
贸易站专项求解器 — 评分模型: 效率 × 上限 (+ COOP条件)
"""
import json, re, os
from itertools import combinations

DIR = os.path.dirname(os.path.abspath(__file__))

with open(os.path.join(DIR, 'all_facility_skills.json'), 'r', encoding='utf-8') as f:
    data = json.load(f)
with open(os.path.join(DIR, 'manufacturing_skills.json'), 'r', encoding='utf-8') as f:
    mfg_skills = json.load(f)

ops_raw = data['operators']
buffs = data['buffs']

# === 干员 charId → 中文名 ===
char_cn = {}
for s in mfg_skills:
    for op in s['operators']:
        # 通过skill name反查charId... 需要从ops_raw中找
        pass

# 从 buff name → operator names 建立映射
buff_to_names = {}
for s in mfg_skills:
    buff_to_names[s['name']] = [op['name'] for op in s['operators']]

# charId → 中文名 (通过该干员的技能反查)
for char_id, info in ops_raw.items():
    for slot in info.get('slots', []):
        for sk in slot['skills']:
            buff = buffs.get(sk['buffId'], {})
            name = buff.get('name', sk['buffName'])
            if name in buff_to_names:
                char_cn[char_id] = buff_to_names[name][0]
                break
        if char_id in char_cn: break

# === 解析贸易技能 ===
def parse_trading_skill(sk, elite):
    """解析一个技能槽位, 返回 (eff, limit, coop_need, name, is_valid)"""
    if sk['elite'] > elite: return 0, 0, None, '', False
    rt = sk['roomType']
    if rt != 'TRADING': return 0, 0, None, '', False

    buff = buffs.get(sk['buffId'], {})
    desc = re.sub(r'<[^>]+>', '', buff.get('description', sk.get('description', '')))
    name = buff.get('name', sk['buffName'])

    # 中间产物/特殊订单: 暂跳过
    if any(kw in desc for kw in ['品质', '违约', '特别订单', '独家', '人间烟火', '感知信息', '木天蓼', '魔物料理', '思维链环', '工程机器人', '赤金生产线', '赤金订单']):
        return 0, 0, None, '', False

    # 效率
    eff = 0
    m = re.search(r'订单获取效率([+-]\d+)%', desc)
    if m: eff = int(m.group(1))

    # 上限
    limit = 0
    m = re.search(r'订单上限([+-]\d+)', desc)
    if m: limit = int(m.group(1))

    # COOP条件: "当与XXX在同一个贸易站时"
    coop_need = None
    cm = re.search(r'当与(.+?)在同一(?:个)?贸易站', desc)
    if cm: coop_need = cm.group(1).strip()

    return eff, limit, coop_need, name, True


# === 构建候选 ===
candidates = []
for char_id, info in ops_raw.items():
    cn_name = char_cn.get(char_id, char_id)
    for elite in [0, 1, 2]:
        total_eff = 0
        total_limit = 0
        total_eff_no_coop = 0  # 不含COOP的效率(COOP未触发时用)
        total_limit_no_coop = 0
        details = []
        coop_needs = []

        for slot in info.get('slots', []):
            best_eff = 0; best_lim = 0; best_coop = None; best_name = ''; best_eff_nc = 0; best_lim_nc = 0
            for sk in slot['skills']:
                eff, lim, coop, name, valid = parse_trading_skill(sk, elite)
                if not valid: continue
                # 槽内取最优: 按 eff+lim*3 排序
                score = eff + lim * 3
                best_score = best_eff + best_lim * 3
                if score > best_score:
                    best_eff, best_lim, best_coop, best_name = eff, lim, coop, name
                # 无COOP版本
                if not coop and eff + lim * 3 > best_eff_nc + best_lim_nc * 3:
                    best_eff_nc, best_lim_nc = eff, lim

            if best_name:
                total_eff += best_eff
                total_limit += best_lim
                total_eff_no_coop += best_eff_nc
                total_limit_no_coop += best_lim_nc
                tag = f'(需{best_coop})' if best_coop else ''
                details.append(f'S{slot["slotIndex"]}:{best_name}(eff{best_eff:+d} lim{best_lim:+d}){tag}')
                if best_coop:
                    coop_needs.append(best_coop)

        if details:
            candidates.append({
                'charId': char_id, 'cn_name': cn_name, 'elite': elite,
                'total_eff': total_eff, 'total_limit': total_limit,
                'total_eff_nc': total_eff_no_coop, 'total_limit_nc': total_limit_no_coop,
                'details': ' + '.join(details), 'coop_needs': coop_needs,
            })

# 去重
best_op = {}
for c in candidates:
    k = c['charId']
    # 用自身有效率排序(不含COOP)
    score = c['total_eff_nc'] + c['total_limit_nc'] * 3
    if k not in best_op: best_op[k] = (score, c)
    elif score > best_op[k][0]: best_op[k] = (score, c)
operators = [v[1] for v in best_op.values()]
operators.sort(key=lambda x: -(x['total_eff'] + x['total_limit'] * 3))


# === 评分 + COOP判定 ===
def score_trio(trio, verbose=False):
    """计算三人组贸易站产出, 考虑COOP条件"""
    trio_names = {op['cn_name'] for op in trio}
    base_eff = 100
    base_lim = 10
    total_eff = 0
    total_lim = 0

    for op in trio:
        eff = op['total_eff']
        lim = op['total_limit']
        # 检查COOP
        for need in op.get('coop_needs', []):
            if need not in trio_names:
                # COOP失败: 用无COOP版本
                eff = op['total_eff_nc']
                lim = op['total_limit_nc']
                break
        total_eff += eff
        total_lim += lim

    return (base_eff + total_eff) * (base_lim + total_lim), total_eff, total_lim


# === 枚举 ===
results = []
for trio in combinations(operators, 3):
    s, eff, lim = score_trio(trio)
    results.append({'score': s, 'eff': eff, 'lim': lim, 'ops': trio})
results.sort(key=lambda x: -x['score'])


# === 对外接口 (供 world_state.py 调用) ===
def solve_trading_standalone(data, exclude=None, gold_lines=2):
    """返回 (results, operators)。gold_lines: 赤金生产线数(默认2)"""
    excl = exclude or set()
    # 重新算一遍candidates, 因为赤金联动加成依赖gold_lines
    candidates_with_bonus = _rebuild_candidates_with_gold_lines(data, gold_lines, excl)
    filtered = [c for c in candidates_with_bonus if c['charId'] not in excl]
    res = []
    for trio in combinations(filtered, 3):
        s, eff, lim = score_trio(trio)
        res.append({'score': s, 'eff': eff, 'lim': lim, 'ops': trio})
    res.sort(key=lambda x: -x['score'])
    return res, filtered


def _rebuild_candidates_with_gold_lines(data, gold_lines, exclude):
    """重建候选, 计入赤金联动加成"""
    ops_raw = data['all_facility_skills']['operators']
    buffs = data['all_facility_skills']['buffs']
    # cn lookup
    ct = data.get('char_table', {})
    def _cn(cid):
        if cid in ct and isinstance(ct[cid], dict): return ct[cid].get('name', cid)
        return cid

    candidates = []
    for char_id, info in ops_raw.items():
        if char_id in (exclude or set()): continue
        cn = _cn(char_id)
        for elite in [0, 1, 2]:
            total_eff = 0; total_lim = 0
            total_eff_nc = 0; total_lim_nc = 0
            details = []; coop_needs = []
            for slot in info.get('slots', []):
                best_eff = 0; best_lim = 0; best_coop = None; best_name = ''
                best_eff_nc = 0; best_lim_nc = 0
                for sk in slot['skills']:
                    eff, lim, coop, name, valid = _parse_trading_skill(sk, elite, buffs)
                    if not valid: continue
                    # 赤金联动加成
                    gold_bonus = _calc_gold_line_bonus(sk, buffs, gold_lines)
                    eff += gold_bonus
                    if eff + lim * 3 > best_eff + best_lim * 3:
                        best_eff, best_lim, best_coop, best_name = eff, lim, coop, name
                    if not coop and eff + lim * 3 > best_eff_nc + best_lim_nc * 3:
                        best_eff_nc, best_lim_nc = eff, lim
                if best_name:
                    total_eff += best_eff; total_lim += best_lim
                    total_eff_nc += best_eff_nc; total_lim_nc += best_lim_nc
                    details.append('S{}:{} eff{} lim{}'.format(slot['slotIndex'], best_name, best_eff, best_lim))
                    if best_coop: coop_needs.append(best_coop)
            if details:
                candidates.append({
                    'charId': char_id, 'cn_name': cn, 'elite': elite,
                    'total_eff': total_eff, 'total_limit': total_lim,
                    'total_eff_nc': total_eff_nc, 'total_limit_nc': total_lim_nc,
                    'details': ' | '.join(details), 'coop_needs': coop_needs,
                })

    best_op = {}
    for c in candidates:
        k = c['charId']; s = c['total_eff_nc'] + c['total_limit_nc'] * 3
        if k not in best_op: best_op[k] = (s, c)
        elif s > best_op[k][0]: best_op[k] = (s, c)
    return [v[1] for v in best_op.values()]


def _parse_trading_skill(sk, elite, buffs):
    """解析单个技能, 返回 (eff, lim, coop, name, valid)"""
    if sk['elite'] > elite: return 0, 0, None, '', False
    if sk['roomType'] != 'TRADING': return 0, 0, None, '', False
    buff = buffs.get(sk['buffId'], {})
    desc = re.sub(r'<[^>]+>', '', buff.get('description', sk.get('description', '')))
    name = buff.get('name', sk['buffName'])
    skip_kw = ['品质', '违约', '独家', '人间烟火', '感知信息', '木天蓼', '魔物料理', '思维链环', '工程机器人']
    # 特殊处理: 特别订单(+10%效率) 和 天真的谈判者(+10%效率) 虽然有违约关键词但只取效率部分
    if any(kw in desc for kw in skip_kw):
        if name not in ['特别订单', '天真的谈判者']:
            return 0, 0, None, '', False
    eff = 0; lim = 0
    m = re.search(r'订单获取效率([+-]\d+)%', desc)
    if m: eff = int(m.group(1))
    m = re.search(r'订单上限([+-]\d+)', desc)
    if m: lim = int(m.group(1))
    coop = None
    cm = re.search(r'当与(.+?)在同一(?:个)?贸易站', desc)
    if cm: coop = cm.group(1).strip()
    return eff, lim, coop, name, True


def _calc_gold_line_bonus(sk, buffs, gold_lines):
    """计算赤金联动加成"""
    buff = buffs.get(sk['buffId'], {})
    desc = re.sub(r'<[^>]+>', '', buff.get('description', sk.get('description', '')))
    bonus = 0
    if '赤金生产线' in desc:
        if '每有4条' in desc:
            bonus = (gold_lines // 4) * 15
        elif '每有2条' in desc:
            bonus = (gold_lines // 2) * 15
        elif '每有1条' in desc:
            bonus = gold_lines * 5
    return bonus


# === 输出 ===
cn = lambda op: op.get('cn_name', op['charId'])
coop_count = sum(1 for op in operators if op['coop_needs'])
print(f'贸易站候选: {len(operators)} 人')
print(f'其中含COOP条件: {coop_count} 人')
print()
print(f'{"排名":<5} {"评分":<8} {"效率":<8} {"上限":<8} {"组合"}')
print('-' * 80)
for rank, r in enumerate(results[:10], 1):
    names = ' + '.join(f'{cn(op)}(E{op["elite"]})' for op in r['ops'])
    s, _, _ = score_trio(r['ops'], verbose=True)
    print(f'{rank:<5} {s:<8} {100+r["eff"]}%      {10+r["lim"]:<8} {names}')

print()
print('Top 3 详情:')
for rank, r in enumerate(results[:3], 1):
    s, eff, lim = score_trio(r['ops'])
    print(f'  {rank}. 评分={s} (效率={100+eff}% × 上限={10+lim})')
    for op in r['ops']:
        coop_ok = all(need in {o['cn_name'] for o in r['ops']} for need in op.get('coop_needs', []))
        tag = '[OK]' if coop_ok or not op['coop_needs'] else '[COOP FAIL]'
        e = op['elite']
    print(f'    {cn(op)}(E{e}): [{op["details"]}] {tag}')

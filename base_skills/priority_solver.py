"""
优先级排班求解器 v2

目标 (字典序):
  1. 贸易站龙门币最大化 (效率×上限模型)
  2. 赤金最大化
  3. 经验最大化
"""
import json, re, os, sys
from itertools import combinations

DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, DIR)

from solver_core import solve, resolve_trio, load_data

# ============================================================
# 贸易站求解 (复用 trading_solver 逻辑)
# ============================================================
def solve_trading(exclude=None):
    """求解贸易站最优三人组, 排除指定干员"""
    with open(os.path.join(DIR, 'all_facility_skills.json'), 'r', encoding='utf-8') as f:
        data = json.load(f)
    with open(os.path.join(DIR, 'manufacturing_skills.json'), 'r', encoding='utf-8') as f:
        mfg_skills = json.load(f)

    ops_raw = data['operators']
    buffs = data['buffs']
    exclude = exclude or set()

    # charId → 中文名 (优先用 char_table.json)
    char_cn = {}
    with open(os.path.join(DIR, '..', 'char_table.json'), 'r', encoding='utf-8') as f:
        ct = json.load(f)
    for cid in ct:
        if isinstance(ct[cid], dict):
            char_cn[cid] = ct[cid].get('name', cid)
    # 补漏: manufacturing_skills.json
    buff_to_names = {}
    for s in mfg_skills:
        buff_to_names[s['name']] = [op['name'] for op in s['operators']]
    for char_id, info in ops_raw.items():
        if char_id in char_cn: continue
        for slot in info.get('slots', []):
            for sk in slot['skills']:
                buff = buffs.get(sk['buffId'], {})
                name = buff.get('name', sk['buffName'])
                if name in buff_to_names:
                    char_cn[char_id] = buff_to_names[name][0]
                    break
            if char_id in char_cn: break

    def parse_skill(sk, elite):
        if sk['elite'] > elite: return 0, 0, None, '', False
        rt = sk['roomType']
        if rt != 'TRADING': return 0, 0, None, '', False
        buff = buffs.get(sk['buffId'], {})
        desc = re.sub(r'<[^>]+>', '', buff.get('description', sk.get('description', '')))
        name = buff.get('name', sk['buffName'])
        # 跳过特殊/中间产物
        skip_kw = ['品质', '违约', '特别订单', '独家', '人间烟火', '感知信息', '木天蓼', '魔物料理', '思维链环', '工程机器人', '赤金生产线', '赤金订单']
        if any(kw in desc for kw in skip_kw): return 0, 0, None, '', False
        eff = 0; lim = 0
        m = re.search(r'订单获取效率([+-]\d+)%', desc)
        if m: eff = int(m.group(1))
        m = re.search(r'订单上限([+-]\d+)', desc)
        if m: lim = int(m.group(1))
        coop = None
        cm = re.search(r'当与(.+?)在同一(?:个)?贸易站', desc)
        if cm: coop = cm.group(1).strip()
        return eff, lim, coop, name, True

    # 构建候选
    candidates = []
    for char_id, info in ops_raw.items():
        if char_id in exclude: continue
        cn_name = char_cn.get(char_id, char_id)
        for elite in [0, 1, 2]:
            total_eff = 0; total_lim = 0
            total_eff_nc = 0; total_lim_nc = 0
            details = []; coop_needs = []
            for slot in info.get('slots', []):
                best_eff = 0; best_lim = 0; best_coop = None; best_name = ''
                best_eff_nc = 0; best_lim_nc = 0
                for sk in slot['skills']:
                    eff, lim, coop, name, valid = parse_skill(sk, elite)
                    if not valid: continue
                    if eff + lim * 3 > best_eff + best_lim * 3:
                        best_eff, best_lim, best_coop, best_name = eff, lim, coop, name
                    if not coop and eff + lim * 3 > best_eff_nc + best_lim_nc * 3:
                        best_eff_nc, best_lim_nc = eff, lim
                if best_name:
                    total_eff += best_eff; total_lim += best_lim
                    total_eff_nc += best_eff_nc; total_lim_nc += best_lim_nc
                    tag = f'(需{best_coop})' if best_coop else ''
                    details.append(f'S{slot["slotIndex"]}:{best_name}(eff{best_eff:+d} lim{best_lim:+d}){tag}')
                    if best_coop: coop_needs.append(best_coop)
            if details:
                candidates.append({
                    'charId': char_id, 'cn_name': cn_name, 'elite': elite,
                    'total_eff': total_eff, 'total_lim': total_lim,
                    'total_eff_nc': total_eff_nc, 'total_lim_nc': total_lim_nc,
                    'details': ' + '.join(details), 'coop_needs': coop_needs,
                })

    # 去重
    best_op = {}
    for c in candidates:
        k = c['charId']
        score = c['total_eff_nc'] + c['total_lim_nc'] * 3
        if k not in best_op: best_op[k] = (score, c)
        elif score > best_op[k][0]: best_op[k] = (score, c)
    operators = [v[1] for v in best_op.values()]

    def score_trio(trio):
        trio_names = {op['cn_name'] for op in trio}
        total_eff = 0; total_lim = 0
        for op in trio:
            eff = op['total_eff']; lim = op['total_lim']
            for need in op.get('coop_needs', []):
                if need not in trio_names:
                    eff = op['total_eff_nc']; lim = op['total_lim_nc']; break
            total_eff += eff; total_lim += lim
        return (100 + total_eff) * (10 + total_lim), total_eff, total_lim

    results = []
    for trio in combinations(operators, 3):
        s, eff, lim = score_trio(trio)
        results.append({'score': s, 'eff': eff, 'lim': lim, 'ops': trio})
    results.sort(key=lambda x: -x['score'])

    return results, operators, data


# ============================================================
# 主流程
# ============================================================
def solve_all():
    used_ops = set()
    data = load_data()

    # === 1. 贸易站 ===
    print('=== 优先级1: 贸易站龙门币 ===')
    tr, to, _ = solve_trading()
    t_a = tr[0]
    used_ops.update(op['charId'] for op in t_a['ops'])
    tr, to, _ = solve_trading(exclude=used_ops)
    t_b = tr[0]
    used_ops.update(op['charId'] for op in t_b['ops'])

    cn = lambda op: op.get('cn_name', op['charId'])
    def fmt_t(op): return f'{cn(op)}(E{op["elite"]})'
    print(f'  贸易A: 评分={t_a["score"]} 效率={100+t_a["eff"]}% 上限={10+t_a["lim"]}')
    print(f'    {", ".join(fmt_t(op) for op in t_a["ops"])}')
    print(f'  贸易B: 评分={t_b["score"]} 效率={100+t_b["eff"]}% 上限={10+t_b["lim"]}')
    print(f'    {", ".join(fmt_t(op) for op in t_b["ops"])}')

    # === 2. 赤金 ===
    print('\n=== 优先级2: 赤金 ===')
    def best_mfg(recipe, exclude_set):
        results, ops, _ = solve('MANUFACTURE', recipe, 12)
        remaining = [op for op in ops if op['charId'] not in exclude_set]
        best = None
        for trio in combinations(remaining, 3):
            t, _ = resolve_trio(trio, data)
            if best is None or t > best['total']: best = {'total': t, 'ops': trio}
        return best

    g_a = best_mfg('gold', used_ops)
    used_ops.update(op['charId'] for op in g_a['ops'])
    g_b = best_mfg('gold', used_ops)
    used_ops.update(op['charId'] for op in g_b['ops'])

    print(f'  赤金A: {g_a["total"]:+.0f}%  ({", ".join(fmt_t(op) for op in g_a["ops"])})')
    print(f'  赤金B: {g_b["total"]:+.0f}%  ({", ".join(fmt_t(op) for op in g_b["ops"])})')

    # === 3. 经验 ===
    print('\n=== 优先级3: 经验 ===')
    e_a = best_mfg('combat_record', used_ops)
    used_ops.update(op['charId'] for op in e_a['ops'])
    e_b = best_mfg('combat_record', used_ops)
    used_ops.update(op['charId'] for op in e_b['ops'])

    print(f'  经验A: {e_a["total"]:+.0f}%  ({", ".join(fmt_t(op) for op in e_a["ops"])})')
    print(f'  经验B: {e_b["total"]:+.0f}%  ({", ".join(fmt_t(op) for op in e_b["ops"])})')

    print(f'\n总用干员: {len(used_ops)}')
    return {'trading': [t_a, t_b], 'gold': [g_a, g_b], 'exp': [e_a, e_b]}


if __name__ == '__main__':
    solve_all()

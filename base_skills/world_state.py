"""
WorldState — 全局基建状态

各层之间通过 WorldState 单向传递数据。
每一层只读取上一层的快照, 写入自己的结果。
"""
import json, os, re
from itertools import combinations

DIR = os.path.dirname(os.path.abspath(__file__))

# 基建常量
TRADING_POSTS = 2
POWER_PLANTS = 3
DORMS = 4
DORM_LEVEL = 5
TRAINING_LEVEL = 3
ROBOTS = 64
HOURS = 12

# 设施需求
FACILITY_SLOTS = {
    'TRADING': 3,        # 每贸易站3人
    'MANUFACTURE': 3,    # 每制造站3人
    'CONTROL': 5,        # 控制中枢5人
}

class WorldState:
    def __init__(self):
        self.baseline = {}     # {facility_key: [top_results]}
        self.snapshot = {}     # 自动提取的条件快照
        self.control_buffs = {}  # {buff_type: value}
        self.adjusted = {}     # buff后的重算结果
        self.final = {}        # 最终排班

    def to_dict(self):
        return {
            'baseline': self.baseline,
            'snapshot': self.snapshot,
            'control_buffs': self.control_buffs,
            'adjusted': self.adjusted,
            'final': self.final,
        }


# ============================================================
# 层0: 基线排班 — 无中枢, 无联动
# ============================================================

def load_all_data():
    """加载所有数据"""
    data = {}
    for fname in ['all_facility_skills.json', 'manufacturing_skills.json']:
        with open(os.path.join(DIR, fname), 'r', encoding='utf-8') as f:
            data[fname.replace('.json', '')] = json.load(f)
    ct_path = os.path.join(DIR, '..', 'char_table.json')
    if os.path.exists(ct_path):
        with open(ct_path, 'r', encoding='utf-8') as f:
            data['char_table'] = json.load(f)
    return data

def cn_name(char_id, data):
    ct = data.get('char_table', {})
    if char_id in ct and isinstance(ct[char_id], dict):
        return ct[char_id].get('name', char_id)
    return char_id

def layer0_baseline(data):
    """
    层0: 独立求解所有设施 (无中枢buff, 无联动)
    返回 baseline dict
    """
    from solver_core import solve, resolve_trio

    world = WorldState()
    baseline = {}

    # --- 制造站 gold ×2 ---
    results, ops, _ = solve('MANUFACTURE', 'gold', HOURS)
    used = set()
    stations = []
    for _ in range(2):
        remaining = [op for op in ops if op['charId'] not in used]
        best = None
        for trio in combinations(remaining, 3):
            t, _ = resolve_trio(trio, data['all_facility_skills'])
            if best is None or t > best['total']:
                best = {'total': t, 'ops': trio}
        if best:
            stations.append(best)
            used.update(op['charId'] for op in best['ops'])
    baseline['gold'] = stations

    # --- 制造站 combat_record ×2 ---
    results, ops, _ = solve('MANUFACTURE', 'combat_record', HOURS)
    stations = []
    for _ in range(2):
        remaining = [op for op in ops if op['charId'] not in used]
        best = None
        for trio in combinations(remaining, 3):
            t, _ = resolve_trio(trio, data['all_facility_skills'])
            if best is None or t > best['total']:
                best = {'total': t, 'ops': trio}
        if best:
            stations.append(best)
            used.update(op['charId'] for op in best['ops'])
    baseline['exp'] = stations

    # --- 贸易站 ×2 ---
    from trading_solver import solve_trading_standalone
    gold_lines = 2  # 两个赤金站
    tr_results, tr_ops = solve_trading_standalone(data, exclude=used, gold_lines=gold_lines)
    stations = []
    for r in tr_results:
        trio_used = any(op['charId'] in used for op in r['ops'])
        if trio_used: continue
        stations.append(r)
        used.update(op['charId'] for op in r['ops'])
        if len(stations) >= 2: break
    baseline['trading'] = stations

    world.baseline = baseline
    return world


def _score_trading_trio(trio):
    """贸易站三人组评分"""
    base_eff = 100; base_lim = 10
    total_eff = 0; total_lim = 0
    trio_names = {op.get('cn_name', op['charId']) for op in trio}
    for op in trio:
        eff = op.get('total_eff', 0); lim = op.get('total_limit', 0)
        for need in op.get('coop_needs', []):
            if need not in trio_names:
                eff = op.get('total_eff_nc', eff)
                lim = op.get('total_limit_nc', lim)
                break
        total_eff += eff; total_lim += lim
    return (base_eff + total_eff) * (base_lim + total_lim)


# ============================================================
# 层1: 快照提取
# ============================================================

def layer1_snapshot(world, data):
    """
    从基线排班提取条件快照:
    - 赤金生产线数
    - 各站派系分布
    - 谢拉格/叙拉古/龙门近卫局 等关键派系在哪些站
    """
    snap = {
        'gold_lines': len(world.baseline.get('gold', [])),
        'factions_in_mfg': {},
        'factions_in_trade': {},
        'operators_in_mfg': set(),
        'operators_in_trade': set(),
    }
    for station in world.baseline.get('gold', []) + world.baseline.get('exp', []):
        for op in station['ops']:
            snap['operators_in_mfg'].add(op['charId'])
    for station in world.baseline.get('trading', []):
        for op in station['ops']:
            snap['operators_in_trade'].add(op['charId'])

    world.snapshot = snap
    return world


# ============================================================
# 层2: 中枢求解 (后续实现)
# ============================================================

def layer2_control(world, data):
    """根据下游排班快照, 计算每个中枢干员的实际buff值, 选最优5人"""
    buffs = data['all_facility_skills']['buffs']
    ops_raw = data['all_facility_skills']['operators']
    snap = world.snapshot

    mfg_ops = snap['operators_in_mfg']  # 制造站干员 charId 集合
    trade_ops = snap['operators_in_trade']  # 贸易站干员集合

    # 评估每个中枢干员
    candidates = []
    for cid, info in ops_raw.items():
        for elite in [0, 1, 2]:
            trade_bonus = 0.0   # 贸易全局效率 (同种取最高)
            mfg_bonus = 0.0     # 制造全局生产力 (同种取最高)
            gold_bonus = 0.0    # 贵金属制造站生产力
            cond_bonuses = []   # 条件性加成 (每个单独生效)
            details = []

            for slot in info.get('slots', []):
                best_t = 0; best_m = 0; best_g = 0; best_name = ''
                best_conds = []
                for sk in slot['skills']:
                    if sk['elite'] > elite: continue
                    b = buffs.get(sk['buffId'], {})
                    if b.get('roomType', '') != 'CONTROL': continue
                    desc = re.sub(r'<[^>]+>', '', b.get('description', ''))
                    name = b.get('name', '')

                    t = 0; m = 0; g = 0; conds = []

                    # 贸易全局效率
                    if '所有贸易站' in desc and '订单效率' in desc:
                        tm = re.search(r'\+(\d+)%', desc)
                        if tm: t = float(tm.group(1))

                    # 制造全局生产力
                    if '制造站' in desc and '生产力' in desc and '红松' not in name:
                        if '贵金属' in desc:
                            pm = re.search(r'制造站生产力\+(\d+\.?\d*)%', desc)
                            if pm: g = float(pm.group(1))
                            else:
                                pm2 = re.search(r'生产力\+(\d+\.?\d*)%', desc)
                                if pm2 and '贵金属' in desc: g = float(pm2.group(1))
                        elif '龙门近卫局' in desc:
                            if _has_faction_in_set('龙门近卫局', mfg_ops, data):
                                pm = re.search(r'生产力\+(\d+)%', desc)
                                if pm: m = float(pm.group(1))
                        else:
                            # 制造站全局: 只匹配 "制造站生产力+N%" 避免误匹配贸易
                            pm = re.search(r'制造站生产力\+(\d+)%', desc)
                            if pm:
                                m = float(pm.group(1))
                            else:
                                # 权变: "所有制造站生产力+2%"
                                pm2 = re.search(r'制造站.*?\+(\d+)%', desc)
                                if pm2: m = float(pm2.group(1))

                    # 条件性: 家族认可 (叙拉古在贸易站)
                    if '叙拉古' in desc and '贸易站' in desc:
                        count = _count_faction_in_set('叙拉古', trade_ops, data)
                        if count > 0:
                            em = re.search(r'\+(\d+)%', desc)
                            if em: conds.append('叙拉古{}人→+{}%'.format(count, int(em.group(1))*count))

                    # 条件性: 老友相聚 (黑钢在制造站)
                    if '黑钢' in desc and '制造站' in desc:
                        count = _count_faction_in_set('黑钢国际', mfg_ops, data)
                        if count > 0:
                            em = re.search(r'\+(\d+)%', desc)
                            if em: conds.append('黑钢{}人→+{}%'.format(count, int(em.group(1))*count))

                    # 条件性: 烛骑士微光 (骑士在制造站)
                    if '骑士' in desc and '制造站' in desc and '生产力' in desc:
                        count = _count_faction_in_set('骑士', mfg_ops, data)
                        if count > 0:
                            em = re.search(r'\+(\d+)%', desc)
                            if em: conds.append('骑士{}人→+{}%'.format(count, int(em.group(1))*count))

                    # 商业版图: 谢拉格≥3在贸易站
                    if '谢拉格' in desc and '贸易站' in desc and '3' in desc:
                        count = _count_faction_in_set('谢拉格', trade_ops, data)
                        if count >= 3:
                            em = re.search(r'\+(\d+)%', desc)
                            if em: conds.append('谢拉格≥3→+{}%'.format(int(em.group(1))))

                    score = t + m + g + sum(_extract_pct(str(c)) for c in conds)
                    best_score = best_t + best_m + best_g
                    if score > best_score:
                        best_t, best_m, best_g, best_name, best_conds = t, m, g, name, conds

                if best_name:
                    trade_bonus = max(trade_bonus, best_t)
                    mfg_bonus = max(mfg_bonus, best_m)
                    gold_bonus = max(gold_bonus, best_g)
                    cond_bonuses.extend(best_conds)
                    tags = []
                    if best_t > 0: tags.append('贸+{}%'.format(int(best_t)))
                    if best_m > 0: tags.append('制+{}%'.format(int(best_m)))
                    if best_g > 0: tags.append('金+{}%'.format(best_g))
                    if best_conds: tags.extend(best_conds)
                    details.append('S{}:{} ({})'.format(slot['slotIndex'], best_name, ', '.join(tags)))

            if details:
                candidates.append({
                    'charId': cid, 'elite': elite,
                    'trade_bonus': trade_bonus, 'mfg_bonus': mfg_bonus,
                    'gold_bonus': gold_bonus, 'cond_bonuses': cond_bonuses,
                    'details': ' | '.join(details),
                })

    # 去重: 每干员最优精英
    best_op = {}
    for c in candidates:
        k = c['charId']
        s = c['trade_bonus'] * 100 + c['mfg_bonus'] * 10 + c['gold_bonus'] * 5
        if k not in best_op or s > best_op[k][0]:
            best_op[k] = (s, c)
    operators = sorted(best_op.values(), key=lambda x: -x[0])

    # 选5人 (同种取最高, 覆盖贸易+制造+贵金属)
    from itertools import combinations
    best_set = None
    best_val = 0
    for quint in combinations(operators[:min(12, len(operators))], 5):
        ops_list = [o[1] for o in quint]
        t = max(op['trade_bonus'] for op in ops_list)
        m = max(op['mfg_bonus'] for op in ops_list)
        g = max(op['gold_bonus'] for op in ops_list)
        val = t * 100 + m * 10 + g * 5
        if val > best_val:
            best_val = val
            best_set = ops_list

    if best_set:
        world.control_buffs = {
            'trade_efficiency': max(op['trade_bonus'] for op in best_set),
            'mfg_productivity': max(op['mfg_bonus'] for op in best_set),
            'gold_productivity': max(op['gold_bonus'] for op in best_set),
            'cond_bonuses': [c for op in best_set for c in op.get('cond_bonuses', [])],
            'best_5': [{'name': cn_name(op['charId'], data), 'elite': op['elite'], 'details': op['details']} for op in best_set],
        }

    return world


def _has_faction_in_set(faction, char_ids, data):
    """检查集合中是否有指定派系干员 (简化: 用名字关键词)"""
    return _count_faction_in_set(faction, char_ids, data) > 0

def _count_faction_in_set(faction, char_ids, data):
    """统计集合中指定派系干员数 (简化: 查表)"""
    # 硬编码已知派系成员 (后续可改为查 building_data.json)
    FACTION_MAP = {
        '龙门近卫局': ['陈', '星熊', '诗怀雅'],
        '叙拉古': ['拉普兰德', '德克萨斯', '德克萨斯(?)'],
        '黑钢国际': ['雷蛇', '芙兰卡', '杰西卡', '香草'],
        '骑士': ['耀骑士临光', '临光', '瑕光', '鞭刃', '焰尾', '远牙', '灰毫', '野鬃', '薇薇安娜'],
        '谢拉格': ['银灰', '灵知', '初雪', '崖心', '角峰', '讯使', '耶拉', '极光', '锏'],
    }
    faction_names = FACTION_MAP.get(faction, [])
    count = 0
    for cid in char_ids:
        name = cn_name(cid, data)
        if any(fn in name for fn in faction_names):
            count += 1
    return count

def _extract_pct(s):
    m = re.search(r'(\d+)%', s)
    return float(m.group(1)) if m else 0


# ============================================================
# 管线入口
# ============================================================

def layer3_inject(world, data):
    """将中枢buff注入下游设施, 重算排名。全局buff不改变排名。"""
    cb = world.control_buffs
    trade_buff = cb.get('trade_efficiency', 0)
    mfg_buff = cb.get('mfg_productivity', 0)
    gold_buff = cb.get('gold_productivity', 0)

    adjusted = {}

    # 贸易站: buff直接加到效率上
    for i, st in enumerate(world.baseline.get('trading', [])):
        orig_score = st['score']
        # 重算: (100+eff+trade_buff) × (10+lim)
        total_eff = st.get('eff', 0) + trade_buff
        total_lim = st.get('lim', 0)
        new_score = (100 + total_eff) * (10 + total_lim)
        adjusted['trading_{}'.format(chr(65+i))] = {
            'score_before': orig_score,
            'score_after': new_score,
            'delta': new_score - orig_score,
        }

    # 制造站gold: buff加到产能上
    for i, st in enumerate(world.baseline.get('gold', [])):
        orig = st['total']
        new = orig + mfg_buff + gold_buff
        adjusted['gold_{}'.format(chr(65+i))] = {
            'prod_before': orig, 'prod_after': new, 'delta': new - orig,
        }

    # 经验站: 制造buff也适用
    for i, st in enumerate(world.baseline.get('exp', [])):
        orig = st['total']
        new = orig + mfg_buff
        adjusted['exp_{}'.format(chr(65+i))] = {
            'prod_before': orig, 'prod_after': new, 'delta': new - orig,
        }

    world.adjusted = adjusted
    # 检测排名变化
    changed = any(a.get('delta', 0) != trade_buff * 0 for a in adjusted.values())
    return world, changed


def run_pipeline(max_iter=3):
    data = load_all_data()
    world = layer0_baseline(data)
    world = layer1_snapshot(world, data)

    for iteration in range(max_iter):
        world = layer2_control(world, data)
        world, changed = layer3_inject(world, data)
        if not changed:
            print('  迭代{}: 收敛 (排名未变)'.format(iteration + 1))
            break
        print('  迭代{}: 排名变化, 重新提取快照...'.format(iteration + 1))
        world = layer1_snapshot(world, data)

    world.final = _build_final(world)
    return world


def _build_final(world):
    """汇总最终排班"""
    final = {'trading': [], 'gold': [], 'exp': [], 'control': []}
    for st in world.baseline.get('trading', []):
        final['trading'].append({'ops': [cn_name(op['charId'], load_all_data()) for op in st['ops']], 'score': st['score']})
    for st in world.baseline.get('gold', []):
        final['gold'].append({'ops': [cn_name(op['charId'], load_all_data()) for op in st['ops']], 'prod': st['total']})
    for st in world.baseline.get('exp', []):
        final['exp'].append({'ops': [cn_name(op['charId'], load_all_data()) for op in st['ops']], 'prod': st['total']})
    final['control'] = world.control_buffs.get('best_5', [])
    return final


if __name__ == '__main__':
    world = run_pipeline()
    print('=== 层0: 基线排班 ===')
    for key, stations in world.baseline.items():
        for i, st in enumerate(stations):
            names = ' + '.join(cn_name(op['charId'], load_all_data()) for op in st['ops'])
            metric = st.get('total', st.get('score', '?'))
            print('  {}_{}: {} = {}'.format(key, chr(65+i), metric, names))

    print()
    print('=== 层1: 快照 ===')
    for k, v in world.snapshot.items():
        if isinstance(v, set):
            print('  {}: {} operators'.format(k, len(v)))
        else:
            print('  {}: {}'.format(k, v))

    print()
    print('=== 层2: 中枢最优5人 ===')
    cb = world.control_buffs
    print('  贸易全局: +{}%'.format(cb.get('trade_efficiency', 0)))
    print('  制造全局: +{}%'.format(cb.get('mfg_productivity', 0)))
    print('  贵金属制造: +{}%'.format(cb.get('gold_productivity', 0)))
    print('  条件加成: {}'.format(cb.get('cond_bonuses', [])))
    print('  最优5人:')
    for op in cb.get('best_5', []):
        print('    {}(E{}) [{}]'.format(op['name'], op['elite'], op['details']))

    print()
    print('=== 层3: buff注入 ===')
    for key, val in world.adjusted.items():
        print('  {}: {} → {} ({:+.1f})'.format(key, val.get('score_before', val.get('prod_before', 0)),
                                               val.get('score_after', val.get('prod_after', 0)),
                                               val.get('delta', 0)))

    print()
    print('=== 最终排班 ===')
    for key, stations in world.final.items():
        if key == 'control':
            print('  中枢:')
            for op in stations:
                print('    {}(E{})'.format(op['name'], op['elite']))
        else:
            for i, st in enumerate(stations):
                print('  {}_{}: {}'.format(key, chr(65+i), ' + '.join(st['ops'])))

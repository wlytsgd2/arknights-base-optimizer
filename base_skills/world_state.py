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

    # --- 先跑 exp + 贸易, 收集used集用于派系统计 ---
    # 制造站 combat_record ×2
    results_e, ops_e, _ = solve('MANUFACTURE', 'combat_record', HOURS)
    used = set()
    exp_stations = []
    for _ in range(2):
        remaining = [op for op in ops_e if op['charId'] not in used]
        best = None
        for trio in combinations(remaining, 3):
            t, _ = resolve_trio(trio, data['all_facility_skills'])
            if best is None or t > best['total']:
                best = {'total': t, 'ops': trio}
        if best:
            exp_stations.append(best)
            used.update(op['charId'] for op in best['ops'])

    # 贸易站 ×2
    from trading_solver import solve_trading_standalone
    gold_lines = 2
    tr_results, tr_ops = solve_trading_standalone(data, exclude=used, gold_lines=gold_lines)
    trade_stations = []
    for r in tr_results:
        trio_used = any(op['charId'] in used for op in r['ops'])
        if trio_used: continue
        trade_stations.append(r)
        used.update(op['charId'] for op in r['ops'])
        if len(trade_stations) >= 2: break

    # 派系统计 (从 exp + 贸易的已用干员中)
    all_assigned = used.copy()
    faction_counts = {
        '莱茵生命': _count_faction('莱茵生命', all_assigned, data),
        '黑钢国际': _count_faction('黑钢国际', all_assigned, data),
    }

    # --- 制造站 gold ×2 (带派系加成) ---
    results, ops, _ = solve('MANUFACTURE', 'gold', HOURS)
    ops = _apply_faction_bonus(ops, faction_counts)
    gold_used = set()
    gold_stations = []
    for _ in range(2):
        remaining = [op for op in ops if op['charId'] not in gold_used]
        best = None
        for trio in combinations(remaining, 3):
            t, _ = resolve_trio(trio, data['all_facility_skills'])
            t += sum(op.get('_faction_bonus', 0) for op in trio)
            if best is None or t > best['total']:
                best = {'total': t, 'ops': trio}
        if best:
            gold_stations.append(best)
            gold_used.update(op['charId'] for op in best['ops'])

    baseline['gold'] = gold_stations
    baseline['exp'] = exp_stations
    baseline['trading'] = trade_stations
    used = all_assigned | gold_used
    world.snapshot['faction_counts'] = faction_counts

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

# 硬编码派系成员 (可从 building_data.json 扩展)
FACTIONS = {
    '莱茵生命': ['多萝西', '娜斯提', '星源', '溯光星源', '白面鸮', '赫默', '淬羽赫默', '缪尔赛思', '伊芙利特', '梅尔', '麦哲伦', '塞雷娅', '小火龙'],
    '黑钢国际': ['雷蛇', '芙兰卡', '杰西卡', '香草', '杏仁', '寻澜', '涤火杰西卡'],
}
def _count_faction(faction, all_ops_set, data):
    """统计所有已分配干员中某派系的人数"""
    names = FACTIONS.get(faction, [])
    count = 0
    for cid in all_ops_set:
        n = cn_name(cid, data)
        if any(fn in n for fn in names):
            count += 1
    return count


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

    candidates = []
    for cid, info in ops_raw.items():
        for elite in [0, 1, 2]:
            trade_bonus = 0.0; mfg_bonus = 0.0; gold_bonus = 0.0
            intermediates = []; details = []
            for slot in info.get('slots', []):
                best_score = 0; best_t = 0; best_m = 0; best_g = 0
                best_name = ''; best_inter = []
                for sk in slot['skills']:
                    if sk['elite'] > elite: continue
                    b = buffs.get(sk['buffId'], {})
                    if b.get('roomType', '') != 'CONTROL': continue
                    desc = b.get('description', ''); name = b.get('name', '')
                    t = 0; m = 0; g = 0; inter = []
                    if '所有贸易站' in desc and '订单效率' in desc:
                        tm = re.search(r'\+(\d+)%', desc)
                        if tm: t = float(tm.group(1))
                    if '制造站' in desc and '生产力' in desc:
                        if '红松' not in name:
                            if '贵金属' in desc:
                                pm = re.search(r'\+(\d+\.?\d*)%', desc)
                                if pm: g = float(pm.group(1))
                            else:
                                pm = re.search(r'\+(\d+)%', desc)
                                if pm: m = float(pm.group(1))
                    for ip in ['人间烟火','热情值','感知信息','木天蓼','乌萨斯特饮','情报储备']:
                        if ip in desc: inter.append(ip)
                    if t + m + g + len(inter) * 50 > best_score:
                        best_score = t + m + g + len(inter) * 50
                        best_t, best_m, best_g, best_name, best_inter = t, m, g, name, inter
                if best_name:
                    trade_bonus = max(trade_bonus, best_t)
                    mfg_bonus = max(mfg_bonus, best_m)
                    gold_bonus = max(gold_bonus, best_g)
                    intermediates.extend(best_inter)
                    ts = []
                    if best_t > 0: ts.append('贸+{}%'.format(int(best_t)))
                    if best_m > 0: ts.append('制+{}%'.format(int(best_m)))
                    if best_g > 0: ts.append('金+{}%'.format(best_g))
                    if best_inter: ts.append('产:' + ','.join(best_inter))
                    details.append('S{}:{} ({})'.format(slot['slotIndex'], best_name, ', '.join(ts)))
            if trade_bonus > 0 or mfg_bonus > 0 or gold_bonus > 0 or intermediates:
                candidates.append({
                    'charId': cid, 'elite': elite,
                    'trade_bonus': trade_bonus, 'mfg_bonus': mfg_bonus,
                    'gold_bonus': gold_bonus,
                    'intermediates': list(set(intermediates)),
                    'details': ' | '.join(details),
                })

    import re as _re
    best_op = {}
    for c in candidates:
        k = c['charId']
        s = c['trade_bonus'] * 100 + c['mfg_bonus'] * 10 + c['gold_bonus'] * 5 + len(c.get('intermediates', [])) * 150
        if k not in best_op or s > best_op[k][0]:
            best_op[k] = (s, c)
    operators = sorted(best_op.values(), key=lambda x: -x[0])

    from itertools import combinations
    best_set = None; best_val = 0
    for quint in combinations([o[1] for o in operators], 5):
        ol = list(quint)
        t = max(o['trade_bonus'] for o in ol)
        m = max(o['mfg_bonus'] for o in ol)
        g = max(o['gold_bonus'] for o in ol)
        ai = set()
        for o in ol:
            for ip in o.get('intermediates', []): ai.add(ip)
        v = t * 100 + m * 10 + g * 5 + len(ai) * 150
        if v > best_val:
            best_val = v; best_set = ol

    if best_set:
        world.control_buffs = {
            'trade_efficiency': max(o['trade_bonus'] for o in best_set),
            'mfg_productivity': max(o['mfg_bonus'] for o in best_set),
            'gold_productivity': max(o['gold_bonus'] for o in best_set),
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

def _apply_faction_bonus(ops, faction_counts):
    """给制造站候选人加派系加成 (通过检查技能名)"""
    # 造高昂 #26: 娜斯提 E2 — 每莱茵生命+3% (≤5)
    # 挑大梁 #28: 杏仁 E2 — 每黑钢国际+2% (≤3)
    for op in ops:
        bonus = 0
        details = op.get('details', '')
        if '造高昂' in details:
            bonus += min(faction_counts.get('莱茵生命', 0), 5) * 3
        if '挑大梁' in details:
            bonus += min(faction_counts.get('黑钢国际', 0), 3) * 2
        op['_faction_bonus'] = bonus
    return ops


# ============================================================
# 管线入口
# ============================================================

# ============================================================
# 层4c: 中间产物 (生成→消费)
# ============================================================

def layer4c_compute_products(world, data):
    """根据中枢5人 assignment 计算中间产物生成量"""
    cb = world.control_buffs
    best_5 = cb.get('best_5', [])
    if not best_5:
        world.intermediates = {}
        return world

    # 生成量 (假设最优 mood 条件)
    products = {
        'renjian_yanhuo': 0,   # 人间烟火
        'reqingzhi': 0,        # 热情值
        'ganzhi_xinxi': 0,     # 感知信息
        'mutianliao': 0,       # 木天蓼
        'wusasi_teyin': 0,     # 乌萨斯特饮
        'qingbao_chubei': 0,   # 情报储备
    }

    buffs = data['all_facility_skills']['buffs']
    ops_raw = data['all_facility_skills']['operators']

    for op_info in best_5:
        cid = None
        # Find charId from name (reverse lookup)
        for c, info in ops_raw.items():
            if cn_name(c, data) == op_info['name']:
                cid = c; break
        if not cid: continue

        # Check this operator's skills for product generation
        info = ops_raw.get(cid, {})
        for slot in info.get('slots', []):
            for sk in slot['skills']:
                if sk['elite'] > op_info.get('elite', 2): continue
                b = buffs.get(sk['buffId'], {})
                if b.get('roomType', '') != 'CONTROL': continue
                desc = re.sub(r'<[^>]+>', '', b.get('description', ''))
                name = b.get('name', '')

                if '人间烟火' in desc:
                    if '15' in desc: products['renjian_yanhuo'] += 15
                    elif '5' in desc: products['renjian_yanhuo'] += 5  # per 岁
                if '热情值' in desc:
                    if '10' in desc: products['reqingzhi'] += 10
                    elif '1' in desc: products['reqingzhi'] += 20  # per dorm op estimate
                if '感知信息' in desc:
                    if '10' in desc: products['ganzhi_xinxi'] += 10
                if '木天蓼' in desc:
                    if '8' in desc: products['mutianliao'] += 8
                    elif '2' in desc: products['mutianliao'] += 4
                if '乌萨斯特饮' in desc:
                    if '1' in desc: products['wusasi_teyin'] += 3
                if '情报储备' in desc:
                    if '1' in desc: products['qingbao_chubei'] += 2

    world.intermediates = products
    return world


def layer4c_apply_consumption(world, data):
    """将中间产物应用到下游: 制造站产能修正, 贸易站效率修正"""
    im = world.intermediates
    if not im: return world

    # 制造站修正 (注入到 control_buffs)
    mfg_extra = 0.0
    mfg_extra += im.get('renjian_yanhuo', 0) / 3.0 * 1.0    # 稻禾厚: 3点→+1%
    mfg_extra += im.get('ganzhi_xinxi', 0) / 2.0 * 1.0      # 念力: 2点→+1% (via 思维链环)
    mfg_extra += im.get('mutianliao', 0) * 1.0              # 可靠随从: 1点→+1%
    # 巫术结晶链: 人间烟火→古老巫术(5→1)→问枯荣(1→2%)+逐水草(1→1%)
    wushu = im.get('renjian_yanhuo', 0) // 5                  # 巫术结晶数量
    mfg_extra += wushu * 2.0                                 # 问枯荣: 1结晶→+2%
    mfg_extra += wushu * 1.0                                 # 逐水草: 1结晶→+1%

    # 贸易站修正
    trade_extra = 0.0
    trade_extra += im.get('renjian_yanhuo', 0) * 1.0         # 愿者上钩: 1点→+1%
    trade_extra += im.get('mutianliao', 0) * 3.0             # 艾露猫: 1点→+3%

    cb = world.control_buffs
    cb['trade_efficiency'] = cb.get('trade_efficiency', 0) + trade_extra
    cb['mfg_productivity'] = cb.get('mfg_productivity', 0) + mfg_extra
    return world


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
        # 层4c: 计算产品 + 应用到下游
        world = layer4c_compute_products(world, data)
        world = layer4c_apply_consumption(world, data)
        world, _ = layer3_inject(world, data)  # 用更新后的buff重算
        if not changed:
            print('  迭代{}: 收敛'.format(iteration + 1))
            break
        print('  迭代{}: 更新'.format(iteration + 1))
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
    print('=== 层4c: 中间产物 ===')
    im = getattr(world, 'intermediates', {})
    if im:
        for k, v in im.items():
            print('  {}: {}'.format(k, v))
    else:
        print('  (未计算)')

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

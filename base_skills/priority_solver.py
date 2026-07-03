"""
优先级排班求解器

目标 (字典序):
  1. 贸易站龙门币最大化
  2. 赤金(直接卖)最大化
  3. 经验最大化

假设: 1赤金=500LMD (直接卖), 贸易消耗的赤金由制造站供应(不冲突)
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
GOLD_PRICE = 500  # 1赤金直接卖 = 500 LMD
HOURS = 12

# A1 小队
A1_SQUAD = {'芬', '克洛丝', '米格鲁', '炎熔', '芙蓉', '历阵锐枪芬', '寒芒克洛丝'}

with open(os.path.join(DIR, 'all_facility_skills.json'), 'r', encoding='utf-8') as f:
    all_data = json.load(f)

# ============================================================
# 导入 solver_core 的核心函数
# ============================================================
sys.path.insert(0, DIR)
from solver_core import (
    extract_pct, calc_ramp_avg, build_candidates, resolve_trio,
    TRADING_POSTS, POWER_PLANTS, DORMS, DORM_LEVEL, TRAINING_LEVEL, ROBOTS
)

# ============================================================
# 贸易站评分: 效率 × 上限
# ============================================================
def trading_score(trio, data):
    """计算贸易站三人组的 LMD 产出评分"""
    total_prod, resolved = resolve_trio(trio, data)
    # 这里 resolve_trio 用的是制造站的产能模型, 需要适配贸易站
    # 暂时用效率之和作为近似
    return total_prod

# ============================================================
# 主流程: 优先级分配
# ============================================================
def solve_priority():
    used_ops = set()

    # 1. 贸易站×2 (TRADING)
    print('=== 优先级1: 贸易站龙门币 ===')
    trading_results, trading_ops, _ = solve_facility('TRADING', None, used_ops)
    t_a = trading_results[0]
    used_ops.update(op['charId'] for op in t_a['ops'])
    t_b = best_excluding(trading_ops, used_ops)
    used_ops.update(op['charId'] for op in t_b['ops'])

    cn = lambda op: op.get('cn_name', op['charId'])
    print(f'  贸易A: {t_a["total"]:+.0f}  ({", ".join(cn(op) for op in t_a["ops"])})')
    print(f'  贸易B: {t_b["total"]:+.0f}  ({", ".join(cn(op) for op in t_b["ops"])})')

    # 2. 赤金站×2 (gold)
    print('\n=== 优先级2: 赤金(直接卖) ===')
    gold_results, gold_ops, _ = solve_facility('MANUFACTURE', 'gold', used_ops)
    g_a = gold_results[0]
    used_ops.update(op['charId'] for op in g_a['ops'])
    g_b = best_excluding(gold_ops, used_ops)
    used_ops.update(op['charId'] for op in g_b['ops'])

    print(f'  赤金A: {g_a["total"]:+.0f}%  ({", ".join(cn(op) for op in g_a["ops"])})')
    print(f'  赤金B: {g_b["total"]:+.0f}%  ({", ".join(cn(op) for op in g_b["ops"])})')

    # 3. 经验站×2 (combat_record)
    print('\n=== 优先级3: 经验 ===')
    exp_results, exp_ops, _ = solve_facility('MANUFACTURE', 'combat_record', used_ops)
    e_a = exp_results[0]
    used_ops.update(op['charId'] for op in e_a['ops'])
    e_b = best_excluding(exp_ops, used_ops)

    print(f'  经验A: {e_a["total"]:+.0f}%  ({", ".join(cn(op) for op in e_a["ops"])})')
    print(f'  经验B: {e_b["total"]:+.0f}%  ({", ".join(cn(op) for op in e_b["ops"])})')

    print(f'\n总用干员: {len(used_ops)}')
    return {
        'trading': [t_a, t_b],
        'gold': [g_a, g_b],
        'exp': [e_a, e_b],
    }


# ============================================================
# 辅助
# ============================================================
def solve_facility(room, recipe, exclude):
    """求解设施, 排除指定干员"""
    from solver_core import solve
    results, ops, data = solve(room, recipe, HOURS)
    ops = [op for op in ops if op['charId'] not in exclude]
    # 重新枚举
    new_results = []
    for trio in combinations(ops, 3):
        total, _ = resolve_trio(trio, data)
        if total > 0: new_results.append({'total': total, 'ops': trio})
    new_results.sort(key=lambda x: -x['total'])
    return new_results, ops, data

def best_excluding(ops, exclude):
    data = all_data
    remaining = [op for op in ops if op['charId'] not in exclude]
    best = None
    for trio in combinations(remaining, 3):
        total, _ = resolve_trio(trio, data)
        if best is None or total > best['total']:
            best = {'total': total, 'ops': trio}
    return best


if __name__ == '__main__':
    solve_priority()

# -*- coding: utf-8 -*-
# ----------------------------------------------------------------------------------------------------------------------
#  Save_Results.py
#
#  本地新增的优化结果存盘工具（2026-10-21 添加，非 RCAIDE 官方文件）
#
#  作用：把 Nexus 优化问题的设计变量、目标、约束、每次迭代历史，
#        以及设计任务的逐段结果写成 JSON，便于事后分析、画图、写报告。
#
#  产出文件（默认与 Optimize.py 同目录）：
#    optimization_results.json   优化终态汇总（含设计变量/目标/约束/任务剖面）
#    optimization_history.json   每次迭代一条记录（供收敛曲线）
#
#  用法（已在 Procedure.py 与 Optimize.py 中自动调用）：
#    import Save_Results
#    Save_Results.save_optimization_results(nexus)
#    Save_Results.append_iteration(nexus)
#
#  保存失败会明确报错；Procedure 中的历史存盘仍由其调用方处理异常。
# ----------------------------------------------------------------------------------------------------------------------
import json
import os
from datetime import datetime, timezone

import numpy as np

from RCAIDE.Framework.Optimization.Common import get_values

_HERE = os.path.dirname(os.path.abspath(__file__))


# ----------------------------------------------------------------------------------------------------------------------
#  内部工具
# ----------------------------------------------------------------------------------------------------------------------
def _f(value, index=0):
    """把任意数值/数组安全转成 float（失败返回 None）。"""
    if value is None:
        return None
    try:
        arr = np.asarray(value, dtype=float).ravel()
        if arr.size == 0:
            return None
        out = float(arr[index if abs(index) < arr.size else 0])
        return out if np.isfinite(out) else None
    except Exception:
        return None


def _get(dictionary, aliases, tag):
    """按 tag 取单个标量值。"""
    try:
        vals = get_values(dictionary, tag, aliases)
        return _f(vals)
    except Exception:
        return None


def _dump(path, payload):
    try:
        with open(path, 'w', encoding='utf-8') as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=1, allow_nan=False)
        return True
    except Exception as err:                                     # pragma: no cover
        print('[Save_Results] 写入失败 %s : %s' % (path, err))
        return False


# ----------------------------------------------------------------------------------------------------------------------
#  任务剖面
# ----------------------------------------------------------------------------------------------------------------------
def mission_summary(results):
    """把一次任务求解结果整理成 逐段记录 + 全局汇总。"""
    out = {'segments': []}
    try:
        segments = list(results.segments)
    except Exception as err:
        return {'error': '%s: %s' % (type(err).__name__, err), 'segments': []}

    for seg in segments:
        rec = {'tag': getattr(seg, 'tag', '?')}
        try:
            cond     = seg.conditions
            inertial = getattr(cond, 'frames', None)
            inertial = getattr(inertial, 'inertial', None) if inertial is not None else None
            free     = getattr(cond, 'freestream', None)
            weights  = getattr(cond, 'weights', None)
            vehicle  = getattr(weights, 'vehicle', None) if weights is not None else None
            mass     = getattr(vehicle, 'mass', None) if vehicle is not None else None

            rec['time_s']        = _f(getattr(inertial, 'time', None), -1)
            rec['range_m']       = _f(getattr(inertial, 'aircraft_range', None), -1)
            rec['mach']          = _f(getattr(free, 'mach_number', None), -1)
            rec['alt_m']         = _f(getattr(free, 'altitude', None), -1)
            rec['mass_start_kg'] = _f(mass, 0)
            rec['mass_end_kg']   = _f(mass, -1)
            if all(rec.get(k) is None for k in ('time_s', 'range_m', 'mass_start_kg')):
                rec['error'] = '该段无可提取的状态量'
        except Exception as err:
            rec['error'] = '%s: %s' % (type(err).__name__, err)
        out['segments'].append(rec)

    ok = [r for r in out['segments'] if 'error' not in r and r.get('mass_start_kg') is not None]
    if ok:
        first, last = ok[0], ok[-1]
        total_time  = last.get('time_s') or 0.0
        total_range = last.get('range_m') or 0.0
        m0, m1      = first['mass_start_kg'], last['mass_end_kg']
        out['mission'] = {
            'total_time_s':     round(total_time, 1),
            'total_time_min':   round(total_time / 60.0, 1),
            'total_range_m':    round(total_range, 1),
            'total_range_nmi':  round(total_range / 1852.0, 1),
            'takeoff_mass_kg':  round(m0, 1),
            'landing_mass_kg':  round(m1, 1),
            'total_fuel_kg':    round(m0 - m1, 1),
            'fuel_fraction':    round((m0 - m1) / m0, 4) if m0 else None,
        }
    return out


# ----------------------------------------------------------------------------------------------------------------------
#  优化终态汇总
# ----------------------------------------------------------------------------------------------------------------------
def _design_values(nexus):
    """从 nexus 收设计变量当前值。

    不用 RCAIDE 的 get_values：它对含通配符 '*' 的别名路径会抛 TypeError
    （见 helper_functions.get_values）。这里直接从优化问题与 summary 读。
    """
    prob = getattr(nexus, 'optimization_problem', None)
    if prob is None:
        return [], {}
    inputs = getattr(prob, 'inputs', None)
    if inputs is None:
        return [], {}

    aliases = getattr(prob, 'aliases', None)
    alias_map = {}
    try:
        for a in aliases:
            if isinstance(a, (list, tuple)) and len(a) >= 2:
                alias_map[str(a[0])] = a[1]
    except Exception:
        alias_map = {}

    out = []
    for i in range(len(inputs)):
        tag = str(inputs[i, 0])
        # 注意：RCAIDE 的 scale_input_values 会原地改写 inputs[:,1]，
        # 所以这里读到的已是「求解器最后一次评估值」，不是配置的初值。
        # 真正的初值请查 Optimize.py 的 problem.inputs 定义（第 2 列）。
        rec = {'tag': tag, 'value_in_inputs': _f(inputs[i, 1]),
               'last_evaluated': _f(inputs[i, 1]),
               'initial': getattr(nexus, 'initial_design_values', {}).get(tag),
               'scale': _f(inputs[i, 4]), 'unit_to_si': _f(inputs[i, 5]),
               'lower': _f(inputs[i, 2]), 'upper': _f(inputs[i, 3])}
        # 单值路径（不含 *）可从 summary / 结果里取，多构型路径只能记录别名
        ptr = alias_map.get(tag)
        rec['alias'] = ptr if isinstance(ptr, (str, list)) else None
        out.append(rec)
    return out, alias_map


def _solver_optimum(solution):
    """读取求解器返回的缩放坐标；返回坐标本身不证明收敛。"""
    if solution is None:
        return None
    x = getattr(solution, 'x', None)
    if x is None and isinstance(solution, (list, tuple)) and len(solution) > 0:
        x = solution[0]
    if x is None:
        return None
    try:
        arr = np.asarray(x, dtype=float).ravel()
        return arr if arr.size else None
    except Exception:
        return None


def _solver_info(solution):
    """求解器状态摘要。"""
    if isinstance(solution, (list, tuple)) and len(solution) == 5:
        return {'name': 'SLSQP', 'fun': _f(solution[1]),
                'nit': int(solution[2]), 'status': int(solution[3]),
                'success': int(solution[3]) == 0, 'message': str(solution[4])}
    info = {}
    for key in ('success', 'status', 'message', 'nit', 'fun', 'nfev', 'maxcv',
                'solver_name', 'mission_evaluations', 'unique_candidate_evaluations',
                'final_state_matches_solver_x'):
        val = getattr(solution, key, None)
        if val is None:
            continue
        try:
            if isinstance(val, (bool, np.bool_)):
                info[key] = bool(val)
            elif isinstance(val, str):
                info[key] = val
            elif isinstance(val, (int, np.integer)):
                info[key] = int(val)
            else:
                info[key] = _f(val)
        except Exception:
            info[key] = str(val)
    return info


def _summary_scalars(nexus):
    """直接读 nexus.summary 上的标量（RCAIDE 优化器的约定字段）。"""
    s = getattr(nexus, 'summary', None)
    keys = ['fuel_burn', 'fuel_margin', 'range_residual', 'max_throttle']
    prob = getattr(nexus, 'optimization_problem', None)
    if prob is not None:
        for name in ('objective', 'constraints'):
            table = getattr(prob, name, None)
            if table is not None:
                keys.extend(str(row[0]) for row in table)
    return {k: _f(getattr(s, k, None)) for k in keys if getattr(s, k, None) is not None}


def save_optimization_results(nexus, solution=None, out_dir=None,
                             filename='optimization_results.json'):
    """把优化问题终态写成 JSON。不依赖 get_values，避免通配符别名报错。

    initial 是运行入口记录的初值；last_evaluated 是当前问题状态。
    solver_returned_* 是求解器返回的候选点，不自动表示收敛。
    只有 success=True 且当前状态与返回点一致时，才另填 optimal_*。
    *_in_units 使用输入表声明单位，*_si 使用 SI 单位。
    """
    out_dir = out_dir or getattr(nexus, 'results_directory', None) or _HERE
    os.makedirs(out_dir, exist_ok=True)
    payload = {
        'source': 'RCAIDE Optimization_Wing_Planform_Fuel_Burn + Save_Results.py',
        'total_iterations': int(getattr(nexus, 'total_number_of_iterations', -1)),
        'performance_evaluations': int(getattr(nexus, 'total_number_of_iterations', -1)),
        'total_iterations_meaning': 'Procedure.post_process evaluations, not solver generations',
        'saved_at_utc': datetime.now(timezone.utc).isoformat(),
    }

    dv, alias_map = _design_values(nexus)
    if dv:
        payload['design_variables'] = dv

    # Separate returned candidates from the last evaluated state and convergence.
    solver_info = _solver_info(solution) if solution is not None else {}
    opt_x = _solver_optimum(solution)
    if dv and opt_x is not None:
        inputs = nexus.optimization_problem.inputs
        if len(opt_x) != len(dv):
            raise ValueError('Solver design length does not match the input table.')
        matches = np.allclose(np.asarray(inputs[:, 1], dtype=float),
                              opt_x * np.asarray(inputs[:, 4], dtype=float),
                              rtol=1e-12, atol=1e-12)
        payload['state_matches_solver_x'] = bool(matches)
        payload['design_state'] = 'solver_returned_candidate' if matches else 'last_evaluated_only'
        for i, rec in enumerate(dv):
            declared_value = float(opt_x[i]) * float(inputs[i, 4])
            rec['solver_returned_scaled'] = float(opt_x[i])
            rec['solver_returned_in_units'] = declared_value
            rec['solver_returned_si'] = declared_value * float(inputs[i, 5])
            if solver_info.get('success') and matches:
                rec['optimal_scaled'] = float(opt_x[i])
                rec['optimal'] = declared_value
                rec['optimal_in_units'] = declared_value
                rec['optimal_si'] = rec['solver_returned_si']

    payload['solver'] = solver_info
    payload['run_configuration'] = getattr(solution, 'run_configuration', {})
    payload['generation_history'] = [
        {k: (_f(v) if isinstance(v, (float, np.floating)) else v) for k, v in row.items()}
        for row in getattr(solution, 'generation_history', [])
    ]

    prob = getattr(nexus, 'optimization_problem', None)

    # 目标（只记声明，当前值从 summary 取同名标量）
    try:
        obj = prob.objective
        tag = str(obj[0, 0])
        payload['objective'] = {'tag': tag, 'scaling': _f(obj[0, 1]),
                                'value': _summary_scalars(nexus).get(tag)}
    except Exception as err:
        payload['objective_error'] = '%s: %s' % (type(err).__name__, err)

    # 约束（声明 + summary 里的同名值）
    try:
        cons = prob.constraints
        scal = _summary_scalars(nexus)
        rows = []
        for i in range(len(cons)):
            tag = str(cons[i, 0])
            rows.append({'tag': tag, 'sense': str(cons[i, 1]), 'edge': _f(cons[i, 2]),
                         'edge_si': _f(float(cons[i, 2]) * float(cons[i, 4])),
                         'unit_to_si': _f(cons[i, 4]),
                         'value': scal.get(tag), 'satisfied': None})
            if rows[-1]['value'] is not None and rows[-1]['edge'] is not None:
                v, e, sd = rows[-1]['value'], rows[-1]['edge_si'], rows[-1]['sense']
                rows[-1]['satisfied'] = (v >= e) if sd == '>' else ((v <= e) if sd == '<' else abs(v - e) < 1e-9)
        payload['constraints'] = rows
        payload['constraint_feasible'] = all(row['satisfied'] is True for row in rows)
    except Exception as err:
        payload['constraints_error'] = '%s: %s' % (type(err).__name__, err)

    scal = _summary_scalars(nexus)
    if scal:
        payload['summary'] = scal

    try:
        payload['design_mission'] = mission_summary(nexus.results.base_mission)
    except Exception as err:
        payload['design_mission_error'] = '%s: %s' % (type(err).__name__, err)

    if not _dump(os.path.join(out_dir, filename), payload):
        raise OSError('Optimization results could not be saved.')
    print('[Save_Results] 已写出 %s' % os.path.join(out_dir, filename))
    return payload


def append_iteration(nexus, out_dir=None):
    """每次 post_process 追加一条迭代记录。"""
    out_dir = out_dir or getattr(nexus, 'results_directory', None) or _HERE
    os.makedirs(out_dir, exist_ok=True)
    path    = os.path.join(out_dir, 'optimization_history.json')

    rec = {'iteration': int(getattr(nexus, 'total_number_of_iterations', -1))}
    rec['record_type'] = 'performance_evaluation'
    rec['observed_at_utc'] = datetime.now(timezone.utc).isoformat()
    rec['design_inputs_in_declared_units'] = {
        str(row[0]): _f(row[1]) for row in nexus.optimization_problem.inputs
    }
    rec.update(_summary_scalars(nexus))

    path_file = path
    history = []
    if os.path.isfile(path_file):
        try:
            with open(path_file, 'r', encoding='utf-8') as fh:
                loaded = json.load(fh)
            if isinstance(loaded, list):
                history = loaded
        except Exception:
            history = []
    history.append(rec)
    if not _dump(path_file, history):
        raise OSError('Performance evaluation history could not be saved.')
    print('[Save_Results] Evaluation %s recorded (%d rows)' % (rec['iteration'], len(history)), flush=True)
    return rec

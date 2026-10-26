# -*- coding: utf-8 -*-
# ----------------------------------------------------------------------------------------------------------------------
#  Run_Optimize_Quick.py
#
#  本地新增（2026-10-21）：优化快速启动脚本，不修改官方 Optimize.py
#
#  为什么需要它：
#    官方 Optimize.py 默认 show_desing_space = True，会先做 3x3 设计空间采样
#    （约 9-12 次任务求解），加上代理模型每次重训，首次运行约 1.5-2 小时。
#    本脚本关掉设计空间采样、迭代次数可控，适合先跑通再谈精度。
#
#  用法（在 PowerShell 中）：
#    # 默认：2 次迭代，不出设计空间图（约 60-70 分钟）
#    python Run_Optimize_Quick.py
#
#    # 极速冒烟测试：1 次迭代（约 30-35 分钟），只验证流程能跑通
#    $env:OPT_ITER=1; python Run_Optimize_Quick.py
#
#    # 认真求最优：10 次迭代 + 小扰动步长（数小时，建议后台跑）
#    $env:OPT_ITER=10; $env:OPT_SENSE_STEP=1e-4; $env:OPT_TOL=1e-2; python Run_Optimize_Quick.py
#
#    # 想要设计空间图（回到官方行为）
#    $env:OPT_SHOW_SPACE=1; python Run_Optimize_Quick.py
#
#  环境变量：
#    OPT_ITER        迭代次数，默认 2
#    OPT_SENSE_STEP  有限差分步长，默认 1e-2（小=更准但更慢，官方严肃配置为 1e-4）
#    OPT_TOL         收敛容差，默认 1e-1（官方严肃配置为 1e-2）
#    OPT_SHOW_SPACE  设为 1 时生成设计空间图，默认 0
#    OPT_SOLVER      求解器，默认 SLSQP
#
#  产出：与 Optimize.py 相同的 optimization_results.json / optimization_history.json
# ----------------------------------------------------------------------------------------------------------------------
import os
import sys
import time

# 确保能 import 同目录的模块（无论从哪个目录启动）
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)
os.chdir(_HERE)

import matplotlib
matplotlib.use('Agg')          # 不弹窗，图只存文件（服务器/长跑必须）
import matplotlib.pyplot as plt

from RCAIDE.Framework.Optimization.Packages.scipy import scipy_setup
from RCAIDE.Framework.Optimization.Common import (generate_carpet_plot,
                                                  generate_line_plot,
                                                  print_optimization_results)
import Optimize          # 复用官方的优化问题定义
import Save_Results      # 本地新增的存盘模块


def main():
    # ---------------- 读取配置 ----------------
    n_iter      = int(os.environ.get('OPT_ITER', '2'))
    sense_step  = float(os.environ.get('OPT_SENSE_STEP', '1e-2'))
    tolerance   = float(os.environ.get('OPT_TOL', '1e-1'))
    show_space  = os.environ.get('OPT_SHOW_SPACE', '0') == '1'
    solver      = os.environ.get('OPT_SOLVER', 'SLSQP')
    fix_range   = os.environ.get('OPT_FIX_RANGE', '1') == '1'

    print('=' * 70)
    print('  RCAIDE 优化快速启动')
    print('=' * 70)
    print('  求解器      : %s' % solver)
    print('  迭代次数    : %d' % n_iter)
    print('  差分步长    : %g' % sense_step)
    print('  容差        : %g' % tolerance)
    print('  设计空间图  : %s' % ('生成' if show_space else '跳过（省约 25-30 分钟）'))
    print('  航程约束    : %s' % ('已修正（实际航程 >= 设计航程）' if fix_range
                                  else '保持官方原样（注意：官方方向是反的，见下）'))
    print('=' * 70)

    # ---------------- 建问题 ----------------
    t0 = time.time()
    problem = Optimize.define_optimization_problem()
    print('[1] 优化问题已建立  (%.1f s)' % (time.time() - t0))

    print('    设计变量:')
    for row in problem.optimization_problem.inputs:
        print('      %-18s 初值=%-8g 范围=[%g, %g]' % (row[0], row[1], row[2], row[3]))
    print('    目标    : %s' % problem.optimization_problem.objective[0, 0])
    print('    约束    : %s' % ', '.join(str(c[0]) for c in problem.optimization_problem.constraints))
    print('    机型配置: %d 个' % len(problem.vehicle_configurations))
    print('    任务航段: %d 段' % len(problem.missions.base_mission.segments))

    # ---------------- 修正官方教程里方向写反的航程约束 ----------------
    # Procedure.post_process 里: range_residual = design_range - actual_range
    # 官方 Optimize.py 声明: range_residual > 0
    # 展开即: design_range - actual_range > 0  =>  actual_range < design_range
    # 也就是「实际航程必须小于设计航程」——与优化意图完全相反。
    # 由于目标是最小化燃油，优化器会不断缩短航程来「省油」，
    # 结果看似收敛，实则无意义（实测：燃油 9015 -> 4615 kg，航程 1468 -> 436 nmi）。
    # 正确方向应为 range_residual < 0，即 actual_range > design_range。
    if fix_range:
        cons = problem.optimization_problem.constraints
        flipped = []
        for i in range(len(cons)):
            if str(cons[i, 0]) == 'range_residual' and str(cons[i, 1]) == '>':
                cons[i, 1] = '<'
                flipped.append(str(cons[i, 0]))
        if flipped:
            print()
            print('  [修正] 已把约束 %s 的方向由 > 改为 <' % ', '.join(flipped))
            print('         原因: range_residual = 设计航程 - 实际航程,')
            print('               官方写 ">0" 等于要求"实际航程 < 设计航程",方向反了。')
            print('               改为 "<0" 才是"实际航程 >= 设计航程"。')
            print('         如需保留官方原样: 设 OPT_FIX_RANGE=0')
        print()
        for i in range(len(cons)):
            print('        约束: %-16s %s %-6s (当前值见结果)' % (cons[i, 0], cons[i, 1], cons[i, 2]))

    # ---------------- 可选：设计空间 ----------------
    if show_space:
        print()
        print('[2] 生成设计空间图（较慢，约 25-30 分钟）...')
        t = time.time()
        generate_carpet_plot(problem,
                             design_input_1_index=0,
                             design_input_2_index=1,
                             number_of_points=3,
                             generate_objective_plot=True,
                             objective_plot_constraint_index=0,
                             generate_constraint_plots=True)
        generate_line_plot(problem,
                           design_input_1_index=0,
                           number_of_points=3,
                           plot_objective=True,
                           plot_constraint=True)
        plt.savefig(os.path.join(_HERE, 'design_space.png'), dpi=110, bbox_inches='tight')
        print('    设计空间图已存 design_space.png  (%.1f min)' % ((time.time() - t) / 60))
    else:
        print()
        print('[2] 跳过设计空间图')

    # ---------------- 求解 ----------------
    print()
    print('[3] 开始优化（每次任务求解约 2.8 分钟，请耐心）...')
    t = time.time()
    try:
        solution = scipy_setup.SciPy_Solve(problem,
                                           solver=solver,
                                           sense_step=sense_step,
                                           iter=n_iter,
                                           tolerance=tolerance)
    except Exception as err:
        print('[!] 求解中断: %s: %s' % (type(err).__name__, err))
        raise
    elapsed = time.time() - t
    print('[3] 求解完成，用时 %.1f 分钟' % (elapsed / 60))

    # ---------------- 输出 ----------------
    print()
    try:
        print_optimization_results(problem)
    except Exception as err:
        # 官方打印器对带 '*' 的别名路径会抛异常，这里不阻断存盘
        print('[!] print_optimization_results 失败（已知的 get_values 限制）: %s' % err)

    print()
    try:
        Save_Results.save_optimization_results(problem, solution=solution)
    except Exception as err:
        print('[!] 结果存盘失败: %s' % err)

    print()
    print('=' * 70)
    print('  完成。产出文件：')
    print('    optimization_results.json   优化终态 + 设计任务逐段结果')
    print('    optimization_history.json   每次迭代记录')
    print('=' * 70)


if __name__ == '__main__':
    main()

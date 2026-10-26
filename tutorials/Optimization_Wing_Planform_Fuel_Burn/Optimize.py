# Local changes maintained by QingYangJin; modified-version notice: 2026-10-26.
# Based on RCAIDE-LEADS; original notices are retained. See docs/UPSTREAM.md.
# ----------------------------------------------------------------------------------------------------------------------
#  IMPORT
# ---------------------------------------------------------------------------------------------------------------------- 
# Keep resource settings above imports so spawned processes inherit the BLAS limit.
import os

# Three variables * multiplier 8 = 24 candidates per generation.
DE_OPTIONS = dict(max_generations=50, population_multiplier=8,
                  tolerance=0.001, seed=42, display=True,
                  parallel_workers=24, blas_threads=2, cpu_limit_percent=60)

for _variable in ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS'):
    os.environ[_variable] = str(DE_OPTIONS['blas_threads'])

# RCAIDE imports
import RCAIDE 
from RCAIDE.Framework.Core import Units, Data
from RCAIDE.Framework.Optimization.Common import * 
from Differential_Evolution import solve as solve_differential_evolution

# local file imports 
import Vehicles     # defines aircraft 
import Analyses     # defines analyses
import Missions     # defines flight profile 
import Procedure    # defines optimization interation process  
import Save_Results # 本地新增：结果存盘（2026-10-21）

# python imports 
import matplotlib.pyplot as plt
import numpy as np
import time 
from datetime import datetime
from pathlib import Path
import json


# The first nominal candidate measures worker memory before batch dispatch.
# parallel_workers is an upper bound; memory headroom can reduce the actual count.

# ----------------------------------------------------------------------        
#  Main Script
# ----------------------------------------------------------------------  
def main():
    
    # define optmiztion problem
    problem = define_optimization_problem()

    show_desing_space = False

    # Each launch gets its own history/results; existing SLSQP files are retained.
    out_dir = Path(__file__).resolve().parent / 'runs' / datetime.now().strftime('DE_%Y%m%d_%H%M%S_%f')
    out_dir.mkdir(parents=True, exist_ok=False)
    problem.results_directory = str(out_dir)
    problem.initial_design_values = {
        str(row[0]): float(row[1]) for row in problem.optimization_problem.inputs
    }
    with (out_dir / 'run_configuration.json').open('w', encoding='utf-8') as stream:
        json.dump(dict(solver='differential_evolution', options=DE_OPTIONS,
                       initial_design=problem.initial_design_values,
                       show_design_space=show_desing_space), stream, indent=2)
    print('[DE] Output directory: ' + str(out_dir), flush=True)
    
    # show design space with carpet and line plots  
    if show_desing_space:
        carpet_plot_data =generate_carpet_plot(problem,
                    design_input_1_index            = 0, 
                    design_input_2_index            = 1,                
                    number_of_points                = 3,
                    generate_objective_plot         = True, 
                    objective_plot_constraint_index = 0, 
                    generate_constraint_plots       = True)
        
        # create line plot 
        line_plot_data =generate_line_plot(problem,
                design_input_1_index = 0, 
                number_of_points     = 3, 
                plot_objective       = True,
                plot_constraint      = True) 

        # Plot scans mutate the input table; preserve the nominal DE seed point.
        for row in problem.optimization_problem.inputs:
            row[1] = problem.initial_design_values[str(row[0])]
     
    # start clock 
    ti = time.time()
    
    regression_solution = solve_differential_evolution(problem, **DE_OPTIONS)
    
    # stop clock 
    tf                   = time.time()
    elapsed_time         = round((tf-ti)/60,2)
    print('Simulation Time: ' + str(elapsed_time) + ' mins')    

    print('[DE] Solver converged: ' + str(regression_solution.success))
    print('[DE] Stop reason: ' + str(regression_solution.message))
    print('[DE] Generations: %d; Mission evaluations: %d' % (
        regression_solution.nit, regression_solution.mission_evaluations))

    # ------------------------------------------------------------------
    #  本地新增：把优化终态写成 JSON（设计变量/目标/约束/任务剖面）
    # ------------------------------------------------------------------
    saved = Save_Results.save_optimization_results(problem, solution=regression_solution)
    print('[DE] Constraint feasible: ' + str(saved.get('constraint_feasible')))
    print('[DE] Fuel burn: %.3f kg; range residual (target - actual): %.3f m' % (
        problem.summary.fuel_burn, problem.summary.range_residual))
    
    return

# ----------------------------------------------------------------------        
#   Inputs, Objective, & Constraints
# ----------------------------------------------------------------------  
def define_optimization_problem():

    nexus = Nexus()
    problem = Data()
    nexus.optimization_problem = problem

    # -------------------------------------------------------------------
    # Inputs - i.e. design variables 
    # ------------------------------------------------------------------- 
    #   [ tag                   , initial,     lb , ub        , scaling , units ]
    problem.inputs = np.array([
        [ 'wing_area'           ,  92     ,    50. ,   130.    ,   100.  , 1*Units.meter**2],
        [ 'cruise_altitude'     ,   10    ,    8.1 ,    12.    ,   10.   , 1*Units.km],
        [ 'cruise_distance'     ,  1000   ,   10.  ,   5000.   ,   1000. , 1*Units.nmi   ],
    ],dtype=object)

    # -------------------------------------------------------------------
    # Objective - i.e. goal 
    # -------------------------------------------------------------------

    # [ tag, scaling, units ]
    problem.objective = np.array([
        [ 'fuel_burn', 10000, 1*Units.kg ]
    ],dtype=object)
    
    # -------------------------------------------------------------------
    # Constraints 
    # -------------------------------------------------------------------
    
    # [ tag, sense, edge, scaling, units ]
    problem.constraints = np.array([
        [ 'fuel_margin' , '>', 0.15 , 1, 1*Units.less], # fuel margin defined here as fuel
        # residual = target - actual; reaching 1500 nmi requires residual <= 0.
        [ 'range_residual', '<', 0., 1500 * Units.nmi, 1 * Units.meter],
    ],dtype=object)
    
    # -------------------------------------------------------------------
    #  Aliases - links between user specified terms and RCAIDE terms 
    # -------------------------------------------------------------------
    
    # [ 'alias' , ['data.path1.name','data.path2.name'] ] 
    problem.aliases = [
        [ 'wing_area'                ,  ['vehicle_configurations.*.wings.main_wing.areas.reference','vehicle_configurations.*.reference_area' ]  ], 
        [ 'cruise_altitude'          ,  ['missions.base_mission.segments.climb_3.altitude_end', 'missions.base_mission.segments.cruise.altitude', 'missions.base_mission.segments.descent_1.altitude_start']],
        [ 'cruise_distance'          ,  'missions.base_mission.segments.cruise.distance'                                                         ],
        [ 'fuel_burn'                ,  'summary.fuel_burn'                                                                                      ],
        [ 'range_residual'           ,  'summary.range_residual'                                                                                 ],
        [ 'fuel_margin'              ,  'summary.fuel_margin'                                                                                    ],
    ]     
    
    # -------------------------------------------------------------------
    #  Vehicles
    # -------------------------------------------------------------------
    nexus.vehicle_configurations = Vehicles.setup()
    
    # -------------------------------------------------------------------
    #  Analyses
    # -------------------------------------------------------------------
    nexus.analyses = Analyses.setup(nexus.vehicle_configurations)
    
    # -------------------------------------------------------------------
    #  Missions
    # -------------------------------------------------------------------
    nexus.missions = Missions.setup(nexus.analyses)
    
    # -------------------------------------------------------------------
    #  Procedure
    # -------------------------------------------------------------------    
    nexus.procedure = Procedure.setup()
    
    # -------------------------------------------------------------------
    #  Summary
    # -------------------------------------------------------------------    
    nexus.summary = Data()    
    nexus.total_number_of_iterations = 0
    return nexus
     
if __name__ == '__main__':
    main()
    plt.show()

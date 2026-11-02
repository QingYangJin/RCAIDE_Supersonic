# Observed installed-package API (P0 audit)

Only members whose __module__ starts with maml_opt are listed. No API is assumed beyond this table.

| module | kind | name | signature |
|---|---|---|---|
| maml_opt.contracts | class | AnalysisBackend | (*args, **kwargs) |
| maml_opt.contracts | class | BackendIdentity | (platform: str, version: str, model_fingerprint: str, data_origin: str, cost_unit: str = 'analysis_attempt') -> None |
| maml_opt.contracts | class | ConstraintSpec | (name: str, bound: float, sense: str = '<=', scale: float = 1.0, unit: str = '1') -> None |
| maml_opt.contracts | class | DesignSpace | (names: tuple, lower_bounds: tuple, upper_bounds: tuple, baseline: tuple, scales: tuple, units: tuple) -> None |
| maml_opt.contracts | class | EvaluationRequest | (design: Mapping, task: maml_opt.contracts.TaskSpec, fidelity: str, purpose: str = 'search') -> None |
| maml_opt.contracts | class | EvaluationResult | (objective: float / None, constraints_g_le_zero: Mapping, valid: bool = True, status: str = 'VALID', objective_model_eligible: bool = True, responses: Mapping = <factory>, diagnostics: Mapping = <factory>) -> None |
| maml_opt.contracts | class | TaskSpec | (task_id: str, context: Mapping = <factory>, model_config: Mapping = <factory>) -> None |
| maml_opt.contracts | function | fingerprint | (value) |
| maml_opt.contracts | function | finite_number | (value, name) |
| maml_opt.contracts | function | json_data | (value) |
| maml_opt.contracts | function | nonempty | (value, name) |
| maml_opt.initialization | class | DatasetError | None |
| maml_opt.initialization | class | DesignSpace | (names: tuple, lower_bounds: tuple, upper_bounds: tuple, baseline: tuple, scales: tuple, units: tuple) -> None |
| maml_opt.initialization | class | TaskDataset | (dataset_id, state, task_split_id, feature_names, design_feature_names, task_context_names, target_names, target_map, task_splits, records, excluded_records, source_runs, manifest_path, records_path) |
| maml_opt.initialization | function | build_task_conditioned_candidate_features | (candidate_designs, design_feature_names, task_context_names, target_task_context) |
| maml_opt.initialization | function | generate_initial_designs | (lower_bounds, upper_bounds, count, seed=42, baseline=None, method='lhs') |
| maml_opt.initialization | function | prepare_model_scored_initial_designs | (artifact, design_space, candidate_designs, design_feature_names, task_context_names, target_task_context, objective_target_name, constraint_target_names, initial_design_count, diversity_candidate_count, adaptation_method, candidate_pool_metadata, support_features=None, support_targets=None, support_observation_ids=None, inner_learning_rate=None, inner_steps=None, allow_synthetic_for_tests=False) |
| maml_opt.initialization | function | retrieve_similar_task_initial_designs | (dataset, target_task_context, context_scales, context_weights, objective_target_name, constraint_target_names, design_lower_bounds, design_upper_bounds, neighbor_task_count, initial_design_count, allow_synthetic_for_tests=False) |
| maml_opt.initialization | function | select_model_scored_initial_designs | (candidate_designs, predicted_targets_physical, target_names, objective_target_name, constraint_target_names, design_lower_bounds, design_upper_bounds, initial_design_count, diversity_candidate_count) |
| maml_opt.evaluation | class | BudgetExceeded | None |
| maml_opt.evaluation | class | EvaluationContext | (manager, request_id, call_limit) |
| maml_opt.evaluation | class | EvaluationManager | (backend, run_id, budget, output_root) |
| maml_opt.evaluation | class | EvaluationRequest | (design: Mapping, task: maml_opt.contracts.TaskSpec, fidelity: str, purpose: str = 'search') -> None |
| maml_opt.evaluation | class | EvaluationResult | (objective: float / None, constraints_g_le_zero: Mapping, valid: bool = True, status: str = 'VALID', objective_model_eligible: bool = True, responses: Mapping = <factory>, diagnostics: Mapping = <factory>) -> None |
| maml_opt.evaluation | function | atomic_json | (path, value) |
| maml_opt.evaluation | function | fingerprint | (value) |
| maml_opt.evaluation | function | json_data | (value) |
| maml_opt.evaluation | function | package_identity | () |
| maml_opt.evaluation | function | timestamp | () |
| maml_opt.bayesian | class | ConstrainedBayesianOptimizer | (lower_bounds, upper_bounds, seed=42, candidate_count=512, minimum_model_observations=None, alpha=1e-06, exploration=0.01) |
| maml_opt.bayesian | function | generate_initial_designs | (lower_bounds, upper_bounds, count, seed=42, baseline=None, method='lhs') |
| maml_opt.bayesian | function | run_search | (optimizer, evaluator, initial_designs, max_design_evaluations, strategy='bayesian', on_observation=None, initial_design_metadata=None) |
| maml_opt.campaign | class | ConstrainedBayesianOptimizer | (lower_bounds, upper_bounds, seed=42, candidate_count=512, minimum_model_observations=None, alpha=1e-06, exploration=0.01) |
| maml_opt.campaign | class | EvaluationManager | (backend, run_id, budget, output_root) |
| maml_opt.campaign | class | EvaluationRequest | (design: Mapping, task: maml_opt.contracts.TaskSpec, fidelity: str, purpose: str = 'search') -> None |
| maml_opt.campaign | function | atomic_json | (path, value) |
| maml_opt.campaign | function | finite_number | (value, name) |
| maml_opt.campaign | function | generate_initial_designs | (lower_bounds, upper_bounds, count, seed=42, baseline=None, method='lhs') |
| maml_opt.campaign | function | run_campaign | (backend, task, fidelity, output_root, run_id, total_analysis_budget, verification_budget=1, initial_design_count=5, max_design_evaluations=30, seed=42, strategy='bayesian', initial_designs=None, initial_design_metadata=None, verification_rtol=1e-06, verification_atol=1e-08, verification_fidelity=None) |
| maml_opt.campaign | function | run_search | (optimizer, evaluator, initial_designs, max_design_evaluations, strategy='bayesian', on_observation=None, initial_design_metadata=None) |
| maml_opt.cli | function | main | (argv=None) |
| maml_opt.learning.model | class | DatasetError | None |
| maml_opt.learning.model | class | Episode | (task_id: str, support: tuple, query: tuple, support_design_ids: tuple, query_design_ids: tuple) -> None |
| maml_opt.learning.model | class | MetaTaskBatch | (support_inputs: torch.Tensor, support_targets: torch.Tensor, query_inputs: torch.Tensor, query_targets: torch.Tensor) -> None |
| maml_opt.learning.model | class | ResponseModel | (input_dim, output_dim, hidden_sizes=(64, 64)) |
| maml_opt.learning.model | class | Standardizer | (mean: tuple, scale: tuple) -> None |
| maml_opt.learning.model | function | adapt_parameters | (model, support_inputs, support_targets, inner_lr, inner_steps, second_order=True) |
| maml_opt.learning.model | function | conditional_pretraining_step | (model, task_batches, optimizer, task_weighting, gradient_clip=None) |
| maml_opt.learning.model | function | episode_to_tensors | (episode, feature_standardizer, target_standardizer, device='cpu', dtype=torch.float32) |
| maml_opt.learning.model | function | evaluate_adaptation | (model, support_inputs, support_targets, query_inputs, query_targets, inner_lr, inner_steps, second_order=False) |
| maml_opt.learning.model | function | fine_tune_model | (model, support_inputs, support_targets, inner_lr, inner_steps) |
| maml_opt.learning.model | function | meta_objective | (model, task_batches, inner_lr, inner_steps, second_order=True) |
| maml_opt.learning.model | function | meta_train_step | (model, task_batches, optimizer, inner_lr, inner_steps, second_order=True, gradient_clip=None) |
| maml_opt.learning.model | function | predict_adapted_responses | (model, query_inputs, adaptation_method, support_inputs=None, support_targets=None, inner_lr=None, inner_steps=None) |
| maml_opt.learning.training | class | DatasetError | None |
| maml_opt.learning.training | class | ResponseModel | (input_dim, output_dim, hidden_sizes=(64, 64)) |
| maml_opt.learning.training | class | TaskDataset | (dataset_id, state, task_split_id, feature_names, design_feature_names, task_context_names, target_names, target_map, task_splits, records, excluded_records, source_runs, manifest_path, records_path) |
| maml_opt.learning.training | class | TrainingError | None |
| maml_opt.learning.training | function | conditional_pretraining_step | (model, task_batches, optimizer, task_weighting, gradient_clip=None) |
| maml_opt.learning.training | function | episode_to_tensors | (episode, feature_standardizer, target_standardizer, device='cpu', dtype=torch.float32) |
| maml_opt.learning.training | function | evaluate_adaptation | (model, support_inputs, support_targets, query_inputs, query_targets, inner_lr, inner_steps, second_order=False) |
| maml_opt.learning.training | function | meta_train_step | (model, task_batches, optimizer, inner_lr, inner_steps, second_order=True, gradient_clip=None) |
| maml_opt.learning.training | function | package_identity | () |
| maml_opt.learning.training | function | train_conditional_pretraining | (dataset, config, output_root, run_id, allow_synthetic_for_tests=False) |
| maml_opt.learning.training | function | train_maml | (dataset, config, output_root, run_id, allow_synthetic_for_tests=False) |
| maml_opt.adapters.rcaide | class | BackendIdentity | (platform: str, version: str, model_fingerprint: str, data_origin: str, cost_unit: str = 'analysis_attempt') -> None |
| maml_opt.adapters.rcaide | class | ConstraintSpec | (name: str, bound: float, sense: str = '<=', scale: float = 1.0, unit: str = '1') -> None |
| maml_opt.adapters.rcaide | class | EvaluationResult | (objective: float / None, constraints_g_le_zero: Mapping, valid: bool = True, status: str = 'VALID', objective_model_eligible: bool = True, responses: Mapping = <factory>, diagnostics: Mapping = <factory>) -> None |
| maml_opt.adapters.rcaide | class | RcaideBackend | (design_space, build_nexus, extract_responses, constraints, model_fingerprint, fidelities, data_origin='SIMULATION', cost_unit='mission_evaluation', input_names=None) |
| maml_opt.adapters.rcaide | function | finite_number | (value, name) |
| maml_opt.data.dataset | class | DatasetError | None |
| maml_opt.data.dataset | class | Episode | (task_id: str, support: tuple, query: tuple, support_design_ids: tuple, query_design_ids: tuple) -> None |
| maml_opt.data.dataset | class | Observation | (observation_id: str, task_id: str, design_id: str, features: tuple, targets: tuple, status: str, analysis_calls: int, source_run_id: str, source_record_id: str, data_origin: str = 'SYNTHETIC_TEST', source_implementation_fingerprint: str = '', source_run_manifest_sha256: str = '', source_evaluation_log_sha256: str = '', source_request_id: str = '', source_attempt_id: str = '', backend_platform: str = '', backend_version: str = '', model_fingerprint: str = '', fidelity: str = '', task_fingerprint: str = '') -> None |
| maml_opt.data.dataset | class | Standardizer | (mean: tuple, scale: tuple) -> None |
| maml_opt.data.dataset | class | TaskDataset | (dataset_id, state, task_split_id, feature_names, design_feature_names, task_context_names, target_names, target_map, task_splits, records, excluded_records, source_runs, manifest_path, records_path) |
| maml_opt.data.archive | class | DatasetError | None |
| maml_opt.data.archive | class | TaskDataset | (dataset_id, state, task_split_id, feature_names, design_feature_names, task_context_names, target_names, target_map, task_splits, records, excluded_records, source_runs, manifest_path, records_path) |
| maml_opt.data.archive | function | atomic_json | (path, value) |
| maml_opt.data.archive | function | audit_archive | (manifest_path) |
| maml_opt.data.archive | function | build_dataset_archive | (history_root, run_ids, output_root, dataset_id, task_split_id, task_splits, task_context_names, task_context_units, target_map, target_units, frozen=False) |
| maml_opt.data.archive | function | fingerprint | (value) |
| maml_opt.data.archive | function | finite_number | (value, name) |
| maml_opt.data.archive | function | json_data | (value) |
| maml_opt.data.archive | function | resolve_target | (response, spec) |
| maml_opt.data.archive | function | write_archive | (output_root, dataset_id, task_split_id, task_splits, design_feature_names, task_context_names, feature_units, target_names, target_units, records, source_runs, frozen=False, target_map=None) |

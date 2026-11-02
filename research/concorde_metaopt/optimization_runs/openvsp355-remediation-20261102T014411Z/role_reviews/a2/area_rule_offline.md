# AREA-RULE-OFFLINE - task-38 (A2, D-12D-003 Round-1)

Status: COMPLETED_OFFLINE / 0 solver starts (no VSPAERO, SU2, RCAIDE, OpenVSP, Gmsh, DOE; only Python/numpy/scipy on archived raw data).
Inputs (read-only): D:/RCAIDE/outputs/concorde_metaopt/p1p3-fullchain-20261031T0407Z/wave_raw/WAVE-00..05; port from research/concorde_metaopt/optimization_runs/p1p3-fullchain-20261031T0407Z/scripts/area_rule_recompute.py (emlord() port of OpenVSP 3.26.1 src/external/wavedragEL/wavedragEL.c).
Method: per-theta slice geometry from Unnamed_WaveDrag_M2.020000_Shown.txt; x = Start + x_norm*Length with Length from results_*.csv (6 dp), not txt Start/End (2 dp): Start/End gives CD rel error 3.6e-5, Length reproduces OpenVSP CDWave to ~1e-6. CDWave = theta-weighted mean(Donq)/Sref with OpenVSP default Sref=100 m^2 (WaveDragMgr.cpp m_Sref.Init(...,100,...)). All Donq below are D/q in m^2, NOT N and NOT CD on aircraft Sref 358.25 m^2.

## 1. Arithmetic reproduction of archived OpenVSP WaveDrag (0 new calls)
| case | geometry | OpenVSP CDWave | port Donq_avg (m^2) | port/100 | rel diff |
|---|---|---|---|---|---|
| WAVE-01 | baseline wing alone | 0.125789 | 12.578880 | 0.12578880 | -1.56e-6 |
| WAVE-02 | baseline wing + fixed fuselage | 0.155025 | 15.502478 | 0.15502478 | -1.40e-6 |
| WAVE-03 | W03=68.0 deg wing alone | 0.116820 | 11.682002 | 0.11682002 | +1.9e-7 |
| WAVE-04 | W03=68.0 deg wing + fuselage | 0.143383 | 14.338322 | 0.14338322 | +1.5e-6 |
| WAVE-05 | baseline wing+fuselage, 72 rot/800 slices | 0.444386 | 44.438679 | 0.44438679 | +1.8e-6 |
=> local Eminton-Lord port is arithmetically faithful to the archived OpenVSP results.

## 2. Sears-Haack analytic benchmark
Formula: Jones Mach-plane area rule / Eminton-Lord; closed form D/q = 128 V^2/(pi L^4) for S(x)=(16V/(3 pi L))[4x(L-x)/L^2]^(3/2).
Exact port convergence: n=81 -1.55e-6; 200 -1.00e-7; 800 -1.55e-9; 1600 -1.93e-10 relative error. Benchmark D/q=0.10185916357881301 (matches archived WAVE-00R analytic value).
White-noise surrogate calibration (n=200, 3 seeds, endpoints pinned; mean rel error vs theory; penalty = integral (S'')^2 dx, resolution-invariant):
| sigma (m^2) | raw EL rel err | lambda_opt | spline rel err | savgol17 rel err |
|---|---|---|---|---|
| 0.002 | 8.7x | 1e-3 | 3.9% | 2.6% |
| 0.005 | 58x | 1e-2 | 6.2% | 12.0% |
| 0.01 | 228x | 1e-2 | 6.3% | 49.4% |
| 0.02 | 810x | 1e-1 | 12.1% | 138% |
| 0.05 | 5245x | 1e-1 | 20.0% | 905% |
| 0.1 | 18380x | 1.0 | 21.2% | 4479% |
Raw EL inversion amplifies slice noise catastrophically. Measured EL matrix condition numbers: n=50 2.8e4; 100 2.3e5; 200 1.9e6; 400 1.5e7; 800 1.2e8.
Calibrated lambda rule fitted here: lambda_opt = c*sigma_hat^b, c=27.84, b=1.606.
Break-bias benchmark: SH + 0.2*Smax gaussian bump (width 0.2 m at x=0.6L), 8000-point reference D/q=0.4655524: raw n=200 error -0.041%; calibrated spline bias -0.29%; savgol17 bias -27.4% => calibrated spline preserves a real geometric break; fixed-window SavGol does not.

## 3. WAVE slice diagnostics (216 theta profiles, 0 negative areas)
| case | n_theta/n_slices | cross-theta volume (m^3) | max endpoint area (m^2) | mean rms S'' | max|dS|/Smax | Donq CV | EL cond | |z|>3.5 | top1/mean |
|---|---|---|---|---|---|---|---|---|---|
| WAVE-01 | 36/200 | 446.72-446.73 | 1.01e-5 | 0.0405 | 0.083 | 0.513 | 1.9e6 | 2 | 261% |
| WAVE-02 | 36/200 | 714.81-714.82 | 5.17e-4 | 0.0658 | 0.115 | 0.588 | 1.9e6 | 2 | 318% |
| WAVE-03 | 36/200 | 446.72-446.73 | 9.43e-6 | 0.0393 | 0.078 | 0.410 | 1.9e6 | 0 | - |
| WAVE-04 | 36/200 | 714.35-714.36 | 5.17e-4 | 0.0634 | 0.093 | 0.409 | 1.9e6 | 0 | - |
| WAVE-05 | 72/800 | 714.81-714.82 | 9.10e-5 | 0.0128 | 0.063 | 2.487 | 1.2e8 | 11 | 1671% |
Cross-theta volume consistent to <0.05 m^3 (slicing closed). WAVE-05 has 11 outlier thetas (73.52 deg Donq=742.48; 78.59 527.55; 136.9 321.25; 68.45 154.74; 55.77 89.29), symmetric theta<->180-theta pairs, present already at 36/200 => geometric slicing artifact (near-tangent slice over fuselage junction), not sampling noise.
Resolution same geometry WAVE-02 (36/200) vs WAVE-05 (72/800), nearest theta: avg Donq ratio 2.87, median 1.08, 4 pairs >2, max 7.72 => NOT converged (fine-grid mean 2.9x coarse-grid mean).
Sensitivity: white noise sigma=0.01 m^2 moves Donq by 0.8% (n=200) to 9.6% (n=800) per realization; sigma=0.1 explodes (1435% at n=800).

## 4. Regularization applied to WAVE
Weighted theta-average D/q (m^2):
| case | raw | calibrated spline | rel change | savgol17 | rel change |
|---|---|---|---|---|---|
| WAVE-01 | 12.579 | 11.814 | -6.1% | 8.702 | -30.8% |
| WAVE-02 | 15.502 | 13.050 | -15.8% | 10.338 | -33.3% |
| WAVE-03 | 11.682 | 11.194 | -4.2% | 8.370 | -28.4% |
| WAVE-04 | 14.338 | 12.605 | -12.1% | 10.076 | -29.7% |
| WAVE-05 | 44.439 | 22.461 | -49.5% | 13.620 | -69.3% |
WAVE-05 shrinks most because raw mean is dominated by 11 outlier thetas; damping those spikes is desirable, but the rule was fitted at n=200 and applied at n=800 (grid-density extrapolation) - indicative only.
Paired increments (wing+body minus wing-alone, same theta/Mach/slice resolution):
| pair | raw mean | raw std | raw SNR | spline mean | spline SNR | savgol mean |
|---|---|---|---|---|---|---|
| baseline (WAVE-02 - WAVE-01) | 2.924 | 3.303 | 0.89 | 1.236 | 0.97 | 1.636 |
| W03+1deg (WAVE-04 - WAVE-03) | 2.656 | 1.569 | 1.69 | 1.410 | 1.44 | 1.706 |
Raw paired SNR <2 (no negative increments); after regularization means drop 30-58% => fuselage increment NOT resolved at either resolution; residual 1.2-1.7 m^2 D/q is same order as noise/regularization bias, so no defensible baseline increment can be claimed.

## 5. Verdict (honest; no tuning to RCAIDE drag)
1. Port arithmetic: VALID (reproduces OpenVSP CDWave ~1e-6; SH exact to 1e-9 at n=800).
2. Raw absolute WAVE Donq: NOT_VALIDATED - ill-conditioned inversion (cond 1.9e6 n=200, 1.2e8 n=800) amplifies slice discretization/geometry noise; white-noise calibration shows 58x-18380x errors at realistic sigma; resolution study not converged (2.87x).
3. Regularization: calibrated spline conditionally usable (break bias -0.29%; white-noise error 4-12% at sigma 0.002-0.02); fixed SavGol unusable (break bias -27%). No independent measured ground truth for WAVE geometry here => still not a validated physical number.
4. Paired wing-alone/wing+body increment: INCONCLUSIVE (SNR<2, no convergence).
5. Therefore WAVE_AREA_RULE stays NOT_VALIDATED; external body correction must NOT be injected; WAVE evidence only qualitative screening at most, with calibration uncertainty.
6. Candidate parameters for a future approved OpenVSP 3.55 WaveDrag round: see area_rule_candidates.json (not executed).

## 6. Files
scripts/wave_diag.py, scripts/wave_diag.json (182 kB), scripts/wave_profiles.json (2.7 MB), area_rule_cases.csv (58 kB), scripts/wave_smooth.py, scripts/wave_smooth.json, scripts/wave_smoothed_per_theta.csv, scripts/extract.py, scripts/_extract.json, run.log.
No repository or GitHub writes; 0 solver starts; numbers traceable to EXT archives with raw_manifest hashes.
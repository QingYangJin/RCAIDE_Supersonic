#!/bin/bash
# Run one isolated-wing SU2 Euler case with 4 MS-MPI ranks, recording the physical
# analysis start/finish in the D-12D-002 approval ledger.
set -u
case_id="$1"
cfg="$2"
log="$3"
EXT_BASE="C:/Users/pc/AppData/Local/RCAIDE_Supersonic_agent_state/fullchain"
LEAD_DIR="$EXT_BASE/lead"
PY="D:/RCAIDE/envs/RCAIDE/python.exe"
SU2="D:/Program Files/SU2/SU2-v8.5.0-win64-mpi/win64-mpi/bin/SU2_CFD.exe"
MPIEXEC="/c/Program Files/Microsoft MPI/Bin/mpiexec"
cd "$(dirname "$cfg")" || exit 9
"$PY" "$LEAD_DIR/ledger.py" start SU2_HF "$case_id" "SU2 8.5.0 Euler isolated 12D main wing ($case_id)" "mpiexec -n 4 SU2_CFD $cfg"
t0=$(date +%s)
timeout 14400 "$MPIEXEC" -n 4 "$SU2" "$cfg" > "$log" 2>&1
rc=$?
t1=$(date +%s)
wall=$((t1 - t0))
status=SOLVED
if [ "$rc" -ne 0 ]; then status=FAILED; fi
"$PY" "$LEAD_DIR/ledger.py" finish "$case_id" "$status" "$wall" "$rc" --note "mpi_ranks=4 log=$(basename "$log")"
echo "WING_RUN_DONE case=$case_id rc=$rc wall_s=$wall status=$status"

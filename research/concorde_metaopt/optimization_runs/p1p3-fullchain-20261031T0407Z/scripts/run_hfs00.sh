#!/bin/bash
set -u
EXT="C:/Users/pc/AppData/Local/RCAIDE_Supersonic_agent_state/fullchain"
W=$EXT/hf/wedge
LEDGER=$EXT/lead/ledger.py
SU2='/d/Program Files/SU2/SU2-v8.5.0-win64-mpi/win64-mpi/bin/SU2_CFD.exe'
PY=D:/RCAIDE/envs/RCAIDE/python.exe
cd $W || exit 1
$PY $LEDGER start SU2_HF HFS-00 '2D supersonic wedge benchmark, Mach 2.0, half angle 10 deg, Euler, theory comparison' '$SU2 hfs00.cfg' || exit 3
T0=$(date +%s)
timeout 1800 "$SU2" hfs00.cfg > su2_hfs00.log 2>&1
RC=$?
T1=$(date +%s)
WALL=$((T1-T0))
ST=SOLVED
[ $RC -ne 0 ] && ST=FAILED
$PY $LEDGER finish HFS-00 $ST $WALL $RC --files 'su2_hfs00.log:0;surface_flow_hfs00.csv:0;restart_hfs00.csv:0;history_hfs00.csv:0' --note 'SU2 8.5.0 Euler 2D wedge; MARKER_EULER wall + MARKER_FAR farfield; MUSCL/Venkatarishnan; residual criterion RMS_DENSITY -8' 
echo EXIT=$RC WALL=$WALL STATUS=$ST
tail -25 su2_hfs00.log
ls -la surface_flow_hfs00.csv restart_hfs00.csv history_hfs00.csv 2>/dev/null

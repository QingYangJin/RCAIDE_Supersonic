#!/usr/bin/env bash
cd C:/Users/pc/AppData/Local/RCAIDE_Supersonic_agent_state/fullchain/lead
for c in WAVE-02 WAVE-03 WAVE-04; do
  D:/RCAIDE/envs/RCAIDE/python.exe -E -s -B run_wave.py $c > $(echo $c | tr 'A-Z' 'a-z')_run.log 2>&1
  echo "$c exit=$?"
  tail -2 $(echo $c | tr 'A-Z' 'a-z')_run.log
done
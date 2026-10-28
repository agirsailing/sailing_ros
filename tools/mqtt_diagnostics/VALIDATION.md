# Local validation — 2026-10-15

Environment: Windows PC, Docker Desktop, local Eclipse Mosquitto 2, Paho 2.1.0.
No Raspberry or EMQX credentials were used for these runs.

- Six-minute MQTT 3.1.1 run: no unexpected disconnects on publisher, native
  observer or WebSocket observer. The initial Windows scheduler delivered
  dashboard at 16 Hz despite a 20 Hz target; the report exposed this discrepancy.
- Corrected scheduling to preserve deadlines without catch-up bursts, and used
  the high-resolution monotonic performance counter on Windows.
- Final-clock 20-second run: 400 dashboard messages per observer, 20 Hz received,
  map 5 Hz, state 1 Hz, no unexpected disconnects. Dashboard median latency was
  about 4.5 ms and p95 about 6 ms. This short run does not certify long-term
  stability at 20 Hz; run the documented 15-minute test on the target network.
- Bash launcher and MQTT 5 smoke test passed against the local broker.
- Forced broker restart: all three peers recorded unexpected disconnection,
  MQTT 3.1.1 reason 128 (Unspecified error), then reconnected. This demonstrates
  why a generic client reason cannot by itself identify a broker quota violation.
- Four offline tests passed: payload/rounding, latency/disconnect report analysis,
  unsuccessful empty runs, and separate subscriber credentials.

Reports remain under the ignored `runs/` directory on the development PC.
Cloud behavior and browser behavior remain to be measured with this tool.

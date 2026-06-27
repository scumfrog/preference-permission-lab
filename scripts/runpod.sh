#!/usr/bin/env bash
# Phase 3c — one-command GPU run for RunPod / Vast.ai, with GUARANTEED pod kill.
#
# Flow: install -> tiny-model smoke (validate plumbing) -> gate check ->
#       real collect (behavior + activations) -> [optional Step 0] ->
#       persist artifacts (runpodctl send, blocking) -> TERMINATE the pod.
#
# The pod is terminated on EXIT via a trap, so it dies even if a step fails —
# never left idle. Artifacts are written to a persistent dir AND pushed off-pod
# (runpodctl send) before the normal exit, so termination does not lose data.
#
# Usage (on the pod):
#   bash scripts/runpod.sh                         # defaults: Qwen2.5-7B, smoke first, terminate
#   MODEL=Qwen/Qwen2.5-7B-Instruct DO_STEP0=1 bash scripts/runpod.sh
#   KEEP=1 bash scripts/runpod.sh                  # debug: do NOT terminate
#
set -euo pipefail

MODEL="${MODEL:-Qwen/Qwen2.5-7B-Instruct}"
SMOKE_MODEL="${SMOKE_MODEL:-Qwen/Qwen2.5-0.5B-Instruct}"
LAYERS="${LAYERS:-all}"
REPS="${REPS:-3}"
TEMPERATURE="${TEMPERATURE:-0.3}"
RUN_SMOKE="${RUN_SMOKE:-1}"
DO_STEP0="${DO_STEP0:-0}"
TERMINATE="${TERMINATE:-1}"     # default ON; set KEEP=1 to override
KEEP="${KEEP:-0}"
# Persist to a network volume if present (survives pod termination), else repo dir.
if [ -d /workspace ] && [ -w /workspace ]; then OUT_DIR="${OUT_DIR:-/workspace/reports}"; else OUT_DIR="${OUT_DIR:-reports}"; fi
PY="${PY:-.venv/bin/python}"

mkdir -p "$OUT_DIR"

terminate_pod() {
  local code=$?
  if [ "$KEEP" = "1" ] || [ "$TERMINATE" != "1" ]; then
    echo "[runpod] KEEP/!TERMINATE set — NOT terminating. REMEMBER to kill the pod manually."
    return 0
  fi
  echo "[runpod] terminating pod (exit code $code) — no idle billing."
  if command -v runpodctl >/dev/null 2>&1 && [ -n "${RUNPOD_POD_ID:-}" ]; then
    runpodctl remove pod "$RUNPOD_POD_ID" || echo "[runpod] runpodctl remove failed; KILL MANUALLY."
  elif command -v vastai >/dev/null 2>&1 && [ -n "${VAST_CONTAINERLABEL:-}${CONTAINER_ID:-}" ]; then
    vastai destroy instance "${CONTAINER_ID:-$VAST_CONTAINERLABEL}" || echo "[runpod] vast destroy failed; KILL MANUALLY."
  else
    echo "[runpod] No runpodctl/vastai or pod id env. Falling back to shutdown."
    shutdown -h now 2>/dev/null || poweroff 2>/dev/null || \
      echo "[runpod] *** COULD NOT SELF-TERMINATE — KILL THE POD MANUALLY NOW. ***"
  fi
}
# Guarantee termination on ANY exit (success, error, or signal) unless KEEP=1.
trap terminate_pod EXIT

echo "[runpod] env: MODEL=$MODEL  LAYERS=$LAYERS  OUT_DIR=$OUT_DIR  TERMINATE=$TERMINATE KEEP=$KEEP"

# 1) deps (idempotent)
if [ ! -x "$PY" ]; then python -m venv .venv; fi
$PY -m pip -q install -e '.[mech]'

# 2) tiny-model smoke (cents) — validate the whole pipeline before paying for the big model
if [ "$RUN_SMOKE" = "1" ]; then
  echo "[runpod] SMOKE on $SMOKE_MODEL ..."
  $PY scripts/phase3c_collect.py --model "$SMOKE_MODEL" --layers 0,4,8 \
    --reps 1 --temperature "$TEMPERATURE" \
    --out-activations "$OUT_DIR/p3c_act_smoke.json" --out-behavior "$OUT_DIR/p3c_beh_smoke.json"
  # gate: the analysis must run end-to-end on the smoke artifacts
  $PY scripts/phase3c_analyze.py --activations "$OUT_DIR/p3c_act_smoke.json" \
    --out "$OUT_DIR/p3c_analysis_smoke.json" --directions-out "$OUT_DIR/p3c_dir_smoke.json" >/dev/null
  echo "[runpod] smoke OK (plumbing validated)."
fi

# 3) real collect (behavior + activations, ONE model load)
echo "[runpod] COLLECT on $MODEL ..."
$PY scripts/phase3c_collect.py --model "$MODEL" --layers "$LAYERS" \
  --reps "$REPS" --temperature "$TEMPERATURE" \
  --out-activations "$OUT_DIR/p3c_act.json" --out-behavior "$OUT_DIR/p3c_beh.json"

# 4) optional Step 0 full behavioral on the confirmatory set (same harness)
if [ "$DO_STEP0" = "1" ]; then
  echo "[runpod] STEP 0 behavioral on $MODEL ..."
  $PY -m pplab.runner agentic --client open --model "$MODEL" \
    --scenario-set confirmatory --reps 5 --temperature "$TEMPERATURE" \
    --output "$OUT_DIR/p3c_step0.json"
fi

echo "[runpod] artifacts in $OUT_DIR:"; ls -la "$OUT_DIR"/p3c_*.json || true

# 5) persist OFF-POD before termination. runpodctl send BLOCKS until you run
#    `runpodctl receive <code>` locally — so data is transferred before kill.
if command -v runpodctl >/dev/null 2>&1; then
  echo "[runpod] ===> Run 'runpodctl receive <CODE>' locally to pull these files, then this script terminates the pod:"
  runpodctl send "$OUT_DIR"/p3c_act.json "$OUT_DIR"/p3c_beh.json \
    $([ "$DO_STEP0" = "1" ] && echo "$OUT_DIR/p3c_step0.json") || \
    echo "[runpod] runpodctl send failed — artifacts remain in $OUT_DIR (persistent if it's a network volume)."
else
  echo "[runpod] runpodctl not found. Artifacts in $OUT_DIR (persistent only if a network volume is mounted). scp them NOW before exit."
fi

echo "[runpod] done. Pod will terminate on exit (KEEP=$KEEP)."
# trap fires here -> terminate_pod

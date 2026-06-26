"""Typer CLI: list-scenarios, run, report."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from . import analysis, evaluator, report
from .ablation import all_variants
from .benchmarks import (
    BenchmarkPresetError,
    estimate_cost,
    get_preset,
    list_presets,
    load_costs,
)
from .experiment import (
    completed_keys_from_runs,
    estimate_grid,
    experiment_summary,
    experiment_summary_from_runs,
    new_experiment_id,
    run_benchmark,
    run_experiment,
)
from .llm_clients import VALID_BEHAVIORS, build_client
from .policies import PolicyProfileError, parse_policy_profiles
from .scenarios import (
    PROJECT_ROOT,
    ScenarioLoadError,
    filter_scenarios,
    load_all,
)
from .trace import TraceLoadError, load_trace

app = typer.Typer(
    add_completion=False,
    help="Preference-to-Permission Confusion research lab.",
    no_args_is_help=True,
)
console = Console()

REPORTS_DIR = PROJECT_ROOT / "reports"


@app.command("list-scenarios")
def list_scenarios(
    domain: Optional[str] = typer.Option(None, help="Filter by domain."),
) -> None:
    """List all loaded scenarios."""
    try:
        cases = load_all()
    except ScenarioLoadError as exc:
        console.print(f"[red]Scenario load error:[/red] {exc}")
        raise typer.Exit(code=1)

    cases = filter_scenarios(cases, domain=domain)
    table = Table(title="Scenarios")
    table.add_column("ID")
    table.add_column("Domain")
    table.add_column("Title")
    table.add_column("Approval?")
    table.add_column("Expected Max Impact")
    for c in cases:
        table.add_row(
            c.id,
            c.domain,
            c.title,
            "yes" if c.explicit_current_approval else "no",
            c.expected_max_impact_without_violation.name,
        )
    console.print(table)
    console.print(f"[dim]{len(cases)} scenario(s).[/dim]")


def _load_cases(domain, scenario):
    try:
        cases = load_all()
    except ScenarioLoadError as exc:
        console.print(f"[red]Scenario load error:[/red] {exc}")
        raise typer.Exit(code=1)
    cases = filter_scenarios(cases, domain=domain, scenario_id=scenario)
    if not cases:
        console.print("[yellow]No scenarios matched the filters.[/yellow]")
        raise typer.Exit(code=1)
    return cases


def _build_client_or_exit(client, behavior, model, temperature):
    try:
        return build_client(client, behavior=behavior, model=model, temperature=temperature)
    except ValueError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1)


def _parse_policies_or_exit(policy):
    try:
        return parse_policy_profiles(policy)
    except PolicyProfileError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1)


def _execute_and_report(
    cases,
    *,
    client,
    behavior,
    model,
    temperature,
    policy_profiles,
    runs,
    memory_variants,
    mode,
    output,
    default_name,
    trace=False,
):
    agent_client = _build_client_or_exit(client, behavior, model, temperature)
    experiment_id = new_experiment_id()
    behavior_label = behavior if client in ("agent", "mock") else None

    try:
        records, rep_results, rep_traces = run_experiment(
            cases,
            agent_client,
            runs=runs,
            policy_profiles=policy_profiles,
            memory_variants=memory_variants,
            experiment_id=experiment_id,
            client_type=client,
            model=model,
            behavior=behavior_label,
            temperature=temperature,
        )
    except RuntimeError as exc:  # e.g. missing API key for a real client
        console.print(f"[red]Run error:[/red] {exc}")
        raise typer.Exit(code=1)

    agg = evaluator.aggregate(rep_results)
    exp = experiment_summary(records)
    generated_at = datetime.now(timezone.utc).isoformat()

    payload = report.build_experiment_payload(
        rep_results,
        rep_traces,
        records,
        exp,
        agg,
        experiment_id=experiment_id,
        client=agent_client.name,
        model=model,
        behavior=behavior_label,
        temperature=temperature,
        policy_profiles=policy_profiles,
        mode=mode,
        generated_at=generated_at,
    )

    json_path = Path(output) if output else REPORTS_DIR / default_name
    report.write_json(payload, json_path)
    md_path = json_path.with_suffix(".md")
    report.write_markdown(payload, md_path)

    report.render_terminal(payload, console)
    if trace:
        for sid in rep_traces:
            report.render_trace(rep_traces[sid], console)

    console.print(
        f"[dim]experiment_id={experiment_id}  runs={len(records)}  mode={mode}[/dim]"
    )
    console.print(f"[green]Wrote[/green] {json_path}")
    console.print(f"[green]Wrote[/green] {md_path}")


@app.command("run")
def run(
    client: str = typer.Option("agent", help="agent | mock | openai | anthropic"),
    behavior: str = typer.Option("borderline", help=f"For agent/mock client: {', '.join(VALID_BEHAVIORS)}"),
    model: Optional[str] = typer.Option(None, help="Model name for openai/anthropic."),
    temperature: Optional[float] = typer.Option(None, help="Sampling temperature (real LLM clients)."),
    policy: str = typer.Option("baseline", help="Policy profile(s), comma-separated for a sweep."),
    runs: int = typer.Option(1, help="Number of repeated runs per scenario."),
    domain: Optional[str] = typer.Option(None, help="Filter by domain."),
    scenario: Optional[str] = typer.Option(None, help="Run a single scenario id."),
    output: Optional[str] = typer.Option(None, help="JSON output path (default reports/latest.json)."),
    trace: bool = typer.Option(False, "--trace", help="Print a per-scenario decision trace to the terminal."),
) -> None:
    """Run scenarios (optionally repeated / multi-policy) and produce a report."""
    if runs < 1:
        console.print("[red]--runs must be >= 1.[/red]")
        raise typer.Exit(code=1)
    cases = _load_cases(domain, scenario)
    policy_profiles = _parse_policies_or_exit(policy)
    _execute_and_report(
        cases,
        client=client,
        behavior=behavior,
        model=model,
        temperature=temperature,
        policy_profiles=policy_profiles,
        runs=runs,
        memory_variants=["original_memory"],
        mode="standard",
        output=output,
        default_name="latest.json",
        trace=trace,
    )


@app.command("run-ablation")
def run_ablation(
    client: str = typer.Option("agent", help="agent | mock | openai | anthropic"),
    behavior: str = typer.Option("borderline", help=f"For agent/mock client: {', '.join(VALID_BEHAVIORS)}"),
    model: Optional[str] = typer.Option(None, help="Model name for openai/anthropic."),
    temperature: Optional[float] = typer.Option(None, help="Sampling temperature (real LLM clients)."),
    policy: str = typer.Option("baseline", help="Policy profile(s), comma-separated."),
    runs: int = typer.Option(1, help="Number of repeated runs per memory variant."),
    domain: Optional[str] = typer.Option(None, help="Filter by domain."),
    scenario: Optional[str] = typer.Option(None, help="Single scenario id."),
    output: Optional[str] = typer.Option(None, help="JSON output path (default reports/ablation.json)."),
) -> None:
    """Run each scenario across all memory variants (ablation experiment)."""
    if runs < 1:
        console.print("[red]--runs must be >= 1.[/red]")
        raise typer.Exit(code=1)
    cases = _load_cases(domain, scenario)
    policy_profiles = _parse_policies_or_exit(policy)
    _execute_and_report(
        cases,
        client=client,
        behavior=behavior,
        model=model,
        temperature=temperature,
        policy_profiles=policy_profiles,
        runs=runs,
        memory_variants=all_variants(),
        mode="ablation",
        output=output,
        default_name="ablation.json",
        trace=False,
    )


@app.command("benchmark")
def benchmark(
    preset: str = typer.Option(..., help=f"Preset: {', '.join(list_presets())}"),
    client: str = typer.Option("openai", help="agent | mock | openai | anthropic"),
    model: Optional[str] = typer.Option(None, help="Model name for real clients."),
    behavior: str = typer.Option("borderline", help="Behavior for agent/mock client."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Print the plan only; make NO model calls."),
    resume: Optional[str] = typer.Option(None, help="Resume from an existing report JSON."),
    sleep_between_calls: float = typer.Option(0.0, help="Seconds to sleep after each model call."),
    max_errors: int = typer.Option(10, help="Stop gracefully after this many model/API errors."),
    output: Optional[str] = typer.Option(None, help="JSON output path (default reports/<experiment_id>.json)."),
    costs: Optional[str] = typer.Option(None, help="Pricing YAML (default benchmark_costs.yaml)."),
) -> None:
    """Expand a benchmark preset into an experiment grid and run it safely."""
    try:
        p = get_preset(preset)
    except BenchmarkPresetError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1)

    try:
        all_cases = load_all()
    except ScenarioLoadError as exc:
        console.print(f"[red]Scenario load error:[/red] {exc}")
        raise typer.Exit(code=1)

    cases = [c for c in all_cases if c.domain in p.domains]
    if p.scenarios:
        wanted = set(p.scenarios)
        cases = [c for c in cases if c.id in wanted]
    if not cases:
        console.print("[yellow]Preset matched no scenarios.[/yellow]")
        raise typer.Exit(code=1)

    runs, temps = p.runs, p.temperatures
    policies, variants = p.policy_profiles, p.memory_variants
    expected_calls = len(cases) * runs * len(temps) * len(policies) * len(variants)

    # Estimate tokens by building prompts only (no model calls).
    prompt_client = _build_client_or_exit(
        client, behavior, model, temps[0] if temps else None
    )
    est = estimate_grid(
        cases,
        prompt_client,
        runs=runs,
        temperatures=temps,
        policy_profiles=policies,
        memory_variants=variants,
    )
    costs_map = load_costs(Path(costs) if costs else None)
    est_cost = estimate_cost(
        model, est["estimated_input_tokens"], est["estimated_output_tokens"], costs_map
    )

    # --- Print the execution plan (always, including dry-run). ---
    console.print(f"[bold]Preset:[/bold] {preset}")
    console.print(f"Domains: {','.join(p.domains)}")
    console.print(f"Scenarios: {len(cases)}")
    console.print(f"Runs: {runs}")
    console.print(f"Temperatures: {len(temps)} {temps}")
    console.print(f"Policy profiles: {len(policies)} {policies}")
    console.print(f"Memory variants: {len(variants)} {variants}")
    console.print(f"[bold]Expected model calls:[/bold] {expected_calls}")
    console.print(f"Estimated input tokens (est.): {est['estimated_input_tokens']:,}")
    console.print(f"Estimated output tokens (est.): {est['estimated_output_tokens']:,}")
    if est_cost is not None:
        console.print(f"Estimated cost (est., USD): ${est_cost}")
    else:
        console.print("Estimated cost: [yellow]cost unavailable[/yellow] (no pricing config for this model)")

    # --- Resume vs fresh. ---
    prior_payload = None
    existing_runs: list[dict] = []
    completed: set = set()
    if resume:
        rpath = Path(resume)
        if not rpath.is_absolute():
            rpath = PROJECT_ROOT / resume
        if not rpath.exists():
            console.print(f"[red]Resume file not found:[/red] {rpath}")
            raise typer.Exit(code=1)
        prior_payload = report.load_payload(rpath)
        experiment_id = prior_payload.get("experiment_id") or new_experiment_id()
        existing_runs = prior_payload.get("runs", [])
        completed = completed_keys_from_runs(existing_runs)
        console.print(
            f"[cyan]Resuming {experiment_id}: {len(existing_runs)} completed runs, "
            f"{expected_calls - len(completed)} remaining.[/cyan]"
        )
    else:
        experiment_id = new_experiment_id()

    created_at = datetime.now(timezone.utc).isoformat()
    manifest = report.build_manifest(
        experiment_id=experiment_id,
        created_at=created_at,
        preset=preset,
        client=client,
        model=model,
        domains=p.domains,
        scenario_ids=[c.id for c in cases],
        runs=runs,
        temperatures=temps,
        policy_profiles=policies,
        memory_variants=variants,
        expected_calls=expected_calls,
        estimated_input_tokens=est["estimated_input_tokens"],
        estimated_output_tokens=est["estimated_output_tokens"],
        estimated_cost=est_cost,
    )
    manifest_path = REPORTS_DIR / f"{experiment_id}_manifest.json"
    report.write_manifest(manifest, manifest_path)
    console.print(f"[green]Wrote manifest[/green] {manifest_path}")

    if dry_run:
        console.print("[yellow]Dry run — no model calls were made.[/yellow]")
        return

    behavior_label = behavior if client in ("agent", "mock") else None

    def client_factory(temp):
        return build_client(client, behavior=behavior, model=model, temperature=temp)

    outcome = run_benchmark(
        cases,
        client_factory=client_factory,
        runs=runs,
        temperatures=temps,
        policy_profiles=policies,
        memory_variants=variants,
        experiment_id=experiment_id,
        client_type=client,
        model=model,
        behavior=behavior_label,
        preset=preset,
        completed_keys=completed,
        sleep_between_calls=sleep_between_calls,
        max_errors=max_errors,
    )

    new_dicts = [r.model_dump() for r in outcome.records]
    all_run_dicts = existing_runs + new_dicts
    exp = experiment_summary_from_runs(all_run_dicts)
    generated_at = datetime.now(timezone.utc).isoformat()

    if prior_payload is not None:
        # Keep the original representative report sections; refresh runs + experiment.
        payload = prior_payload
        payload["runs"] = all_run_dicts
        payload["experiment"] = exp
        payload["generated_at"] = generated_at
    else:
        # aggregate([]) returns a complete zero-filled dict, so this is safe even
        # when every cell errored (no representative results captured).
        agg = evaluator.aggregate(outcome.rep_results)
        payload = report.build_experiment_payload(
            outcome.rep_results,
            outcome.rep_traces,
            outcome.records,
            exp,
            agg,
            experiment_id=experiment_id,
            client=prompt_client.name,
            model=model,
            behavior=behavior_label,
            temperature=None,
            policy_profiles=policies,
            mode="benchmark",
            generated_at=generated_at,
            preset=preset,
        )

    json_path = Path(output) if output else REPORTS_DIR / f"{experiment_id}.json"
    report.write_json(payload, json_path)
    md_path = json_path.with_suffix(".md")
    report.write_markdown(payload, md_path)

    if outcome.errors:
        console.print(
            f"[yellow]{outcome.errors} model error(s) recorded as run records "
            f"(model_error/invalid_output).[/yellow]"
        )
    if outcome.stopped:
        console.print(
            f"[red]Stopped early: error budget ({max_errors}) reached. "
            f"Partial results saved.[/red]"
        )
    console.print(
        f"[dim]experiment_id={experiment_id}  new_runs={len(new_dicts)}  "
        f"total_runs={len(all_run_dicts)}[/dim]"
    )
    console.print(f"[green]Wrote[/green] {json_path}")
    console.print(f"[green]Wrote[/green] {md_path}")
    console.print(
        f"[dim]Next: pplab analyze --input {json_path}  |  "
        f"pplab export-csv --input {json_path} --output {json_path.with_suffix('.csv')}[/dim]"
    )


@app.command("analyze")
def analyze_cmd(
    input: str = typer.Option(..., "--input", help="Benchmark report JSON to analyze."),
) -> None:
    """Print and write a causal analysis of a benchmark report."""
    path = Path(input)
    if not path.is_absolute():
        path = PROJECT_ROOT / input
    if not path.exists():
        console.print(f"[red]Report file not found:[/red] {path}")
        raise typer.Exit(code=1)
    payload = report.load_payload(path)
    result = analysis.build_analysis(payload)
    analysis.render_analysis_terminal(result, console)

    eid = result.get("experiment_id") or path.stem
    md = analysis.render_analysis_markdown(result, payload)
    md_path = REPORTS_DIR / f"{eid}_analysis.md"
    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text(md, encoding="utf-8")
    console.print(f"[green]Wrote[/green] {md_path}")


@app.command("agentic")
def agentic_cmd(
    client: str = typer.Option("mock", help="mock | openai | anthropic"),
    behavior: str = typer.Option("violator", help="For mock: safe|drift|violator|retrier|deceptive"),
    model: Optional[str] = typer.Option(None, help="Model for real tool-calling clients."),
    temperature: Optional[float] = typer.Option(None, help="Sampling temperature."),
    reps: int = typer.Option(20, help="Repetitions per arm (justify with power; see PHASE_3A_DESIGN)."),
    seed: int = typer.Option(12345, help="RNG seed for episode order + bootstrap."),
    sleep_between_episodes: float = typer.Option(0.0, help="Seconds to sleep between episodes."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Print the plan; no model calls."),
    output: Optional[str] = typer.Option(None, help="JSON output (default reports/agentic_<client>.json)."),
) -> None:
    """Phase 3a: real tool-calling against the immutable capability gateway."""
    import json as _json

    from .agentic import (
        aggregate_by_arm,
        build_agentic_driver,
        build_phase3a_scenarios,
        run_agentic_experiment,
        style_channel_contrasts,
    )

    scenarios = build_phase3a_scenarios()
    n_arms, episodes = len(scenarios), len(scenarios) * reps
    console.print(f"[bold]Phase 3a — agentic gateway probe[/bold]")
    console.print(f"Client: {client}  Arms: {n_arms} (4 unauthorized 2x2 + 2 controls)  Reps: {reps}")
    console.print(f"Episodes: {episodes}  (each episode = a multi-step tool-calling conversation)")
    console.print(f"Approx max model calls: {episodes} x up-to-6 steps = ~{episodes*6}")
    if dry_run:
        console.print("[yellow]Dry run — no model calls made.[/yellow]")
        return

    try:
        outcomes = run_agentic_experiment(
            lambda: build_agentic_driver(client, behavior=behavior, model=model, temperature=temperature),
            scenarios, reps=reps, seed=seed, sleep_between_episodes=sleep_between_episodes,
        )
    except (RuntimeError, ValueError) as exc:
        console.print(f"[red]Agentic run error:[/red] {exc}")
        raise typer.Exit(code=1)

    arms = aggregate_by_arm(outcomes, seed=seed)
    contrasts = style_channel_contrasts(outcomes, seed=seed)

    table = Table(title="Per-arm primary endpoint (95% bootstrap CI)")
    table.add_column("Arm")
    table.add_column("Condition")
    table.add_column("Metric")
    table.add_column("Rate [CI]", justify="right")
    table.add_column("EnfFail", justify="right")
    for arm, s in arms.items():
        table.add_row(arm, s["condition"], s["primary_metric"],
                      f"{s['mean']:.2f} [{s['lo']:.2f},{s['hi']:.2f}]", str(s["enforcement_failures"]))
    console.print(table)
    console.print("[bold]2x2 contrasts (violation-attempt rate, 95% bootstrap CI):[/bold]")
    for k, v in contrasts.items():
        if k == "total_enforcement_failures":
            continue
        flag = " [red]CI excludes 0[/red]" if v.get("excludes_zero") else ""
        console.print(f"  {k}: {v['estimate']:+.3f} [{v['lo']:+.3f},{v['hi']:+.3f}]{flag}")
    if contrasts["total_enforcement_failures"] == 0:
        console.print("[green]Gateway audit OK: 0 authorization-enforcement failures.[/green]")
    else:
        console.print("[red]GATEWAY AUDIT FAILED — sensitive action allowed without capability![/red]")

    payload = {
        "phase": "3a",
        "client": client,
        "model": model,
        "temperature": temperature,
        "reps": reps,
        "seed": seed,
        "arms": arms,
        "contrasts": contrasts,
        "episodes": [o.__dict__ for o in outcomes],
    }
    out_path = Path(output) if output else REPORTS_DIR / f"agentic_{client}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(_json.dumps(payload, indent=2), encoding="utf-8")
    console.print(f"[green]Wrote[/green] {out_path}")


@app.command("export-csv")
def export_csv_cmd(
    input: str = typer.Option("reports/latest.json", "--input", help="Run JSON to export."),
    output: str = typer.Option("reports/latest.csv", "--output", help="CSV output path."),
) -> None:
    """Export one CSV row per scenario run for downstream analysis."""
    in_path = Path(input)
    if not in_path.is_absolute():
        in_path = PROJECT_ROOT / input
    if not in_path.exists():
        console.print(f"[red]Report file not found:[/red] {in_path}")
        raise typer.Exit(code=1)
    payload = report.load_payload(in_path)
    out_path = Path(output)
    if not out_path.is_absolute():
        out_path = PROJECT_ROOT / output
    n = report.export_csv(payload, out_path)
    console.print(f"[green]Wrote[/green] {out_path} ({n} run rows)")


@app.command("report")
def report_cmd(
    input: str = typer.Option("reports/latest.json", "--input", help="Path to a run JSON file."),
) -> None:
    """Render a previously-saved run report to the terminal."""
    path = Path(input)
    if not path.is_absolute():
        path = PROJECT_ROOT / input
    if not path.exists():
        console.print(f"[red]Report file not found:[/red] {path}")
        raise typer.Exit(code=1)
    payload = report.load_payload(path)
    report.render_terminal(payload, console)


@app.command("inspect")
def inspect(
    input: str = typer.Option(..., "--input", help="Path to a run JSON file."),
    scenario: str = typer.Option(..., "--scenario", help="Scenario id to inspect."),
) -> None:
    """Print a readable decision trace for one scenario from a saved run."""
    path = Path(input)
    if not path.is_absolute():
        path = PROJECT_ROOT / input
    if not path.exists():
        console.print(f"[red]Report file not found:[/red] {path}")
        raise typer.Exit(code=1)

    payload = report.load_payload(path)
    traces = payload.get("decision_traces", {})
    if scenario not in traces:
        available = ", ".join(sorted(traces)) or "(none)"
        console.print(
            f"[red]No decision trace for scenario '{scenario}'.[/red]\n"
            f"Available: {available}"
        )
        raise typer.Exit(code=1)

    # Fail closed: a malformed trace must not render as if it were valid.
    try:
        trace = load_trace(traces[scenario])
    except TraceLoadError as exc:
        console.print(f"[red]Malformed decision trace:[/red] {exc}")
        raise typer.Exit(code=1)

    report.render_trace(trace, console)


if __name__ == "__main__":
    app()

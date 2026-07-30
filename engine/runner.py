import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
import pandas as pd
from .scenario import Scenario
from .model import SchoolModel


def run_one(scenario: Scenario, steps: int, seed: int = 42) -> dict:
    model = SchoolModel(scenario, seed=seed)
    for _ in range(steps):
        model.step()

    df = model.collector.to_df()
    last = df.iloc[-1]

    total_pupils = len(model.pupils)
    total_teachers = len(model.teachers)
    total_staff = len(model.staff)

    ever_infected_pupils = int(total_pupils - last["S_pupils"])
    ever_infected_teachers = int(total_teachers - last["S_teachers"])
    ever_infected_staff = int(total_staff - last["S_staff"])

    missed_days_total = (
        sum(a.missed_school_days for a in model.pupils)
        + sum(a.missed_school_days for a in model.teachers)
        + sum(a.missed_school_days for a in model.staff)
    )

    return {
        "meta": {
            "scenario": asdict(scenario),
            "seed": seed,
            "steps": steps,
            "created_at": datetime.now().isoformat(timespec="seconds"),
        },
        "summary": {
            "ever_infected_pupils": ever_infected_pupils,
            "ever_infected_teachers": ever_infected_teachers,
            "ever_infected_staff": ever_infected_staff,
            "ever_infected_total": int(ever_infected_pupils + ever_infected_teachers + ever_infected_staff),
            "missed_school_days_total": float(missed_days_total),
        },
        "timeseries": df.to_dict(orient="list"),
    }


def run_monte_carlo(
    scenario: Scenario,
    steps: int,
    n_runs: int = 100,
    out_dir: str = "results",
    base_seed: int = 1234,
) -> Path:
    out_path = Path(out_dir) / scenario.name / datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path.mkdir(parents=True, exist_ok=True)

    summaries = []
    for i in range(n_runs):
        seed = base_seed + i
        res = run_one(scenario, steps=steps, seed=seed)
        summaries.append(res["summary"])

        with open(out_path / f"run_{i:03d}.json", "w", encoding="utf-8") as f:
            json.dump(res, f, indent=2)

    pd.DataFrame(summaries).to_csv(out_path / "summaries.csv", index=False)

    with open(out_path / "scenario.json", "w", encoding="utf-8") as f:
        json.dump(asdict(scenario), f, indent=2)

    return out_path


# ---------- GUI helpers ----------
def list_result_groups(out_dir: str = "results") -> list[Path]:
    base = Path(out_dir)
    if not base.exists():
        return []
    return sorted([p for p in base.iterdir() if p.is_dir()])


def list_runs_for_group(group_dir: Path) -> list[Path]:
    """
    group_dir = results/<scenario_name>/
    returns timestamp folders inside it.
    """
    if not group_dir.exists():
        return []
    return sorted([p for p in group_dir.iterdir() if p.is_dir()], reverse=True)


def load_summaries(run_dir: Path) -> pd.DataFrame:
    p = run_dir / "summaries.csv"
    return pd.read_csv(p)


def load_scenario(run_dir: Path) -> dict:
    p = run_dir / "scenario.json"
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)
    
    
def save_single_run(scenario: Scenario,steps: int, out_dir: str = "results",seed: int = 42,) -> Path:
    """
    Runs ONE simulation and saves it to:
    results/<scenario_name>/<timestamp>/run_000.json + scenario.json + summaries.csv
    Returns the run directory path.
    """
    out_path = Path(out_dir) / scenario.name / datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path.mkdir(parents=True, exist_ok=True)

    res = run_one(scenario, steps=steps, seed=seed)

    # save run file
    with open(out_path / "run_000.json", "w", encoding="utf-8") as f:
        json.dump(res, f, indent=2)

    # save scenario
    with open(out_path / "scenario.json", "w", encoding="utf-8") as f:
        json.dump(asdict(scenario), f, indent=2)

    # save summaries.csv with a single row
    pd.DataFrame([res["summary"]]).to_csv(out_path / "summaries.csv", index=False)

    return out_path


def load_run_json(run_json_path: Path) -> dict:
    with open(run_json_path, "r", encoding="utf-8") as f:
        return json.load(f)


"""Exact optimisation models for the (stochastic) IHTC."""

import json
from pathlib import Path

import gurobipy as gp
from gurobipy import GRB


def load_instances(data_dir="./data"):
    """Read every instance JSON in `data_dir`, keyed by file stem (e.g. 'small01')."""
    paths = sorted(Path(data_dir).glob("*.json"))
    if not paths:
        raise FileNotFoundError(f"No .json instances found in {Path(data_dir).resolve()}")
    return {p.stem: json.loads(p.read_text()) for p in paths}


def build_model(name, instance):
    """Build the Gurobi model for one instance.

    Variables (stored on the model for use when extracting the solution):
        admission[p, d]: 1 if patient p is admitted on day d
        room[p, r]:      1 if patient p is admitted to room r
        ot[p, t]:        1 if patient p is admitted to operating theatre t

    TODO: constraints and objective are yet to be specified.
    """
    patients = [p["id"] for p in instance["patients"]]
    days = range(instance["days"])
    rooms = [r["id"] for r in instance["rooms"]]
    theaters = [t["id"] for t in instance["operating_theaters"]]

    # Variables
    model = gp.Model(name)
    model._admission = model.addVars(patients, days, vtype=GRB.BINARY, name="admission")
    model._room = model.addVars(patients, rooms, vtype=GRB.BINARY, name="room")
    model._ot = model.addVars(patients, theaters, vtype=GRB.BINARY, name="ot")

    # Hard constraints


    # Soft constraints

    

    return model


def _chosen(variables, patient):
    """Indices k with variables[patient, k] at 1 in the current solution."""
    return [k for (p, k), var in variables.items() if p == patient and var.X > 0.5]


def extract_patients(model, instance):
    """Build the "patients" part of the solution JSON from admission, room and ot.

    Checks that each patient is either admitted on exactly one day with exactly
    one room and one OT, or not admitted at all with no room and no OT.
    """
    patients = []
    errors = []
    for patient in instance["patients"]:
        pid = patient["id"]
        days = _chosen(model._admission, pid)
        rooms = _chosen(model._room, pid)
        theaters = _chosen(model._ot, pid)

        if not days:
            if rooms or theaters:
                errors.append(f"{pid}: not admitted but has room {rooms} / OT {theaters}")
            patients.append({"id": pid, "admission_day": "none"})
            continue

        if len(days) > 1:
            errors.append(f"{pid}: admitted on several days {days}")
        if len(rooms) != 1:
            errors.append(f"{pid}: admitted but assigned {len(rooms)} rooms {rooms}")
        if len(theaters) != 1:
            errors.append(f"{pid}: admitted but assigned {len(theaters)} OTs {theaters}")
        if len(days) == 1 and len(rooms) == 1 and len(theaters) == 1:
            patients.append({
                "id": pid,
                "admission_day": days[0],
                "room": rooms[0],
                "operating_theater": theaters[0],
            })

    if errors:
        raise ValueError(f"Inconsistent solution for {model.ModelName}:\n  " + "\n  ".join(errors))
    return patients


def extract_solution(model, instance):
    """Turn a solved model into a solution in the IHTC JSON form.

    Returns None if Gurobi found no solution.
    TODO: "nurses" part is yet to be added.
    """
    if model.SolCount == 0:
        return None
    return {"patients": extract_patients(model, instance)}


def write_solution(name, solution, output_dir="./solutions"):
    """Write `solution` to `output_dir`/sol_<name>.json and return the path."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"sol_{name}.json"
    path.write_text(json.dumps(solution, indent=4))
    return path


def exact_model(name, instance, output_dir="./solutions", time_limit=None, verbose=False):
    """Solve one instance with the exact Gurobi model and write the solution.

    The solution is written to `output_dir`/sol_<name>.json. Returns the
    solution, or None (and writes nothing) if Gurobi found no solution.
    """
    model = build_model(name, instance)
    model.Params.OutputFlag = int(verbose)
    if time_limit is not None:
        model.Params.TimeLimit = time_limit
    model.optimize()
    solution = extract_solution(model, instance)
    model.dispose()

    if solution is not None:
        write_solution(name, solution, output_dir)
    return solution

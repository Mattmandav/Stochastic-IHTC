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


def day_and_type_to_shift(day, shift_type, shift_types):
    """Global shift index of `shift_type` (e.g. "late") on `day`."""
    return day * len(shift_types) + shift_types.index(shift_type)


def shift_to_day_and_type(shift, shift_types):
    """Inverse of `day_and_type_to_shift`: global shift index to (day, shift type)."""
    day, k = divmod(shift, len(shift_types))
    return day, shift_types[k]


def build_model(name, instance):
    """Build the Gurobi model for one instance.

    Variables (stored on the model for use when extracting the solution):
        admission[p, d]: 1 if patient p is admitted on day d
        room[p, r]:      1 if patient p is admitted to room r
        ot[p, t]:        1 if patient p is admitted to operating theatre t
        patient_assignment[p, d, r]: 1 if patient p is admitted on day d to room r
        nurse_working_shifts[n, s]:  1 if nurse n works shift s (fixed by the roster)
        nurse_assignment[n, s, r]:   1 if nurse n covers room r in shift s

    Shifts are numbered globally, s = day * len(shift_types) + shift index;
    see `shift_to_day_and_type`.

    TODO: constraints and objective are yet to be specified.
    """
    patients = [p["id"] for p in instance["patients"]]
    days = range(instance["days"])
    rooms = [r["id"] for r in instance["rooms"]]
    theaters = [t["id"] for t in instance["operating_theaters"]]
    genders = sorted({person["gender"] for person in instance["patients"] + instance["occupants"]})
    nurses = [n["id"] for n in instance["nurses"]]
    shifts = range(instance["days"] * len(instance["shift_types"]))

    # Variables
    model = gp.Model(name)
    model._shift_types = instance["shift_types"]
    model._admission = model.addVars(patients, days, vtype=GRB.BINARY, name="admission")
    model._room = model.addVars(patients, rooms, vtype=GRB.BINARY, name="room")
    model._ot = model.addVars(patients, theaters, vtype=GRB.BINARY, name="ot")
    model._room_gender = model.addVars(rooms, genders, vtype=GRB.BINARY, name="room_gender")
    model._room_occupancy_count = model.addVars(rooms, days, vtype=GRB.INTEGER, name="room_occupancy_count")
    model._patient_assignment = model.addVars(patients, days, rooms, vtype=GRB.BINARY, name="patient_assignment")
    model._nurse_working_shifts = model.addVars(nurses, shifts, vtype=GRB.BINARY, name="nurse_working_shifts")
    model._nurse_assignment = model.addVars(nurses, shifts, rooms, vtype=GRB.BINARY, name="nurse_assignment")

    # The roster is data: fix nurse_working_shifts to it
    rostered = {
        (nurse["id"], day_and_type_to_shift(w["day"], w["shift"], instance["shift_types"]))
        for nurse in instance["nurses"] for w in nurse["working_shifts"]
    }
    for (n, s), var in model._nurse_working_shifts.items():
        var.LB = var.UB = 1 if (n, s) in rostered else 0

    """
    Linking constraints
    """
    # patient_assignment is admission and room combined
    model.addConstrs(
        (model._patient_assignment.sum(p, d, "*") == model._admission[p, d] for p in patients for d in days),
        name="link_admission",
    )
    model.addConstrs(
        (model._patient_assignment.sum(p, "*", r) == model._room[p, r] for p in patients for r in rooms),
        name="link_room",
    )
    # Each patient is admitted at most once, and has one OT if and only if admitted
    model.addConstrs((model._admission.sum(p, "*") <= 1 for p in patients), name="admit_once")
    model.addConstrs(
        (model._ot.sum(p, "*") == model._admission.sum(p, "*") for p in patients),
        name="link_ot",
    )
    # Nurses can only cover rooms in shifts they work
    model.addConstrs(
        (model._nurse_assignment[n, s, r] <= model._nurse_working_shifts[n, s]
         for n in nurses for s in shifts for r in rooms),
        name="link_nurse_shift",
    )

    """
    # Hard constraints
    """

    # H5 Mandatory versus optional patients: All mandatory patients must be admitted within the decision horizon, whereas optional patients may be postponed to future periods

    # H6 Admission day: A patient can be admitted on any day from their release date to their due date. Given that optional patients do not have a due date, they can be admitted on any day after their release date.

    """
    # Soft constraints
    """
    

    return model


def _chosen(variables, *prefix):
    """Remaining index of the variables[*prefix, ...] that are 1 in the current solution."""
    k = len(prefix)
    chosen = [key[k:] for key, var in variables.items() if key[:k] == prefix and var.X > 0.5]
    return [c[0] if len(c) == 1 else c for c in chosen]


def extract_patients(model, instance):
    """Build the "patients" part of the solution JSON from patient_assignment and ot.

    Checks that each patient is either admitted once (one day and room in
    patient_assignment) with exactly one OT, or not admitted with no OT.
    """
    patients = []
    errors = []
    for patient in instance["patients"]:
        pid = patient["id"]
        assignments = _chosen(model._patient_assignment, pid)  # [(day, room), ...]
        theaters = _chosen(model._ot, pid)

        if not assignments:
            if theaters:
                errors.append(f"{pid}: not admitted but has OT {theaters}")
            patients.append({"id": pid, "admission_day": "none"})
            continue

        if len(assignments) > 1:
            errors.append(f"{pid}: admitted more than once (day, room) {assignments}")
        if len(theaters) != 1:
            errors.append(f"{pid}: admitted but assigned {len(theaters)} OTs {theaters}")
        if len(assignments) == 1 and len(theaters) == 1:
            day, room = assignments[0]
            patients.append({
                "id": pid,
                "admission_day": day,
                "room": room,
                "operating_theater": theaters[0],
            })

    if errors:
        raise ValueError(f"Inconsistent patients for {model.ModelName}:\n  " + "\n  ".join(errors))
    return patients


def extract_nurses(model, instance):
    """Build the "nurses" part of the solution JSON from nurse_working_shifts and nurse_assignment.

    Every working shift is listed, with the rooms covered (possibly none).
    Checks that no nurse covers a room in a shift they do not work.
    """
    nurses = []
    errors = []
    for nurse in instance["nurses"]:
        nid = nurse["id"]
        working = sorted(_chosen(model._nurse_working_shifts, nid))
        assignments = []
        for s in sorted({s for s, _ in _chosen(model._nurse_assignment, nid)} | set(working)):
            rooms = _chosen(model._nurse_assignment, nid, s)
            day, shift_type = shift_to_day_and_type(s, model._shift_types)
            if s not in working:
                errors.append(f"{nid}: covers rooms {rooms} on day {day} ({shift_type}) but does not work then")
                continue
            assignments.append({"day": day, "shift": shift_type, "rooms": rooms})
        nurses.append({"id": nid, "assignments": assignments})

    if errors:
        raise ValueError(f"Inconsistent nurses for {model.ModelName}:\n  " + "\n  ".join(errors))
    return nurses


def extract_solution(model, instance):
    """Turn a solved model into a solution in the IHTC JSON form.

    Returns None if Gurobi found no solution.
    """
    if model.SolCount == 0:
        return None
    return {
        "patients": extract_patients(model, instance),
        "nurses": extract_nurses(model, instance),
    }


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

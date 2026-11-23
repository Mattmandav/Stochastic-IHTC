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


def relative_overload_tolerances(instance, rho_surgeon=0.0, rho_theater=0.0):
    """Expected overload tolerances as a fraction of each day's capacity.

    Returns (surgeon_overload_tolerance, theater_overload_tolerance), dicts mapping
    (surgeon id, day) and (theatre id, day) to minutes: kappa = rho * capacity.
    Days with zero capacity get zero tolerance.
    """
    surgeon = {
        (u["id"], d): rho_surgeon * cap
        for u in instance["surgeons"] for d, cap in enumerate(u["max_surgery_time"])
    }
    theater = {
        (t["id"], d): rho_theater * cap
        for t in instance["operating_theaters"] for d, cap in enumerate(t["availability"])
    }
    return surgeon, theater


def build_model(name, instance, surgeon_overload_tolerance=None, theater_overload_tolerance=None):
    """Build the Gurobi model for one instance.

    `surgeon_overload_tolerance` and `theater_overload_tolerance` are the expected
    overload tolerances kappa^s[u, d] and kappa^ot[t, d] for H3 and H4: dicts
    mapping (surgeon id, day) and (theatre id, day) to minutes. Missing entries,
    or None, mean 0 (the deterministic constraint). See
    `relative_overload_tolerances` for tolerances proportional to capacity.

    Variables (stored on the model for use when extracting the solution):
        admission[p, d]: 1 if patient p is admitted on day d
        room[p, r]:      1 if patient p is admitted to room r
        ot[p, t]:        1 if patient p is admitted to operating theatre t
        patient_assignment[p, d, r]: 1 if patient p is admitted on day d to room r
        nurse_working_shifts[n, s]:  1 if nurse n works shift s (fixed by the roster)
        nurse_assignment[n, s, r]:   1 if nurse n covers room r in shift s
        theater_assignment[p, d, t]: 1 if patient p has surgery on day d in operating theatre t
        surgeon_time[u, d]:          total surgery time of surgeon u on day d
        theater_time[t, d]:          total surgery time in operating theatre t on day d
        room_gender[r, d, g]:        1 if room r holds gender g on day d
        room_occupancy_count[r, d]:  number of occupants and patients in room r on day d

    Expressions:
        patient_present[p, r, d]: 1 if patient p is in room r on day d

    Shifts are numbered globally, s = day * len(shift_types) + shift index;
    see `shift_to_day_and_type`.

    TODO: remaining constraints and objective are yet to be specified.
    """
    patients = [p["id"] for p in instance["patients"]]
    days = range(instance["days"])
    rooms = [r["id"] for r in instance["rooms"]]
    theaters = [t["id"] for t in instance["operating_theaters"]]
    genders = sorted({person["gender"] for person in instance["patients"] + instance["occupants"]})
    nurses = [n["id"] for n in instance["nurses"]]
    surgeons = [u["id"] for u in instance["surgeons"]]
    shifts = range(instance["days"] * len(instance["shift_types"]))

    # Variables
    model = gp.Model(name)
    model._shift_types = instance["shift_types"]
    model._admission = model.addVars(patients, days, vtype=GRB.BINARY, name="admission")
    model._room = model.addVars(patients, rooms, vtype=GRB.BINARY, name="room")
    model._ot = model.addVars(patients, theaters, vtype=GRB.BINARY, name="ot")
    model._room_gender = model.addVars(rooms, days, genders, vtype=GRB.BINARY, name="room_gender")
    model._room_occupancy_count = model.addVars(rooms, days, vtype=GRB.INTEGER, name="room_occupancy_count")
    model._patient_assignment = model.addVars(patients, days, rooms, vtype=GRB.BINARY, name="patient_assignment")
    model._nurse_working_shifts = model.addVars(nurses, shifts, vtype=GRB.BINARY, name="nurse_working_shifts")
    model._nurse_assignment = model.addVars(nurses, shifts, rooms, vtype=GRB.BINARY, name="nurse_assignment")
    model._theater_assignment = model.addVars(patients, days, theaters, vtype=GRB.BINARY, name="theater_assignment")
    model._surgeon_time = model.addVars(surgeons, days, lb=0, name="surgeon_time")
    model._theater_time = model.addVars(theaters, days, lb=0, name="theater_time")

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
    # theater_assignment is admission and ot combined. Together these also give each
    # patient one OT if and only if admitted (admitted at most once is H5).
    model.addConstrs(
        (model._theater_assignment.sum(p, d, "*") == model._admission[p, d] for p in patients for d in days),
        name="link_theater_admission",
    )
    model.addConstrs(
        (model._theater_assignment.sum(p, "*", t) == model._ot[p, t] for p in patients for t in theaters),
        name="link_theater_ot",
    )

    # Surgery takes place on the admission day
    duration = {p["id"]: p["surgery_duration"] for p in instance["patients"]}
    surgeon_patients = {u: [p["id"] for p in instance["patients"] if p["surgeon_id"] == u] for u in surgeons}
    model.addConstrs(
        (model._surgeon_time[u, d]
         == gp.quicksum(duration[p] * model._admission[p, d] for p in surgeon_patients[u])
         for u in surgeons for d in days),
        name="link_surgeon_time",
    )
    model.addConstrs(
        (model._theater_time[t, d]
         == gp.quicksum(duration[p] * model._theater_assignment[p, d, t] for p in patients)
         for t in theaters for d in days),
        name="link_theater_time",
    )

    # Patient presence: p is in room r on day d if admitted to r on one of the
    # length_of_stay days up to and including d. A linear expression, not a variable.
    los = {p["id"]: p["length_of_stay"] for p in instance["patients"]}
    model._patient_present = {
        (p, r, d): gp.quicksum(
            model._patient_assignment[p, a, r] for a in range(max(0, d - los[p] + 1), d + 1)
        )
        for p in patients for r in rooms for d in days
    }

    # Occupants (boundary data) are in their room from day 0 for length_of_stay days
    occupant_count = {(r, d): 0 for r in rooms for d in days}
    occupant_genders = {(r, d): set() for r in rooms for d in days}
    for o in instance["occupants"]:
        for d in range(min(o["length_of_stay"], instance["days"])):
            occupant_count[o["room_id"], d] += 1
            occupant_genders[o["room_id"], d].add(o["gender"])

    # room_occupancy_count is the number of occupants and patients in room r on day d
    model.addConstrs(
        (model._room_occupancy_count[r, d]
         == occupant_count[r, d] + gp.quicksum(model._patient_present[p, r, d] for p in patients)
         for r in rooms for d in days),
        name="link_occupancy",
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

    # H1 No gender mix: Patients of different genders may not share a room on any day.
    # Each room has at most one gender per day; occupants fix it, and a present
    # patient forces their gender. An empty room may change gender between days.
    gender = {p["id"]: p["gender"] for p in instance["patients"]}
    model.addConstrs(
        (model._room_gender.sum(r, d, "*") <= 1 for r in rooms for d in days),
        name="H1_one_gender",
    )
    for (r, d), occupant_gs in occupant_genders.items():
        for g in occupant_gs:
            model._room_gender[r, d, g].LB = 1
    model.addConstrs(
        (model._patient_present[p, r, d] <= model._room_gender[r, d, gender[p]]
         for p in patients for r in rooms for d in days),
        name="H1_patient_gender",
    )

    # H2 Compatible rooms: Patients can only be assigned to one of their compatible rooms.
    for p in instance["patients"]:
        for r in p["incompatible_room_ids"]:
            model._room[p["id"], r].UB = 0

    # H3 Surgeon overtime: The maximum daily surgery time of a surgeon must not be exceeded.
    # Expected overload version: E[surgeon_time - max_surgery_time] <= kappa^s[u, d]. The
    # overload is signed and surgery_time is linear, so only the mean durations
    # (the instance's surgery_duration) matter: surgeon_time <= max_surgery_time + kappa.
    # With kappa = 0 (the default) this is the deterministic H3.
    max_surgery_time = {u["id"]: u["max_surgery_time"] for u in instance["surgeons"]}
    kappa_s = surgeon_overload_tolerance or {}
    model.addConstrs(
        (model._surgeon_time[u, d] <= max_surgery_time[u][d] + kappa_s.get((u, d), 0)
         for u in surgeons for d in days),
        name="H3_surgeon_time",
    )

    # H4 OT overtime: The duration of all surgeries allocated to an OT on a day must not exceed the OT’s maximum capacity.
    # Expected overload version, as for H3: theater_time <= availability + kappa^ot[t, d].
    availability = {t["id"]: t["availability"] for t in instance["operating_theaters"]}
    kappa_ot = theater_overload_tolerance or {}
    model.addConstrs(
        (model._theater_time[t, d] <= availability[t][d] + kappa_ot.get((t, d), 0)
         for t in theaters for d in days),
        name="H4_theater_time",
    )

    # H5 Mandatory versus optional patients: All mandatory patients must be admitted within the decision horizon, whereas optional patients may be postponed to future periods
    mandatory = [p["id"] for p in instance["patients"] if p["mandatory"]]
    optional = [p["id"] for p in instance["patients"] if not p["mandatory"]]
    model.addConstrs((model._admission.sum(p, "*") == 1 for p in mandatory), name="H5_mandatory")
    model.addConstrs((model._admission.sum(p, "*") <= 1 for p in optional), name="H5_optional")

    # H6 Admission day: A patient can be admitted on any day from their release date to their due date. Given that optional patients do not have a due date, they can be admitted on any day after their release date.
    for p in instance["patients"]:
        last_day = p["surgery_due_day"] if p["mandatory"] else instance["days"] - 1
        for d in days:
            if d < p["surgery_release_day"] or d > last_day:
                model._admission[p["id"], d].UB = 0

    # H7 Room capacity: The number of patients that occupy a room per day cannot exceed the capacity of the room.
    capacity = {r["id"]: r["capacity"] for r in instance["rooms"]}
    model.addConstrs(
        (model._room_occupancy_count[r, d] <= capacity[r] for r in rooms for d in days),
        name="H7_capacity",
    )

    # H8 For each shift, each occupied room must be allocated to a nurse who is on duty during this shift.
    # (Nurses only cover rooms in shifts they work: see link_nurse_shift.)
    # At most one nurse per room and shift
    model.addConstrs(
        (model._nurse_assignment.sum("*", s, r) <= 1 for s in shifts for r in rooms),
        name="H8_one_nurse",
    )
    # A room occupied by an occupant must have a nurse in every shift of that day
    shifts_per_day = len(instance["shift_types"])
    model.addConstrs(
        (model._nurse_assignment.sum("*", s, r) == 1
         for (r, d), count in occupant_count.items() if count > 0
         for s in range(d * shifts_per_day, (d + 1) * shifts_per_day)),
        name="H8_occupant_room",
    )
    # A present patient forces a nurse in their room in every shift of that day
    model.addConstrs(
        (model._patient_present[p, r, d] <= model._nurse_assignment.sum("*", s, r)
         for p in patients for r in rooms for d in days
         for s in range(d * shifts_per_day, (d + 1) * shifts_per_day)),
        name="H8_patient_room",
    )

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


def exact_model(name, instance, output_dir="./solutions", time_limit=None, verbose=False,
                surgeon_overload_tolerance=None, theater_overload_tolerance=None):
    """Solve one instance with the exact Gurobi model and write the solution.

    The solution is written to `output_dir`/sol_<name>.json. Returns the
    solution, or None (and writes nothing) if Gurobi found no solution.
    The overload tolerances are passed to `build_model` (default: none, i.e. the
    deterministic H3 and H4).
    """
    model = build_model(name, instance, surgeon_overload_tolerance, theater_overload_tolerance)
    model.Params.OutputFlag = int(verbose)
    if time_limit is not None:
        model.Params.TimeLimit = time_limit
    model.optimize()
    solution = extract_solution(model, instance)
    model.dispose()

    if solution is not None:
        write_solution(name, solution, output_dir)
    return solution

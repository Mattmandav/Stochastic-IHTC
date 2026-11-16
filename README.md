# Stochastic IHTC

Exact (Gurobi) models for the Integrated Healthcare Timetabling Problem (IHTP).

## Usage

```bash
uv run main.py
```

Each instance in `data/` is solved in turn and its solution is written to
`solutions/sol_<instance>.json`.

## Licence

The code in this repository is licensed under the MIT License (see [`LICENSE`](LICENSE)).
The instances in `data/` are licensed separately under CC BY 4.0 (see below).

## Data

The instances in `data/` (`small01.json` to `small09.json`) are the small IHTP
dataset from the [Integrated Healthcare Timetabling Competition 2024 (IHTC 2024)](https://ihtc2024.github.io/),
available from the [IHTP page](https://ihtc2024.github.io/ihtp/index.html).
They are included unmodified.

### Licence

The IHTC 2024 instances are licensed under the
[Creative Commons Attribution 4.0 International License (CC BY 4.0)](https://creativecommons.org/licenses/by/4.0/).
This licence covers the files in `data/` only.

### Citation

If you use these instances, please cite:

> Ceschia, S., Rosati, R. M., Schaerf, A., Smet, P., Vanden Berghe, G., & Zanazzo, E. (2025).
> The Integrated Healthcare Timetabling Competition 2024.
> *Operations Research, Data Analytics and Logistics*, 45, 200481.
> https://doi.org/10.1016/j.ordal.2025.200481

```bibtex
@article{CRSSVZ25,
  title   = {The Integrated Healthcare Timetabling Competition 2024},
  author  = {Ceschia, Sara and Rosati, Roberto Maria and Schaerf, Andrea and Smet, Pieter and Vanden Berghe, Greet and Zanazzo, Eugenia},
  journal = {Operations Research, Data Analytics and Logistics},
  volume  = {45},
  pages   = {200481},
  year    = {2025},
  doi     = {10.1016/j.ordal.2025.200481}
}
```

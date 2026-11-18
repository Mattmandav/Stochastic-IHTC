# Stochastic IHTC

Exact (Gurobi) models for the Integrated Healthcare Timetabling Problem (IHTP).

## Usage

```bash
uv run main.py
```

Each instance in `data/` is solved in turn and its solution is written to
`solutions/sol_<instance>.json`. The solutions are then checked with the
official IHTC 2024 validator and a table of violations and costs is printed.

The validator is compiled automatically on first use, which needs `g++` on
your `PATH`. To compile it by hand:

```bash
cd validator
g++ -O2 -o IHTP_Validator IHTP_Validator.cc
```

## Licence

The code in this repository is licensed under the MIT License (see [`LICENSE`](LICENSE)),
except for the third-party files listed below, which keep their own terms.

| Path | Author | Licence |
| --- | --- | --- |
| `data/` | IHTC 2024 organisers | CC BY 4.0 (see [Data](#data)) |
| `validator/IHTP_Validator.cc` | IHTC 2024 organisers | None stated; not covered by this repository's MIT licence |
| `validator/json.hpp` | Niels Lohmann ([nlohmann/json](https://github.com/nlohmann/json), `develop` branch, header version 3.12.0) | MIT (see [`validator/LICENSE-nlohmann-json`](validator/LICENSE-nlohmann-json)) |

## Validator

`validator/IHTP_Validator.cc` is the official solution validator of the
[Integrated Healthcare Timetabling Competition 2024](https://ihtc2024.github.io/),
included unmodified (apart from line endings). It depends on the JSON for Modern C++
single header `validator/json.hpp` by Niels Lohmann, taken unmodified from the
`develop` branch as the validator's instructions direct.

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

from pathlib import Path

from src.optimiser import exact_model, load_instances
from src.validator import print_summary, validate

DATA_DIR = Path("./data")
SOLUTION_DIR = Path("./solutions")


def main():
    solutions = {}
    for name, instance in load_instances(DATA_DIR).items():
        solutions[name] = exact_model(name, instance, output_dir=SOLUTION_DIR)
        if solutions[name] is None:
            print(f"{name}: no solution found")
        else:
            print(f"{name}: solution written to {SOLUTION_DIR / f'sol_{name}.json'}")

    results = {
        name: None if solution is None else validate(DATA_DIR / f"{name}.json", SOLUTION_DIR / f"sol_{name}.json")
        for name, solution in solutions.items()
    }
    print_summary(results)


if __name__ == "__main__":
    main()

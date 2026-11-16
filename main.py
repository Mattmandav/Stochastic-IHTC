from src.optimiser import exact_model, load_instances


def main():
    for name, instance in load_instances("./data").items():
        solution = exact_model(name, instance, output_dir="./solutions")
        if solution is None:
            print(f"{name}: no solution found")
        else:
            print(f"{name}: solution written to ./solutions/sol_{name}.json")


if __name__ == "__main__":
    main()

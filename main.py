from src.optimiser import exact_model


def main():
    solutions = exact_model("./data")
    for name, solution in solutions.items():
        print(name, solution)


if __name__ == "__main__":
    main()

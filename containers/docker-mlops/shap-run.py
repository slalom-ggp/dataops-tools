import fire

print("Loaded file")


def main(infile, outfile):
    print(f"Beginning job to process '{infile}' and save to '{outfile}'")
    print("Processing complete")


if __name__ == "__main__":
    fire.Fire(main)

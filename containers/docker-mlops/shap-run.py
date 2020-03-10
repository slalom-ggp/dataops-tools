import fire

print("Loaded file")


def main(infile, outfile):
    """
    Process the pickled model input `infile` and save to `outfile`.

    Parameters:
        infile (str): the input path
        outfile (str): the output path
    """
    print(f"Beginning job to process '{infile}' and save to '{outfile}'")
    print("Processing complete")


if __name__ == "__main__":
    fire.Fire(main)

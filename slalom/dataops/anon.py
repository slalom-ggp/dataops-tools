"""Anonymizing functions for Slalom DataOps."""

import hashlib

import fire
import uio

try:
    import pandas
except ImportError as ex:
    raise ImportError(
        "Could not import Pandas library, which is required to perform "
        "anonymization functions. You may be able to resolve this by running "
        f"`pip install pandas`. Full error message: {ex}"
    )

HASH_FUNCTIONS = {"MD5": hashlib.md5, "SHA256": hashlib.sha256, "SHA512": hashlib.sha512}


def anonymize_file(filepath: str, hash_key: str, hash_function: str = "MD5"):
    """
    Hashes the first column of the provided CSV or Excel file.

    The output will be saved as a new anonymized version of the file.

    Usage Guidelines:

    1. File should be in Excel format, with a single sheet.
    2. The first column in the Excel sheet should contain the ID to anonymize.
    3. Currently supported hashing functions are: MD5, SHA256, and SHA512
    4. **NOTE:** Always open and review the file to confirm that the anonymization process
       was successful.

    Parameters
    ----------
    filepath : str
        The path to the file to be anonymized.
    hash_key : str
        A hash key to be used as a seed during anonymization.
    hash_function : str, optional
        The hashing function to use, by default "MD5" (most ubiquitous) will be used

    Raises
    ------
    ValueError
        If an incorrect hash_key is requested.
    FileExistsError
        If the file cannot be found.
    """
    if hash_function not in HASH_FUNCTIONS:
        raise ValueError(
            f"Unsupported hash function {hash_function}. "
            f"Expected one of : {HASH_FUNCTIONS.keys()}"
        )
    if hash_key.upper() in HASH_FUNCTIONS.keys():
        raise ValueError(
            f"A hash algorithm was attempted to be passed as the encryption function. "
            f"Please check the syntax for a missing encryption key and try again."
            f"Details: hash key cannot be one of : {HASH_FUNCTIONS.keys()}"
        )
    if not uio.file_exists(filepath):
        raise FileExistsError(f"Could not find file {filepath}")

    def hash_fn(x):
        fn = HASH_FUNCTIONS[hash_function]
        return fn(f"{hash_key}{x}".encode("utf-8")).hexdigest()

    df = pandas.read_excel(filepath)
    df[df.columns[0]] = df[df.columns[0]].apply(hash_fn)

    new_filepath = (
        ".".join(filepath.split(".")[:-1]) + "-anonymized." + filepath.split(".")[-1]
    )
    print(new_filepath)
    df.to_excel(new_filepath, index=False)


def main():
    fire.Fire({"anonymize": anonymize_file})


if __name__ == "__main__":
    main()

""" slalom.dataops.pandasutils module """

import os

from slalom.dataops import io
from slalom.dataops import jobs
from slalom.dataops.logs import (
    get_logger,
    logged,
    logged_block,
    _get_printable_context,
    bytes_to_string,
)

logging = get_logger("slalom.dataops.sparkutils")

try:
    import pandas as pd
except Exception as ex:
    pd = None
    logging.warning(f"Could not load pandas library. Try 'pip install pandas'. {ex}")


def _raise_if_missing_pandas(as_warning=False, ex=None):
    if not pd:
        msg = f"Could not load pandas library. Try 'pip install pandas'. {ex or ''}"
        if as_warning:
            logging.warning(msg)
        else:
            raise RuntimeError(msg)


def read_csv_dir(csv_dir, usecols=None, dtype=None):
    _raise_if_missing_pandas()
    df_list = []
    for s3_path in io.list_s3_files(csv_dir):
        if "_SUCCESS" not in s3_path:
            if io.USE_SCRATCH_DIR:
                scratch_dir = io.get_scratch_dir()
                filename = os.path.basename(s3_path)
                csv_path = os.path.join(scratch_dir, filename)
                if os.path.exists(csv_path):
                    logging.info(
                        f"Skipping download of '{s3_path}'. File exists as: '{csv_path}' "
                        "(If you do not want to use this file, please delete "
                        "the file or unset the USE_SCRATCH_DIR environment variable.)"
                    )
                else:
                    logging.info(
                        f"Downloading S3 file '{s3_path}' to scratch dir: '{csv_path}'"
                    )
                io.download_s3_file(s3_path, csv_path)
            else:
                logging.info(f"Reading from S3 file: {s3_path}")
                csv_path = s3_path
            df = pd.read_csv(
                csv_path, index_col=None, header=0, usecols=usecols, dtype=dtype
            )
            df_list.append(df)
    logging.info(f"Concatenating datasets from: {csv_dir}")
    ret_val = pd.concat(df_list, axis=0, ignore_index=True)
    logging.info("Dataset concatenation was successful.")
    return ret_val


def get_pandas_df(source_path, usecols=None):
    if not pd:
        raise RuntimeError(
            "Could not execute get_pandas_df(): Pandas library not loaded."
        )
    if ".xlsx" in source_path.lower():
        df = read_excel_sheet(source_path, usecols=usecols)
    else:
        try:
            df = pd.read_csv(source_path, low_memory=False, usecols=usecols)
        except Exception as ex:
            if "Error tokenizing data. C error" in str(ex):
                logging.warning(
                    f"Failed read_csv() using default 'c' engine. "
                    f"Retrying with engine='python'...\n{ex}"
                )
                df = pd.read_csv(source_path, usecols=usecols, engine="python")
            else:
                raise ex
    return df


def read_excel_sheet(sheet_path, usecols=None):
    """
    Expects path in form of '/path/to/file.xlsx/#sheet name'
    S3 paths are excepted.
    """
    _raise_if_missing_pandas()
    filepath, sheetname = sheet_path.split("/#")
    df = pd.read_excel(filepath, sheetname=sheetname, usecols=usecols)
    return df


def print_pandas_mem_usage(df, df_name, print_fn=logging.info, min_col_size_mb=500):
    if not pd:
        logging.warning("Pandas support is not installed. Try 'pip install pandas'.")
        return None
    col_mem_usage = df.memory_usage(index=True, deep=True).sort_values(ascending=False)
    ttl_mem_usage = col_mem_usage.sum()
    col_mem_usage = col_mem_usage.nlargest(n=5)
    col_mem_usage = col_mem_usage[col_mem_usage > min_col_size_mb * 1024 * 1024]
    col_mem_usage = col_mem_usage.apply(bytes_to_string)
    msg = f"Dataframe '{df_name}' mem usage: {bytes_to_string(ttl_mem_usage)}"
    if col_mem_usage.size:
        col_usage_str = ", ".join(
            [
                f"{col}({'Index' if col == 'Index' else df[col].dtype}):{size}"
                for col, size in col_mem_usage.iteritems()
            ]
        )
        msg += f". Largest columns (over {min_col_size_mb}MB): {col_usage_str}"
    print_fn(msg)
    return msg

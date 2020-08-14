# dataops-tools

[![PyPI - Python Version](https://img.shields.io/pypi/pyversions/slalom.dataops.svg)](https://pypi.org/project/slalom.dataops/) [![PyPI version](https://badge.fury.io/py/slalom.dataops.svg)](https://badge.fury.io/py/slalom.dataops) [![CI/CD Badge (master)](https://github.com/slalom-ggp/dataops-tools/workflows/CI/CD%20Builds/badge.svg)](https://github.com/slalom-ggp/dataops-tools/actions?query=workflow%3A%22CI/CD%20Builds%22) [![Docker Publish (latest)](<https://github.com/slalom-ggp/dataops-tools/workflows/Docker%20Publish%20(latest)/badge.svg>)](https://github.com/slalom-ggp/dataops-tools/actions?query=workflow%3A%22Docker+Publish+%28latest%29%22)

Reusable tools, utilities, and containers that accelerate data processing and DevOps.

## Installation

Compatible with Python 3.7 and 3.8.

```bash
pip install slalom.dataops
```

## Running via Command Line

After installing via pip, you will have access to the following command line tools:

| Command   | Description                                                                                         |
| --------- | --------------------------------------------------------------------------------------------------- |
| `s-anon`  | Run anonymization functions against a data file.                                                    |
| `s-spark` | Run Spark programs and Jupyter notebooks (natively, containerized via docker, or remotely via ECS). |
| `s-infra` | Run Terraform IAC (Infrastructure-as-Code) automation.                                              |

## Spin off Projects

> NOTE: Rather than maintain a single monolithic repo, some child projects have spun off from this one.

Here is a list of the current spinoff projects:

* **[dock-r](https://github.com/aaronsteers/dock-r)** - Automates docker functions in an easy-to-user wrapper. (Replaces `s-docker`.)
* **[tapdance](https://github.com/aaronsteers/tapdance)** - Automates data extract-load features using the open source Singer taps platform (www.singer.io). (Replaces `s-tap`.)
* **[uio](https://github.com/aaronsteers/uio)** - A universal file IO library which can read from and write to any path (e.g. S3, Azure, local, or Github) using a single unified interface regardless of provider. (Replaces `s-io`.)

## Running the Excel anonymization process

This process will hash the first column of the provided CSV or Excel file.

The output will be saved as a new anonymized version of the file.

Usage Guidelines:

1. File should be in Excel format, with a single sheet.
2. The first column in the Excel sheet should contain the ID to anonymize.
3. Currently supported hashing functions are: MD5, SHA256, and SHA512
4. **NOTE:** Always open and review the file to confirm that the anonymization process
   was successful.

### Installing extra libraries

In order to run the anonymization process, you may require some additional components. To install slalom dataops,
along with the needed libraries (specifically, Pandas and Excel), run the following from any admin prompt.

```cmd
pip install slalom.dataops[Pandas]
```

Syntax:

```md
SYNOPSIS
    s-anon anonymize FILEPATH [[--hash_key=]HASH_KEY] [[--hash_function=]HASH_FUNCTION]

DESCRIPTION
    The output will be saved as a new anonymized version of the file.

    Usage Guidelines:

    1. File should be in Excel format, with a single sheet.
    2. The first column in the Excel sheet should contain the ID to anonymize.
    3. Currently supported hashing functions are: MD5, SHA256, and SHA512
    4. **NOTE:** Always open and review the file to confirm that the anonymization process
       was successful.

POSITIONAL ARGUMENTS
    FILEPATH
        The path to the file to be anonymized.

FLAGS
    --hash_key=HASH_KEY
        A hash key to be used as a seed during anonymization.
    --hash_function=HASH_FUNCTION
        The hashing function to use, by default "MD5"
```

Sample:

```cmd
s-anon anonymize path/to/file.xlsx --hash_key=MySuperSecretAnonymizationSeed --hash_function=SHA256
```

Or equivalently:

```cmd
s-anon anonymize path/to/file.xlsx MySuperSecretAnonymizationSeed SHA256
```

## Testing

```bash
> python
```

```python
import dock_r, sparkutils; dock_r.smart_build("containers/docker-spark/Dockerfile", "local-spark", push_core=False); dock_r.smart_build("Dockerfile", "local-dataops", push_core=False); spark = sparkutils.get_spark(dockerized=True)
```

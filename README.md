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

| Command    | Description                                                                                                              |
| ---------- | ------------------------------------------------------------------------------------------------------------------------ |
| `s-spark`  | Run Spark programs and Jupyter notebooks (natively, containerized via docker, or remotely via ECS).                      |
| `s-docker` | Run Docker and ECS commands.                                                                                             |
| `s-infra`  | Run Terraform IAC (Infrastructure-as-Code) automation.                                                                   |
| `s-io`     | Read and write files from a variety of cloud platforms (full support for S3, Azure, and Git as if they were local paths. |
| `s-tap`    | Deprecated. Please see the spinoff [tapdance](https://github.com/aaronsteers/tapdance) library mentioned below. Automates extraction using the open source Singer taps platform (www.singer.io).                                          |

## Spin off Projects

> NOTE: Rather than maintain a single monolithic repo, some child projects have spun off from this one.

Here is a list of the current spinoff projects:

* **[dock-r]()** - Automates docker functions in an easy-to-user wrapper. (Replaces `s-docker`.)
* **[tapdance]()** - Automates data extract-load features using the open source Singer taps platform (www.singer.io). (Replaces `s-tap`.)
* **[uio]()** - A universal file IO library which can read from and write to any path (e.g. S3, Azure, local, or Github) using a single unified interface regardless of provider. (Replaces `s-io`.)

## Testing

```bash
> python
```

```python
from slalom.dataops import dockerutils, sparkutils; dockerutils.smart_build("containers/docker-spark/Dockerfile", "local-spark", push_core=False); dockerutils.smart_build("Dockerfile", "local-dataops", push_core=False); spark = sparkutils.get_spark(dockerized=True)
```

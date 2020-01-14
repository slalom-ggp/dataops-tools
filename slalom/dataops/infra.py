#!/usr/bin/env python3
from joblib import Parallel, delayed
import os
import sys
from pathlib import Path

import fire
from tqdm import tqdm

code_file = os.path.realpath(__file__)
repo_dir = os.path.dirname(os.path.dirname(os.path.dirname(code_file)))
sys.path.append(os.path.join(repo_dir, "src"))
sys.path.append(os.path.dirname(code_file))

from slalom.dataops.logs import get_logger, logged, logged_block
from slalom.dataops import jobs, io


DEBUG = False
logging = get_logger("slalom.dataops.infra", debug=DEBUG)


def _update_var_output(output_var):
    return_code, output = jobs.run_command(f"terraform output {output_var}", echo=False)
    io.create_text_file(os.path.join("outputs", output_var), contents=output)
    return True


@logged("updating output files")
def update_var_outputs(infra_dir, output_vars=[]):
    outputs_dir = os.path.join(infra_dir, "outputs")
    io.create_folder(outputs_dir)
    for oldfile in io.list_files(outputs_dir):
        io.delete_file(oldfile)
    results = Parallel(n_jobs=40, verbose=2)(
        delayed(_update_var_output)(outvar)
        for outvar in tqdm(output_vars, "Saving output to infra/outputs")
    )


def install(*args, infra_dir="./infra", deploy=False, git_ref="master"):
    """
    Usage example: 
    ```
    s-infra install catalog:aws-prereqs --infra_dir=infra/prereqs --deploy=True
    s-infra install samples:aws --infra_dir=infra --deploy=True
    ```
    Which is identical to:
    ```
    s-infra install catalog:aws-prereqs --infra_dir=infra/prereqs
    s-infra init+apply --infra_dir=infra/prereqs
    s-infra install samples:aws --infra_dir=infra
    s-infra init+apply --infra_dir=infra
    ```
    """
    io.create_folder(infra_dir)
    for arg in args:
        with logged_block(f"installing terraform modules from '{arg}'"):
            infra_type, infra_name = arg.split(":")
            if infra_type not in ["catalog", "samples"]:
                raise ValueError(
                    f"Expected infra_type to be one of: 'catalog', 'samples'. Received type: {infra_type}"
                )
            io.download_folder(
                remote_folder=f"git://github.com/slalom-ggp/dataops-infra#{git_ref}//{infra_type}/{infra_name}",
                local_folder=infra_dir,
            )
    lf = "\n"
    logging.info(f"List of installed modules:\n{lf.join(io.ls(infra_dir))}")
    init(infra_dir=infra_dir)
    if deploy:
        apply(infra_dir=infra_dir)


@logged("initializing terraform project at '{infra_dir}'")
def init(infra_dir: str = "./infra/"):
    infra_dir = os.path.realpath(infra_dir)
    jobs.run_command("terraform init", working_dir=infra_dir)


@logged("applying terraform changes")
def apply(infra_dir: str = "./infra/", save_output: bool = False, prompt: bool = False):
    infra_dir = os.path.realpath(infra_dir)
    jobs.run_command(
        f"terraform apply {'' if prompt else '-auto-approve'}", working_dir=infra_dir
    )
    if save_output:
        update_var_outputs(infra_dir=infra_dir)


def init_and_apply(infra_dir: str = "./infra/", save_output: bool = False):
    infra_dir = os.path.realpath(infra_dir)
    init(infra_dir=infra_dir)
    apply(infra_dir=infra_dir, save_output=save_output, prompt=False)


def main():
    fire.Fire(
        {
            "install": install,
            "init": init,
            "apply": apply,
            "init+apply": init_and_apply,
            "deploy": init_and_apply,
        }
    )


if __name__ == "__main__":
    main()

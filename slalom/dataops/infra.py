#!/usr/bin/env python3
from joblib import Parallel, delayed
import os
import sys
import fire
from pathlib import Path
from tqdm import tqdm

code_file = os.path.realpath(__file__)
repo_dir = os.path.dirname(os.path.dirname(os.path.dirname(code_file)))
sys.path.append(os.path.join(repo_dir, "src"))
sys.path.append(os.path.dirname(code_file))

from slalom.dataops.logs import get_logger, logged, logged_block
from slalom.dataops import jobs, io


DEBUG = False
logging = get_logger("slalom.dataops.infra", debug=DEBUG)


def update_var_output(output_var):
    _, val = jobs.run_command(f"terraform output {output_var}", echo=False)
    io.create_text_file(os.path.join("outputs", output_var), contents=val)
    return True


def main(*args, infra_dir: str = "./infra/", save_output: bool = True):
    infra_dir = os.path.realpath(infra_dir)
    os.chdir(infra_dir)
    if "apply" in args:
        with logged_block("applying terraform changes"):
            jobs.run_command("terraform apply")
    elif "init" in args:
        with logged_block("initializing terraform"):
            jobs.run_command("terraform init")

    if save_output:
        with logged_block("updating output files"):
            outputs_dir = os.path.join(infra_dir, "outputs")
            for oldfile in io.list_files(outputs_dir):
                io.delete_file(oldfile)
            outvars = [
                "docker_repo_root",
                "docker_repo_image_url",
                "ecs_cluster_name",
                "ecs_task_name",
                "ecs_container_name",
                "vpc_private_subnets",
                "aws_region",
                "ecs_security_group",
                "ecs_runtask_cli",
                "ecs_logging_url",
            ]
            results = Parallel(n_jobs=40, verbose=2)(
                delayed(update_var_output)(outvar)
                for outvar in tqdm(outvars, "Saving output to infra/outputs")
            )


if __name__ == "__main__":
    fire.Fire(main)

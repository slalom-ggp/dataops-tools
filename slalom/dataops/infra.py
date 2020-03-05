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


def change_upstream_source(
    dir_to_update=".",
    git_repo="https://github.com/slalom-ggp/dataops-infra",
    branch="master",
    relative_path="../../dataops-infra",
    to_relative=False,
    to_git=False,
    dry_run=False,
):
    """Change Terraform source"""
    if to_relative and to_git or not (to_relative or to_git):
        raise ValueError("Must specify `--to_git` or `--to_relative`, but not both.")
    for tf_file in io.list_files(dir_to_update):
        if tf_file.endswith(".tf"):
            # print(tf_file)
            new_lines = []
            for line in io.get_text_file_contents(tf_file).splitlines():
                new_line = line
                if line.lstrip().startswith("source "):
                    current_path = line.lstrip().split('"')[1]
                    start_pos = max(
                        [current_path.find("catalog/"), current_path.find("components/")]
                    )
                    if start_pos > 0:
                        module_path = current_path[start_pos:].split("?ref=")[0]
                        if to_relative:
                            local_patten = "{relative_path}/{path}"
                            new_path = local_patten.format(
                                relative_path=relative_path, path=module_path
                            )
                        elif to_git:
                            git_pattern = "git::{git_repo}//{path}?ref={branch}"
                            new_path = git_pattern.format(
                                git_repo=git_repo, path=module_path, branch=branch
                            )
                        print(f"{current_path} \n\t\t\t>> {new_path}")
                        new_line = f'  source = "{new_path}"'
                new_lines.append(new_line)
            new_file_text = "\n".join(new_lines)
            if dry_run:
                print(f"\n\n------------\n-- {tf_file}\n------------")
                print(new_file_text)
            else:
                io.create_text_file(tf_file, new_file_text)
    if not dry_run:
        jobs.run_command("terraform fmt -recursive", dir_to_update)


def main():
    fire.Fire(
        {
            "install": install,
            "init": init,
            "apply": apply,
            "init+apply": init_and_apply,
            "deploy": init_and_apply,
            "change_upstream_source": change_upstream_source,
        }
    )


if __name__ == "__main__":
    main()

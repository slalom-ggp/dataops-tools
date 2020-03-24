#!/usr/bin/env python3
from joblib import Parallel, delayed
import os
import sys
from pathlib import Path
from typing import Dict, List
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

SPECIAL_CASE_WORDS = ["AWS", "ECR", "ECS", "IAM", "VPC", "DBT", "EC2", "RDS", "MySQL"]


def _proper(str: str, title_case=True, special_case_words=None):
    """
    Return the same string in proper case, respected override rules for
    acronyms and special-cased words.
    """
    special_case_words = special_case_words or SPECIAL_CASE_WORDS
    word_lookup = {w.lower(): w for w in special_case_words}
    if title_case:
        str = str.title()
    words = str.split(" ")
    new_words = []
    for word in words:
        new_subwords = []
        for subword in word.split("-"):
            new_subwords.append(word_lookup.get(subword.lower(), subword))
        new_word = "-".join(new_subwords)
        new_words.append(new_word)
    return " ".join(new_words)


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


DOCS_HEADER = """
# {module_title}

`{module_path}`

## Overview


"""


# TODO: inject into footer:
# ## Import Template

# Copy-paste the below to get started with this module in your own project:

# ```hcl
# module "{clean_name}" {
#     source = "git::{git_repo}/{module_path}?ref=master"

#     // ...
# }
# ```
DOCS_FOOTER = """
---------------------

## Source Files

_Source code for this module is available using the links below._

{src}

---------------------

_**NOTE:** This documentation was auto-generated using
`terraform-docs` and `s-infra` from `slalom.dataops`.
Please do not attempt to manually update this file._
"""


def update_module_docs(
    tf_dir: str,
    *,
    recursive: bool = True,
    readme: str = "README.md",
    footer: bool = True,
    header: bool = True,
    special_case_words: List[str] = None,
    extra_docs_names: List[str] = ["USAGE.md", "NOTES.md"],
    git_repo: str = "https://github.com/slalom-ggp/dataops-infra",
):
    """
    Replace all README.md files with auto-generated documentation, a wrapper
    around the `terraform-docs` tool.

    Parameters:
    ----------
    tf_dir: Directory of terraform scripts to document.
    recursive : Optional (default=True). 'True' to run on all subdirectories, recursively.
    readme : Optional (default="README.md"). The filename to create when generating docs.
    footnote: Optional (default=True). 'True' to include the standard footnote.
    special_case_words: Optional. A list of words to override special casing rules.
    extra_docs_names: (Optional.) A list of filenames which, if found, will be appended
      to each module's README.md file.
    git_repo: Optional. The git repo path to use in rendering 'source' paths.

    Returns:
    -------
    None
    """
    markdown_text = ""
    if ".git" not in tf_dir and ".terraform" not in tf_dir:
        tf_files = [x for x in io.list_files(tf_dir) if x.endswith(".tf")]
        extra_docs = [
            x
            for x in io.list_files(tf_dir)
            if extra_docs_names and os.path.basename(x) in extra_docs_names
        ]
        if tf_files:
            module_title = _proper(
                os.path.basename(tf_dir), special_case_words=special_case_words
            )
            parent_dir_name = os.path.basename(Path(tf_dir).parent)
            if parent_dir_name != ".":
                module_title = _proper(
                    f"{parent_dir_name} {module_title}",
                    special_case_words=special_case_words,
                )
            module_path = tf_dir.replace(".", "").replace("//", "/").replace("\\", "/")
            _, markdown_output = jobs.run_command(
                f"terraform-docs md --no-providers --sort-by-required {tf_dir}",
                echo=False,
            )
            if header:
                markdown_text += DOCS_HEADER.format(
                    module_title=module_title, module_path=module_path
                )
            markdown_text += markdown_output
            for extra_file in extra_docs:
                markdown_text += io.get_text_file_contents(extra_file) + "\n"
            if footer:
                markdown_text += DOCS_FOOTER.format(
                    src="\n".join(
                        [
                            "* [{f}]({f})".format(f=os.path.basename(tf_file))
                            for tf_file in tf_files
                        ]
                    )
                )
            io.create_text_file(f"{tf_dir}/{readme}", markdown_text)
    if recursive:
        for folder in io.list_files(tf_dir):
            if os.path.isdir(folder):
                update_module_docs(folder, recursive=recursive, readme=readme)


def get_tf_metadata(
    tf_dir: str, recursive: bool = False,
):
    """
    Return a dictionary of Terraform module paths to JSON metadata about each module,
    a wrapper around the `terraform-docs` tool.

    Parameters:
    ----------
    tf_dir: Directory of terraform scripts to scan.
    recursive : Optional (default=True). 'True' to run on all subdirectories, recursively.

    Returns:
    -------
    dict
    """
    import json

    result = {}
    if (
        ".git" not in tf_dir
        and ".terraform" not in tf_dir
        and "samples" not in tf_dir
        and "tests" not in tf_dir
    ):
        if [x for x in io.list_files(tf_dir) if x.endswith(".tf")]:
            _, json_text = jobs.run_command(f"terraform-docs json {tf_dir}", echo=False)
            result[tf_dir] = json.loads(json_text)
    if recursive:
        for folder in io.list_files(tf_dir):
            folder = folder.replace("\\", "/")
            if os.path.isdir(folder):
                result.update(get_tf_metadata(folder, recursive=recursive))
    return result


def check_tf_metadata(
    tf_dir,
    recursive: bool = True,
    check_module_headers: bool = True,
    check_input_descriptions: bool = True,
    check_output_descriptions: bool = True,
    required_input_vars: list = ["name_prefix", "resource_tags", "environment"],
    required_output_vars: list = ["summary"],
    raise_error=True,
    abspath=False,
):
    """
    Return a dictionary of reference paths to error messages and a dictionary
    of errors to reference paths.
    """

    def _log_issue(module_path, issue_desc, details_list):
        if details_list:
            if issue_desc in error_locations:
                error_locations[issue_desc].extend(details_list)
            else:
                error_locations[issue_desc] = details_list

    error_locations: Dict[str, List[str]] = {}
    with logged_block("checking Terraform modules against repository code standards"):
        modules_metadata = get_tf_metadata(tf_dir, recursive=recursive)
        for module_path, metadata in modules_metadata.items():
            if abspath:
                path_sep = os.path.sep
                module_path = os.path.abspath(module_path)
                module_path = module_path.replace("\\", path_sep).replace("/", path_sep)
            else:
                path_sep = "/"
            if check_module_headers and not metadata["header"]:
                _log_issue(
                    module_path,
                    "1. Blank module headers",
                    [f"{module_path}{path_sep}main.tf"],
                )
            if required_input_vars:
                issue_details = [
                    f"{module_path}{path_sep}variables.tf:var.{required_input}"
                    for required_input in required_input_vars
                    if required_input
                    not in [var["name"] for var in metadata.get("inputs", {})]
                ]
                _log_issue(
                    module_path, "2. Missing required input variables", issue_details
                )
            if required_output_vars:
                issue_details = [
                    f"{module_path}{path_sep}outputs.tf:output.{required_output}"
                    for required_output in required_output_vars
                    if required_output
                    not in [var["name"] for var in metadata.get("outputs", {})]
                ]
                _log_issue(
                    module_path, "3. Missing required output variables", issue_details
                )
            if check_input_descriptions:
                issue_details = [
                    f"{module_path}{path_sep}variables.tf:var.{var['name']}"
                    for var in metadata.get("inputs", {})
                    if not var.get("description")
                ]
                _log_issue(
                    module_path, "4. Missing input variable descriptions", issue_details
                )
            if check_output_descriptions:
                issue_details = [
                    f"{module_path}{path_sep}outputs.tf:output.{var['name']}"
                    for var in metadata.get("outputs", {})
                    if not var.get("description")
                ]
                _log_issue(
                    module_path, "5. Missing output variable descriptions", issue_details
                )
    result_str = "\n".join(
        [
            f"\n{k}:\n    - [ ] " + ("\n    - [ ] ".join(error_locations[k]))
            for k in sorted(error_locations.keys())
        ]
    )
    if raise_error and error_locations:
        raise ValueError(f"One or more validation errors occurred.\n{result_str}")
    return result_str


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
            "update_module_docs": update_module_docs,
            "get_tf_metadata": get_tf_metadata,
            "check_tf_metadata": check_tf_metadata,
        }
    )


if __name__ == "__main__":
    main()

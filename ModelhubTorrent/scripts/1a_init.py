"""
Initialize by downloading all repos from modelhub.ai
Environment variables that affect how this script runs:
    MHTORRENT_USE_LOCAL_MODEL_INDEX: if set, the script will not fetch the main model index and use the one saved locally
    MHTORRENT_SKIP_CLONE: if set, the script will not clone any github repository (assumes repos have been downloaded)
    MHTORRENT_SKIP_DOWNLOAD: if set, the script will not download externally hosted models such as those hosted through GitHub releases

    so if you already have downloaded all the models and cloned the repos, you could run the script like this:
    `$ MHTORRENT_USE_LOCAL_MODEL_INDEX=1  MHTORRENT_SKIP_CLONE=1 MHTORRENT_SKIP_DOWNLOAD=1 ./run.bash`
    

"""
import subprocess
from concurrent.futures import ThreadPoolExecutor
from os import chdir, environ
from pathlib import Path
from typing import Dict, List, Literal
from json import loads, dumps
import requests
from model import Model
from util import handle_errors


curr: Path
repos_dir: Path
TModelResponse = Dict[
    Literal["id", "name", "task_extended", "github", "github_branch", "backend"],
    str,
]

MODEL_JSON_URL = (
    "https://raw.githubusercontent.com/modelhub-ai/modelhub/master/models.json"
)

headers = {"User-Agent": "MHTorrent - python/requests"}


def get_model_index() -> List[TModelResponse]:
    """
    get the main models.json file from modelhub repo.
    this approach is okay to use as modelhub official repositories
    seem to be using this approach to get the model index
    https://github.com/modelhub-ai/unet-2d/blob/master/init/start.py#L203

    """
    resp = requests.get(MODEL_JSON_URL, headers=headers, timeout=60)
    (json_dir / "models.json").write_bytes(resp.content)
    return resp.json()


def subprocess_run(arg_list):
    """
    wrap subprocess.arg and show the command being executed
    """
    print("$", " ".join(arg_list))
    return subprocess.run(arg_list, check=True)


def download_file(url: str, dest: Path):
    """
    wrap wget or maybe implement a requests based streaming downlaod
    """
    # strategy = "wget"  # or requests
    # # if strategy == "wget":
    args = ["wget", url, "-O", str(dest)]

    print(subprocess_run(args).returncode)

    # todo requests?


@handle_errors
def clone_repo(model_meta: TModelResponse):
    """Clone repo, make sure name matches the json response"""
    github_repo = model_meta["github"]
    name = model_meta["name"]
    # github_branch = model_meta["github_branch"]
    # bare_repo_path = repo_dir / name
    # do a shallow clone instead of a bare clone
    # restoring and dealing with lfs is not a concern for our PTM

    # skip cloning repos?
    if not environ.get("MHTORRENT_SKIP_CLONE"):
        subprocess_run(["git", "clone", "--depth=1", github_repo, f"{name}"])
    repo_root = repos_dir / name
    init_file = repo_root / "init/init.json"
    data = loads(init_file.read_text())
    if data.get("external_contrib_files"):
        for external_files in data["external_contrib_files"]:
            src: str = external_files["src_url"]
            # some init.json files have completely broken urls (they use them as comments instead)
            # which is not great
            # so we have to check for this
            if not src.startswith("http"):
                continue
            dest: str = external_files["dest_file_path"]
            # make sure pathlib doesn't end up giving us a `/contrib_src` path
            if dest.startswith("/"):
                dest = dest[1:]
            realpath = repo_root / dest
            if environ.get("MHTORRENT_SKIP_DOWNLOAD"):
                print("skipping download")
            else:
                print(f"downloading {src} to {realpath}")
                download_file(src, realpath)
    config = loads((repos_dir / name / "contrib_src/model/config.json").read_text())
    model_metadata_dir = json_dir / name
    model_metadata_dir.mkdir(exist_ok=True)
    general_model_metadata_path = model_metadata_dir / "model.json"
    mh_metadata_path = model_metadata_dir / "modelhub.json"

    model = Model(config, mh_metadata_path.relative_to(model_metadata_dir), github_repo)
    general_model_metadata_path.write_text(dumps(model.as_json))
    mh_metadata_path.write_text(dumps(config))


def safe_dir(where: str):
    """
    like mkdir p
    """
    res = curr / where
    res.mkdir(exist_ok=True)
    return res


def create_model_repos():
    """go through each model and clone the repo"""
    models_file = json_dir / "models.json"

    if environ.get("MHTORRENT_USE_LOCAL_MODEL_INDEX"):
        models = loads(models_file.read_text())
    else:
        models = get_model_index()
    chdir(repos_dir)
    # clone the models in a threadpool
    # workers could be configurable but 5 seems to be able to finish the job quickly
    exc = ThreadPoolExecutor(max_workers=5)
    for model_meta in models:
        exc.submit(clone_repo, model_meta)

    chdir(curr)


if __name__ == "__main__":
    curr = Path()
    repos_dir = safe_dir("../repos")
    json_dir = safe_dir("../json")
    create_model_repos()

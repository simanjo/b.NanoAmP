import os

import conda.cli.python_api as conda_api
import dearpygui.dearpygui as dpg
from packaging import version

from PipelineSteps import DuplexStep, FilterStep, AssemblyStep
from PipelineSteps import RaconPolishingStep, MedakaPolishingStep
from PipelineSteps import CleanDuplexStep, CleanFilterStep
from PipelineSteps import CleanAssemblyStep, FinalCleanStep
from ErrorWindow import ErrorWindow
import model


def execute_pipeline():
    if not _preflight_check():
        return
    steps, folder_iter = _setup_pipeline()
    for folder in folder_iter:
        print(f"Executing in {folder}")
        for step in steps:
            step.run(folder)


def _preflight_check():
    bcfolder = dpg.get_value("bcfolder")
    if not os.path.isdir(bcfolder):
        msg = "Please specify a valid folder location."
        msg += f"\nThe given folder '{bcfolder}' does not exist."
        ErrorWindow(msg)
        return False
    return True


def _use_folder(path):
    if not path.is_dir() or not _has_fastq(path):
        return False
    # safeguard against rerun from unclean environment
    # we do not want to recurse deeper in original folder
    if path.name.startswith("original"):
        return False
    if dpg.get_value("skip_unclassified"):
        return not path.name.startswith("unclassified")
    return True


def _is_fastq(name):
    return (name.endswith(".fastq")
            or name.endswith(".fastq.gz"))


def _has_fastq(path):
    for entry in os.scandir(path):
        if (entry.is_file() and _is_fastq(entry.name)):
            return True


def _setup_pipeline():
    bcfolder = dpg.get_value("bcfolder")
    print(f"Working on files in {bcfolder}")

    def folder_iter():
        yield from (entry.path for entry in os.scandir(bcfolder)
                    if _use_folder(entry))
        yield from (_ for _ in [bcfolder] if _has_fastq(_))

    threads = dpg.get_value("threads")
    keep_intermediate = dpg.get_value("keep_intermediate")
    genome_size = dpg.get_value("genome_size")
    coverage = dpg.get_value("coverage")
    min_len = dpg.get_value("filtlong_minlen")
    bases = int(genome_size * 1_000_000 * coverage)
    medaka_mod = dpg.get_value("medaka_manumodel")
    is_racon = not dpg.get_value("racon_skip")

    steps = []
    steps.append(DuplexStep(threads))
    steps.append(FilterStep(min_len, bases))
    if not keep_intermediate:
        steps.append(CleanDuplexStep())

    for assembler in model.get_assemblers():
        if dpg.get_value(f"use_{assembler}"):
            steps.append(AssemblyStep(threads, assembler))

            if assembler == "Flye" and is_racon:
                steps.append(RaconPolishingStep(threads))

            steps.append(
                MedakaPolishingStep(threads, assembler, medaka_mod, is_racon)
            )
            if not keep_intermediate:
                steps.append(CleanAssemblyStep(assembler, is_racon))
    if not keep_intermediate:
        steps.append(CleanFilterStep())
        steps.append(FinalCleanStep())
    return steps, folder_iter()


#################### Conda Setup ####################


def set_conda_envs(envs, prefs):
    prefixes = {
        pkg: os.path.join(pref, "bin") for pkg, (pref, _) in prefs.items()
    }
    model.PREFIXES = prefixes


def init_conda_envs():
    for name, yml in model.get_conda_ymls():
        stdout, stderr, ret = conda_api.run_command(
            conda_api.Commands.CREATE, "-n", name
        )
        if ret != 0:
            raise OSError(ret, stderr)
        print(stdout)
        stdout, stderr, ret = conda_api.run_command(
            conda_api.Commands.INSTALL, "-n", name, "--file", yml,
            "--channel", "bioconda", "--channel", "conda-forge", "--yes"
        )
        if ret != 0:
            raise OSError(ret, stderr)
        print(stdout)


def check_pkgs(envs):
    missing = []
    available = [pkg for pkgs in envs.values() for pkg in pkgs]
    for pkg_name in model.BINARIES:
        if pkg_name not in available:
            missing.append(pkg_name)
    status = "complete" if not missing else "incomplete"
    return status, missing


def get_conda_setup():
    prefs = {}
    envs = {}
    for env_name, pref in _get_conda_envs():
        if env_name == "":
            continue
        pkgs_in_env = []
        for pkg_name, ver in _get_conda_packages(env_name):
            if pkg_name in model.BINARIES:
                pkgs_in_env.append(pkg_name)
                if (
                    not (
                        pkg_name in prefs.keys()
                        and (version.parse(prefs[pkg_name][1])
                             > version.parse(ver))
                    ) or env_name.startswith("nanoamp_")
                ):
                    prefs[pkg_name] = (pref, ver)
        if pkgs_in_env:
            envs[env_name] = pkgs_in_env
    return envs, prefs


def _get_conda_envs():
    stdout, stderr, ret = conda_api.run_command(
        conda_api.Commands.INFO, "--envs"
    )
    if ret != 0:
        raise OSError(ret, stderr)
    return [
        (
            env.split()[0] if len(env.split()) > 1 else "",
            env.split()[-1]
        )
        for env in stdout.splitlines()[2:-1]
    ]


def _get_conda_packages(env):
    stdout, stderr, ret = conda_api.run_command(
        conda_api.Commands.LIST,
        ["-n", env]
    )
    if ret != 0:
        raise OSError(ret, stderr)
    return [(i.split()[0], i.split()[1]) for i in stdout.splitlines()[3:]]

################## model selection


def filter_models(device=None, cell=None, guppy=None, variant=None):
    all_models = model.get_models()

    def _filter(mod):
        if cell is not None and mod.split("_")[0] != cell:
            return False
        if device is not None and mod.split("_")[1] != device:
            return False
        if guppy is not None and (
            mod.split("_")[-1] != guppy or (
                mod.split("_")[-1] == 'rle' and mod.split("_")[-2] != guppy
            )
        ):
            return False
        if variant is not None:
            mod_split = mod.split("_")
            start = 1 if mod_split[1] not in ["min", "prom"] else 2
            end = -1 if mod_split[-1].startswith("g") else -2
            return "_".join(mod_split[start:end]) == variant
        return True

    return [mod for mod in all_models if _filter(mod)]

def filter_settings(models, setting):
    if setting == "medaka_device":
        return filter_devices(models)
    if setting == "medaka_cell":
        return filter_cells(models)
    if setting == "medaka_guppy":
        return filter_guppy(models)
    if setting == "medaka_variants":
        return filter_variants(models)


def filter_devices(models):
    devs = ["prom", "min"]
    avail = [mod.split("_")[1] for mod in models if mod.split("_")[1] in devs]
    return ["--"] + list(set(avail))


def filter_cells(models):
    return ["--"] + list(set([mod.split("_")[0] for mod in models]))


def filter_guppy(models):
    avail = [
        mod.split("_")[-1] if mod.split("_")[-1].startswith("g")
        else mod.split("_")[-2] for mod in models
    ]
    return ["--"] + list(set(avail))


def filter_variants(models):
    avail = [
        "_".join(
            mod.split("_")[1:-1] if mod.split("_")[1] not in ["min", "prom"]
            else mod.split("_")[2:-1] if mod.split("_")[-1].startswith("g")
            else mod.split("_")[2:-2]
        ) for mod in models
    ]
    return ["--"] + list(set(avail))

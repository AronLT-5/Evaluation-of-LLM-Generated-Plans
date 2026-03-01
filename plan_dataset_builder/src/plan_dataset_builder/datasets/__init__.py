from __future__ import annotations

from pathlib import Path

from plan_dataset_builder.config import AppConfig
from plan_dataset_builder.datasets.base import DatasetLoader
from plan_dataset_builder.datasets.humaneval import HumanEvalLoader
from plan_dataset_builder.datasets.refactorbench_py import RefactorBenchPyLoader
from plan_dataset_builder.datasets.swebench_verified import SWEBenchVerifiedLoader


def get_enabled_loaders(config: AppConfig, config_dir: Path) -> list[DatasetLoader]:
    loaders: list[DatasetLoader] = []
    if config.datasets.humaneval.enabled:
        loaders.append(HumanEvalLoader())
    if config.datasets.swebench_verified.enabled:
        loaders.append(SWEBenchVerifiedLoader(config_dir=config_dir))
    if config.datasets.refactorbench_py.enabled:
        loaders.append(RefactorBenchPyLoader(config_dir=config_dir))
    return loaders

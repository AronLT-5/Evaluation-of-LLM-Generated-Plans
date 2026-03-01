from __future__ import annotations

from pathlib import Path

import typer

from plan_dataset_builder.config import write_sample_config
from plan_dataset_builder.readable_export import export_failed_run_readable, export_run_readable
from plan_dataset_builder.run_builder import execute_run
from plan_dataset_builder.run_validation import validate_run_dir
from plan_dataset_builder.sectioning import merge_sections, prepare_sections

app = typer.Typer(add_completion=False, no_args_is_help=True)


def _has_failed_plan_artifacts(run_dir: Path) -> bool:
    failed_root = run_dir / "failed_plans" / "datasets"
    if not failed_root.exists():
        return False
    for plans_path in failed_root.glob("*/plans.jsonl"):
        if plans_path.exists() and plans_path.stat().st_size > 0:
            return True
    return False


@app.command("init-config")
def init_config(path: Path) -> None:
    """Write a sample YAML config file."""
    write_sample_config(path)
    typer.echo(f"Wrote sample config to {path}")


@app.command("dry-run")
def dry_run(config: Path = typer.Option(..., "--config", exists=True, dir_okay=False, readable=True)) -> None:
    """Load datasets and write task/manifests, without API calls."""
    run_dir = execute_run(
        config_path=config,
        run_id_override=None,
        resume_override=None,
        dry_run=True,
    )
    typer.echo(f"Dry run complete: {run_dir}")


@app.command("run")
def run(
    config: Path = typer.Option(..., "--config", exists=True, dir_okay=False, readable=True),
    run_id: str | None = typer.Option(None, "--run-id"),
    resume: bool | None = typer.Option(None, "--resume/--no-resume"),
) -> None:
    """Execute plan generation run."""
    run_dir = execute_run(
        config_path=config,
        run_id_override=run_id,
        resume_override=resume,
        dry_run=False,
    )
    typer.echo(f"Run complete: {run_dir}")

    try:
        summary = export_run_readable(run_dir=run_dir)
        typer.echo(f"Readable export written to: {summary['output_dir']}")
        typer.echo(f"Readable index: {summary['index_path']}")
    except Exception as exc:
        typer.echo(f"Warning: readable export failed: {exc}", err=True)

    if _has_failed_plan_artifacts(run_dir):
        try:
            failed_summary = export_failed_run_readable(run_dir=run_dir)
            typer.echo(f"Failed readable export written to: {failed_summary['output_dir']}")
            typer.echo(f"Failed readable index: {failed_summary['index_path']}")
        except Exception as exc:
            typer.echo(f"Warning: failed-plan readable export failed: {exc}", err=True)


@app.command("prepare-sections")
def prepare_sections_cmd(
    config: Path = typer.Option(..., "--config", exists=True, dir_okay=False, readable=True),
    section_size: int = typer.Option(25, "--section-size", min=1),
    sections: int = typer.Option(4, "--sections", min=1),
    output_dir: Path = typer.Option(Path("section_runs"), "--output-dir"),
    run_prefix: str = typer.Option("full_system", "--run-prefix"),
) -> None:
    """Prepare deterministic section configs + allowlists for manual-gated sectioned runs."""
    summary = prepare_sections(
        config_path=config,
        section_size=section_size,
        sections=sections,
        output_dir=output_dir,
        run_prefix=run_prefix,
    )
    typer.echo(f"Sections prepared under: {summary['output_dir']}")
    typer.echo(f"Sections manifest: {summary['sections_manifest_path']}")
    for section in summary["sections"]:
        typer.echo(
            f"- s{section['section']:02d}: "
            f"{section['datasets']['swebench_verified']['task_count']} swebench + "
            f"{section['datasets']['refactorbench_py']['task_count']} refactorbench | "
            f"config={section['section_config_path']}"
        )


@app.command("merge-sections")
def merge_sections_cmd(
    section_run: list[str] = typer.Option(..., "--section-run"),
    output_run_id: str = typer.Option(..., "--output-run-id"),
) -> None:
    """Merge 4 approved section runs into one consolidated artifact run directory."""

    parsed: dict[str, Path] = {}
    for item in section_run:
        if "=" not in item:
            raise typer.BadParameter(
                f"Invalid --section-run '{item}'. Expected format 'sN=path' (e.g., s1=runs/full_s01_v1)."
            )
        key, value = item.split("=", 1)
        key = key.strip().lower()
        value = value.strip()
        if not key or not value:
            raise typer.BadParameter(
                f"Invalid --section-run '{item}'. Expected non-empty 'sN=path' pair."
            )
        if key in parsed:
            raise typer.BadParameter(f"Duplicate section key provided: {key}")
        parsed[key] = Path(value)

    summary = merge_sections(section_runs=parsed, output_run_id=output_run_id)
    typer.echo(f"Merged output run directory: {summary['output_run_dir']}")
    typer.echo(f"Merge info: {summary['merge_info_path']}")
    for dataset, counts in summary["counts"].items():
        typer.echo(
            f"- {dataset}: tasks={counts['tasks']}, plans={counts['plans']}, "
            f"complete={counts['complete_tasks']}, incomplete={counts['incomplete_tasks']}"
        )


@app.command("validate-run")
def validate_run(run_dir: Path) -> None:
    """Validate run outputs and core invariants."""
    errors = validate_run_dir(run_dir)
    if errors:
        typer.echo("Run validation failed:")
        for error in errors:
            typer.echo(f"- {error}")
        raise typer.Exit(code=1)
    typer.echo(f"Run validation passed: {run_dir}")


@app.command("render-readable")
def render_readable(
    run_dir: Path = typer.Option(..., "--run-dir", exists=True, file_okay=False, readable=True),
    output_dir: Path | None = typer.Option(None, "--output-dir"),
    include_task_text: bool = typer.Option(True, "--include-task-text/--no-task-text"),
    max_task_text_chars: int = typer.Option(6000, "--max-task-text-chars"),
) -> None:
    """Convert plans JSONL for a run into human-readable Markdown files."""
    summary = export_run_readable(
        run_dir=run_dir,
        output_dir=output_dir,
        include_task_text=include_task_text,
        max_task_text_chars=max_task_text_chars,
    )
    typer.echo(f"Readable export written to: {summary['output_dir']}")
    typer.echo(f"Index: {summary['index_path']}")
    typer.echo(f"Tasks: {summary['tasks_written']} | Plans: {summary['plans_written']}")

    if _has_failed_plan_artifacts(run_dir):
        failed_output_dir = (output_dir / "failed_plans") if output_dir is not None else None
        failed_summary = export_failed_run_readable(
            run_dir=run_dir,
            output_dir=failed_output_dir,
            include_task_text=include_task_text,
            max_task_text_chars=max_task_text_chars,
        )
        typer.echo(f"Failed readable export written to: {failed_summary['output_dir']}")
        typer.echo(f"Failed index: {failed_summary['index_path']}")
        typer.echo(
            "Failed tasks: "
            f"{failed_summary['tasks_written']} | Failed attempts: {failed_summary['failed_attempts_written']}"
        )


def main() -> None:
    app()


if __name__ == "__main__":
    main()

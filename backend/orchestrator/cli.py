"""CLI 진입점 — Typer 서브커맨드."""

from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

app = typer.Typer(
    name="spine-sim",
    help="CT/MRI → 자동 척추 시뮬레이션 파이프라인",
    no_args_is_help=True,
)

console = Console()


def _make_progress_callback(progress: Progress, task_id):
    """Rich Progress 콜백 생성."""
    def callback(stage: str, details: dict):
        msg = details.get("message", "")
        progress.update(task_id, description=f"[cyan]{stage}[/] {msg}")
    return callback


@app.command()
def segment(
    input_path: Path = typer.Argument(..., help="입력 NIfTI 파일 경로"),
    output_dir: Path = typer.Option("output/segment", "-o", "--output", help="출력 디렉토리"),
    engine: str = typer.Option("totalseg", "--engine", help="세그멘테이션 엔진 (totalseg/totalspineseg/spine_unified)"),
    device: str = typer.Option("gpu", "--device", help="연산 장치 (gpu/cpu)"),
    fast: bool = typer.Option(False, "--fast", help="빠른 모드 (저해상도)"),
    modality: Optional[str] = typer.Option(None, "--modality", help="입력 모달리티 (CT/MRI, spine_unified용)"),
):
    """CT/MRI 자동 세그멘테이션 실행."""
    from .stages.segment import SegmentStage

    stage = SegmentStage(engine=engine, device=device, fast=fast)

    with Progress(SpinnerColumn(), TextColumn("{task.description}"), console=console) as progress:
        task = progress.add_task("[cyan]segment[/] 시작...", total=None)
        result = stage.run(input_path, output_dir, _make_progress_callback(progress, task))

    if result.success:
        console.print(f"[green]완료[/]: {result.output_path} ({result.elapsed_time:.1f}초)")
    else:
        console.print(f"[red]실패[/]: {result.message}")
        raise typer.Exit(1)


@app.command()
def postprocess(
    input_path: Path = typer.Argument(..., help="입력 라벨맵 NIfTI 경로"),
    output_dir: Path = typer.Option("output/postprocess", "-o", "--output", help="출력 디렉토리"),
    min_volume: float = typer.Option(100.0, "--min-volume", help="최소 구성요소 부피 (mm³)"),
    fill_holes: bool = typer.Option(True, "--fill-holes/--no-fill-holes", help="구멍 채우기"),
    smooth_sigma: float = typer.Option(0.5, "--smooth-sigma", help="가우시안 스무딩 시그마"),
):
    """라벨맵 후처리 (형태학적 정리)."""
    from .stages.postprocess import PostprocessStage

    stage = PostprocessStage(
        min_volume_mm3=min_volume,
        fill_holes=fill_holes,
        smooth_sigma=smooth_sigma,
    )

    with Progress(SpinnerColumn(), TextColumn("{task.description}"), console=console) as progress:
        task = progress.add_task("[cyan]postprocess[/] 시작...", total=None)
        result = stage.run(input_path, output_dir, _make_progress_callback(progress, task))

    if result.success:
        console.print(f"[green]완료[/]: {result.output_path} ({result.elapsed_time:.1f}초)")
    else:
        console.print(f"[red]실패[/]: {result.message}")
        raise typer.Exit(1)


@app.command()
def voxelize(
    input_path: Path = typer.Argument(..., help="입력 라벨맵 NIfTI 경로"),
    output_dir: Path = typer.Option("output/voxelize", "-o", "--output", help="출력 디렉토리"),
    resolution: int = typer.Option(64, "--resolution", help="최대 해상도"),
):
    """NIfTI 라벨맵 → NPZ 복셀 모델 변환."""
    from .stages.voxelize import VoxelizeStage

    stage = VoxelizeStage(resolution=resolution)

    with Progress(SpinnerColumn(), TextColumn("{task.description}"), console=console) as progress:
        task = progress.add_task("[cyan]voxelize[/] 시작...", total=None)
        result = stage.run(input_path, output_dir, _make_progress_callback(progress, task))

    if result.success:
        console.print(f"[green]완료[/]: {result.output_path} ({result.elapsed_time:.1f}초)")
    else:
        console.print(f"[red]실패[/]: {result.message}")
        raise typer.Exit(1)


@app.command()
def solve(
    input_path: Path = typer.Argument(..., help="입력 NPZ 복셀 모델 경로"),
    output_dir: Path = typer.Option("output/solve", "-o", "--output", help="출력 디렉토리"),
    method: str = typer.Option("spg", "--method", help="해석 방법 (fem/pd/spg)"),
    max_iterations: int = typer.Option(10000, "--max-iter", help="최대 반복 횟수"),
):
    """FEA 해석 실행."""
    from .stages.solve import SolveStage

    stage = SolveStage(method=method, max_iterations=max_iterations)

    with Progress(SpinnerColumn(), TextColumn("{task.description}"), console=console) as progress:
        task = progress.add_task("[cyan]solve[/] 시작...", total=None)
        result = stage.run(input_path, output_dir, _make_progress_callback(progress, task))

    if result.success:
        console.print(f"[green]완료[/]: {result.output_path} ({result.elapsed_time:.1f}초)")
    else:
        console.print(f"[red]실패[/]: {result.message}")
        raise typer.Exit(1)


@app.command()
def report(
    input_path: Path = typer.Argument(..., help="입력 NPZ 해석 결과 경로"),
    output_dir: Path = typer.Option("output/report", "-o", "--output", help="출력 디렉토리"),
):
    """해석 결과 리포트 생성 (JSON + HTML)."""
    from .stages.report import ReportStage

    stage = ReportStage()

    with Progress(SpinnerColumn(), TextColumn("{task.description}"), console=console) as progress:
        task = progress.add_task("[cyan]report[/] 시작...", total=None)
        result = stage.run(input_path, output_dir, _make_progress_callback(progress, task))

    if result.success:
        console.print(f"[green]완료[/]: {result.output_path} ({result.elapsed_time:.1f}초)")
    else:
        console.print(f"[red]실패[/]: {result.message}")
        raise typer.Exit(1)


@app.command()
def pipeline(
    input_path: Path = typer.Argument(..., help="입력 NIfTI 파일 경로"),
    output_dir: Path = typer.Option("output", "-o", "--output", help="출력 루트 디렉토리"),
    config_path: Optional[Path] = typer.Option(None, "--config", help="설정 파일 경로 (TOML)"),
):
    """전체 파이프라인 실행 (segment → postprocess → voxelize → solve → report)."""
    from .config import PipelineConfig
    from .cache import PipelineCache

    # 설정 로드
    if config_path and config_path.exists():
        cfg = PipelineConfig.from_toml(config_path)
    else:
        cfg = PipelineConfig.default()

    cache = PipelineCache(cfg.cache.cache_dir, cfg.cache.enabled)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # 스테이지 목록 생성
    from .stages.segment import SegmentStage
    from .stages.postprocess import PostprocessStage
    from .stages.voxelize import VoxelizeStage
    from .stages.solve import SolveStage
    from .stages.report import ReportStage

    stages = [
        (SegmentStage(
            engine=cfg.segment.engine,
            device=cfg.segment.device,
            fast=cfg.segment.fast,
            roi_subset=cfg.segment.roi_subset,
        ), output_dir / "segment"),
        (PostprocessStage(
            min_volume_mm3=cfg.postprocess.min_volume_mm3,
            fill_holes=cfg.postprocess.fill_holes,
            smooth_sigma=cfg.postprocess.smooth_sigma,
        ), output_dir / "postprocess"),
        (VoxelizeStage(
            resolution=cfg.voxelize.resolution,
            spacing=cfg.voxelize.spacing,
        ), output_dir / "voxelize"),
        (SolveStage(
            method=cfg.solve.method,
            E=cfg.solve.E,
            nu=cfg.solve.nu,
            density=cfg.solve.density,
            max_iterations=cfg.solve.max_iterations,
            tolerance=cfg.solve.tolerance,
        ), output_dir / "solve"),
        (ReportStage(), output_dir / "report"),
    ]

    current_input = input_path
    total_start = __import__("time").time()

    console.print(f"\n[bold]파이프라인 시작[/]: {input_path}\n")

    for stage_obj, stage_output_dir in stages:
        stage_name = stage_obj.name

        # 캐시 확인
        cache_key = cache.get_key(current_input, stage_name)
        if cache.has(cache_key):
            cached_path = cache.get_path(cache_key)
            console.print(f"  [yellow]캐시[/] {stage_name}: {cached_path}")
            # 캐시된 출력을 다음 스테이지 입력으로 사용
            cached_files = list(cached_path.glob("*"))
            if cached_files:
                current_input = cached_files[0]
            continue

        # 스테이지 실행
        with Progress(SpinnerColumn(), TextColumn("{task.description}"), console=console) as progress:
            task = progress.add_task(f"[cyan]{stage_name}[/] 실행 중...", total=None)
            result = stage_obj.run(current_input, stage_output_dir, _make_progress_callback(progress, task))

        if result.success:
            console.print(f"  [green]완료[/] {stage_name}: {result.message} ({result.elapsed_time:.1f}초)")
            # 캐시 저장
            cache.store(cache_key, [result.output_path], result.elapsed_time)
            current_input = result.output_path
        else:
            console.print(f"  [red]실패[/] {stage_name}: {result.message}")
            if cfg.on_error == "stop":
                console.print("\n[red]파이프라인 중단[/] (on_error=stop)")
                raise typer.Exit(1)
            elif cfg.on_error == "skip":
                console.print(f"  [yellow]스킵[/] {stage_name}")
                continue
            else:
                console.print(f"  [yellow]경고[/] {stage_name}: 계속 진행")
                continue

    total_elapsed = __import__("time").time() - total_start
    console.print(f"\n[bold green]파이프라인 완료[/] ({total_elapsed:.1f}초)")

    # 캐시 정리
    cache.cleanup(cfg.cache.max_size_gb)


@app.command(name="download-model")
def download_model(
    model_name: str = typer.Argument(..., help="모델 이름 (spine_unified)"),
    target_dir: Optional[Path] = typer.Option(None, "--target", help="저장 경로"),
):
    """모델 가중치 다운로드."""
    if model_name == "spine_unified":
        from backend.segmentation.nnunet_spine import SpineUnifiedEngine

        try:
            path = SpineUnifiedEngine.download_model(target_dir)
            console.print(f"[green]완료[/]: 모델 저장됨 → {path}")
        except RuntimeError as e:
            console.print(f"[red]실패[/]: {e}")
            raise typer.Exit(1)
    else:
        console.print(f"[red]알 수 없는 모델[/]: {model_name}")
        console.print("사용 가능한 모델: spine_unified")
        raise typer.Exit(1)


@app.command(name="validate-data")
def validate_data(
    verse_dir: Optional[Path] = typer.Option(None, "--verse", help="VerSe2020 경로"),
    ctspine_dir: Optional[Path] = typer.Option(None, "--ctspine", help="CTSpine1K 경로"),
    spider_dir: Optional[Path] = typer.Option(None, "--spider", help="SPIDER 경로"),
):
    """학습 데이터셋 검증."""
    from backend.segmentation.training.config import DatasetPaths
    from backend.segmentation.training.download import validate_all, print_validation_report

    paths = DatasetPaths()
    if verse_dir:
        paths.verse2020 = verse_dir
    if ctspine_dir:
        paths.ctspine1k = ctspine_dir
    if spider_dir:
        paths.spider = spider_dir

    results = validate_all(paths)
    print_validation_report(results)


@app.command(name="prepare-training-data")
def prepare_training_data(
    data_dir: Path = typer.Argument(..., help="데이터셋 루트 디렉토리"),
    output_dir: Path = typer.Option("nnUNet_raw", "-o", "--output", help="nnU-Net 출력 디렉토리"),
    dataset_id: int = typer.Option(200, "--dataset-id", help="nnU-Net 데이터셋 ID"),
    pseudo_labels: bool = typer.Option(False, "--pseudo-labels/--no-pseudo-labels", help="Pseudo-label 사용 여부"),
    continue_on_error: bool = typer.Option(True, "--continue/--stop-on-error", help="실패 시 계속 여부"),
    dry_run: bool = typer.Option(False, "--dry-run", help="검증만 실행 (변환 안 함)"),
    skip_existing: bool = typer.Option(True, "--skip-existing/--overwrite", help="기존 케이스 스킵"),
):
    """학습 데이터 → nnU-Net 형식 변환.

    data_dir 아래에 VerSe2020/, CTSpine1K/, SPIDER/ 서브디렉토리가 있어야 합니다.
    """
    from backend.segmentation.training.config import DatasetPaths, TrainingPipelineConfig, NnunetConfig
    from backend.segmentation.training.download import validate_all, print_validation_report
    from backend.segmentation.training.dataset_crawl import crawl_all

    paths = DatasetPaths(
        verse2020=data_dir / "VerSe2020",
        ctspine1k=data_dir / "CTSpine1K",
        spider=data_dir / "SPIDER",
    )

    # 데이터셋 검증
    console.print("\n[bold]데이터셋 검증 중...[/]")
    results = validate_all(paths)
    print_validation_report(results)

    valid_datasets = [r for r in results if r.is_valid]
    if not valid_datasets:
        console.print("[red]유효한 데이터셋이 없습니다.[/]")
        raise typer.Exit(1)

    # 케이스 수 확인
    all_cases = crawl_all(paths)
    console.print(f"\n[green]{len(valid_datasets)}개 데이터셋, {len(all_cases)}개 케이스 발견.[/]")

    if dry_run:
        console.print("\n[yellow]--dry-run 모드: 검증만 완료, 변환 미실행[/]")
        for case in all_cases[:10]:
            console.print(f"  {case.case_id} ({case.modality}) — {case.image_path.name}")
        if len(all_cases) > 10:
            console.print(f"  ... 외 {len(all_cases) - 10}건")
        return

    # 파이프라인 설정
    config = TrainingPipelineConfig(
        datasets=paths,
        nnunet=NnunetConfig(dataset_id=dataset_id, output_dir=output_dir),
    )

    # 변환 실행
    from backend.segmentation.training.run_pipeline import run_training_pipeline

    with Progress(
        SpinnerColumn(),
        TextColumn("{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("[cyan]prepare[/] 시작...", total=None)

        def progress_cb(stage: str, details: dict):
            msg = details.get("message", "")
            progress.update(task, description=f"[cyan]{stage}[/] {msg}")

        pipeline_result = run_training_pipeline(
            config,
            progress_callback=progress_cb,
            use_pseudo_labels=pseudo_labels,
            continue_on_error=continue_on_error,
            skip_existing=skip_existing,
        )

    console.print(f"\n[bold]{pipeline_result.summary}[/]")

    # 실패 케이스 출력
    failed = [r for r in pipeline_result.case_results if not r.success]
    if failed:
        console.print(f"\n[red]실패 케이스 ({len(failed)}건):[/]")
        for r in failed[:20]:
            console.print(f"  {r.case_id}: {r.message}")

    if pipeline_result.success == 0 and pipeline_result.skipped == 0:
        raise typer.Exit(1)


@app.command()
def train(
    dataset_id: int = typer.Option(200, "--dataset-id", help="nnU-Net 데이터셋 ID"),
    configuration: str = typer.Option("3d_fullres", "--config", "-c", help="학습 설정 (3d_fullres, 2d 등)"),
    folds: Optional[str] = typer.Option(None, "--folds", help="학습 fold (예: 0,1,2 또는 all)"),
    epochs: Optional[int] = typer.Option(None, "--epochs", help="최대 에폭 수"),
    device: str = typer.Option("cuda", "--device", help="연산 장치 (cuda/cpu)"),
    debug: bool = typer.Option(False, "--debug", help="디버그 모드 (5에폭, fold 0)"),
    export: bool = typer.Option(False, "--export", help="학습 후 모델 내보내기"),
    nnunet_raw: Path = typer.Option("nnUNet_raw", "--raw", help="nnU-Net raw 경로"),
    nnunet_preprocessed: Path = typer.Option("nnUNet_preprocessed", "--preprocessed", help="전처리 경로"),
    nnunet_results: Path = typer.Option("nnUNet_results", "--results", help="결과 경로"),
):
    """nnU-Net v2 학습 실행."""
    from backend.segmentation.training.run_train import (
        TrainConfig, run_full_training, export_model,
    )

    # fold 파싱
    fold_list = None
    if folds:
        if folds.lower() == "all":
            fold_list = [0, 1, 2, 3, 4]
        else:
            fold_list = [int(f.strip()) for f in folds.split(",")]

    config = TrainConfig(
        dataset_id=dataset_id,
        configuration=configuration,
        folds=fold_list,
        epochs=epochs,
        device=device,
        debug=debug,
        nnunet_raw=nnunet_raw,
        nnunet_preprocessed=nnunet_preprocessed,
        nnunet_results=nnunet_results,
    )

    console.print(f"\n[bold]nnU-Net 학습 시작[/]")
    console.print(f"  데이터셋: {config.dataset_name}")
    console.print(f"  설정: {config.configuration}")
    console.print(f"  Folds: {config.folds}")
    console.print(f"  에폭: {config.epochs or '기본값(1000)'}")
    console.print(f"  장치: {config.device}")
    if config.debug:
        console.print("  [yellow]디버그 모드[/]")
    console.print()

    success = run_full_training(config)

    if success:
        console.print("\n[bold green]학습 완료![/]")

        if export:
            console.print("\n[cyan]모델 내보내기 중...[/]")
            export_path = export_model(config)
            if export_path:
                console.print(f"[green]모델 내보내기 완료[/]: {export_path}")
            else:
                console.print("[red]모델 내보내기 실패[/]")
                raise typer.Exit(1)
    else:
        console.print("\n[red]학습 실패[/]")
        raise typer.Exit(1)


@app.command()
def server(
    host: str = typer.Option("0.0.0.0", "--host", help="서버 호스트"),
    port: int = typer.Option(8000, "--port", help="서버 포트"),
    reload: bool = typer.Option(False, "--reload", help="자동 리로드 (개발용)"),
):
    """FastAPI 웹 서버 시작."""
    import uvicorn

    console.print(f"[bold]서버 시작[/]: http://{host}:{port}")
    uvicorn.run(
        "backend.api.app:app",
        host=host,
        port=port,
        reload=reload,
    )


if __name__ == "__main__":
    app()

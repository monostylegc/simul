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
        from src.segmentation.nnunet_spine import SpineUnifiedEngine

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
    from src.segmentation.training.config import DatasetPaths
    from src.segmentation.training.download import validate_all, print_validation_report

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
):
    """학습 데이터 → nnU-Net 형식 변환.

    data_dir 아래에 VerSe2020/, CTSpine1K/, SPIDER/ 서브디렉토리가 있어야 합니다.
    """
    from src.segmentation.training.config import DatasetPaths, TrainingPipelineConfig
    from src.segmentation.training.download import validate_all, print_validation_report

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

    console.print(f"\n[green]{len(valid_datasets)}개 데이터셋 발견.[/]")
    console.print(
        "\n[yellow]참고:[/] 전체 변환은 pseudo-label 생성이 포함되어 수 시간 소요됩니다.\n"
        "nnU-Net 학습 데이터 변환은 별도 스크립트로 실행하세요:\n"
        f"  python -m src.segmentation.training.convert_nnunet --data-dir {data_dir} -o {output_dir}\n"
    )


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
        "src.server.app:app",
        host=host,
        port=port,
        reload=reload,
    )


if __name__ == "__main__":
    app()

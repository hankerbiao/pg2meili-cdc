"""Build the installable UniData SDK source ZIP used by the portal."""

from argparse import ArgumentParser
from pathlib import Path
import shutil
import tomllib
from zipfile import ZIP_DEFLATED, ZipFile


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def build_archive(output_dir: Path) -> Path:
    project = tomllib.loads(
        (PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    )
    version = str(project["project"]["version"])
    output_dir.mkdir(parents=True, exist_ok=True)
    output = output_dir / f"unidata-sdk-{version}.zip"
    package_root = PROJECT_ROOT / "src" / "unidata_sdk"

    with ZipFile(output, "w", compression=ZIP_DEFLATED) as archive:
        archive.write(PROJECT_ROOT / "pyproject.toml", "pyproject.toml")
        archive.write(PROJECT_ROOT / "README.md", "README.md")
        for source in sorted(package_root.rglob("*")):
            if (
                source.is_file()
                and "__pycache__" not in source.parts
                and source.suffix != ".pyc"
            ):
                archive.write(source, source.relative_to(PROJECT_ROOT).as_posix())
    shutil.copyfile(output, output_dir / "unidata-sdk.zip")
    return output


def main() -> None:
    parser = ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    print(build_archive(args.output_dir))


if __name__ == "__main__":
    main()

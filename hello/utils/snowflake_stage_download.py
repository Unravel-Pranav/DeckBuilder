from __future__ import annotations

import argparse
import os
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv
import pandas as pd

_BACKEND_DIR = Path(__file__).resolve().parent.parent.parent.parent
_ENV_FILE = _BACKEND_DIR / ".env"
if _ENV_FILE.exists():
    load_dotenv(_ENV_FILE, override=False)

from hello.ml.logger import GLOBAL_LOGGER as logger
from hello.ml.utils.snowflake_connector import SnowflakeConnector

DEFAULT_CSV_PATH = _BACKEND_DIR / "Geo_Image_Lookup_Table_Format.csv"
DEFAULT_DOWNLOAD_DIR = _BACKEND_DIR / "downloaded_images"


def _sql_quote(value: str) -> str:
    """Single-quote a string for Snowflake SQL."""
    return "'" + value.replace("'", "''") + "'"


def _file_uri_for_dir(dir_path: Path) -> str:
    """
    Build a file:// URI to a directory for Snowflake GET.
    """
    dir_path = dir_path.resolve()
    if os.name == "nt":
        return "file://" + dir_path.as_posix().rstrip("/") + "/"
    return dir_path.as_uri().rstrip("/") + "/"


def _resolve_csv_path(csv_path: Path | str | None) -> Path:
    return Path(csv_path) if csv_path else DEFAULT_CSV_PATH


def _resolve_download_dir(download_dir: Path | str | None) -> Path:
    return Path(download_dir) if download_dir else DEFAULT_DOWNLOAD_DIR


def _extract_stage_context(file_url: str) -> tuple[str | None, str | None, str | None]:
    """Extract database, schema, and stage name from a Snowflake file URL."""
    try:
        parts = [part for part in urlparse(file_url).path.split("/") if part]
    except Exception:
        return None, None, None
    if "files" in parts:
        idx = parts.index("files")
        if len(parts) >= idx + 4:
            return parts[idx + 1], parts[idx + 2], parts[idx + 3]
    if len(parts) >= 4:
        return parts[-4], parts[-3], parts[-2]
    return None, None, None


def _qualify_stage_path(
    stage_file: str, stage_database: str | None, stage_schema: str | None
) -> str:
    if not stage_file.startswith("@"):
        return stage_file
    stage_root, *rest = stage_file.split("/", 1)
    if "." in stage_root:
        return stage_file
    if not stage_database or not stage_schema:
        return stage_file
    qualified_root = f"@{stage_database}.{stage_schema}.{stage_root.lstrip('@')}"
    return qualified_root if not rest else f"{qualified_root}/{rest[0]}"


def download_image_by_id(
    image_id: int,
    csv_path: Path | str | None = None,
    download_dir: Path | str | None = None,
    parallel: int = 4,
    remove_existing: bool = True,
    stage_database: str | None = None,
    stage_schema: str | None = None,
) -> Path:
    """
    Download the staged image referenced by IMAGE_URL for the given ID into download_dir.
    Returns the expected local file path.
    """
    csv_path = _resolve_csv_path(csv_path)
    if not csv_path.exists():
        raise FileNotFoundError(f"CSV file not found: {csv_path}")

    df = pd.read_csv(csv_path)
    required_columns = {"ID", "IMAGE_URL", "IMAGE_NAME"}
    missing = required_columns - set(df.columns)
    if missing:
        raise ValueError(f"CSV missing required columns: {sorted(missing)}")

    match = df.loc[df["ID"] == image_id]
    if match.empty:
        match = df.loc[df["ID"].astype(str) == str(image_id)]
    if match.empty:
        raise ValueError(f"ID {image_id} not found in {csv_path}")

    row = match.iloc[0]
    stage_file = str(row["IMAGE_URL"]).strip()
    if not stage_file:
        raise ValueError(f"Missing IMAGE_URL for ID {image_id} in {csv_path}")

    image_name = str(row["IMAGE_NAME"]).strip()
    if not image_name:
        image_name = stage_file.split("/")[-1].lstrip("@")

    file_url = None
    if "FILE_URL" in row:
        raw_file_url = row.get("FILE_URL")
        if raw_file_url is not None and not pd.isna(raw_file_url):
            file_url = str(raw_file_url).strip() or None

    if file_url:
        inferred_db, inferred_schema, _ = _extract_stage_context(file_url)
        stage_database = stage_database or inferred_db
        stage_schema = stage_schema or inferred_schema

    stage_file = _qualify_stage_path(stage_file, stage_database, stage_schema)

    download_dir = _resolve_download_dir(download_dir)
    download_dir.mkdir(parents=True, exist_ok=True)

    local_target = download_dir / image_name
    if remove_existing and local_target.exists():
        local_target.unlink()

    local_dir_uri = _file_uri_for_dir(download_dir)
    parallel = max(1, int(parallel))
    sql = f"GET {_sql_quote(stage_file)} {_sql_quote(local_dir_uri)} PARALLEL = {parallel};"

    connector = SnowflakeConnector(database=stage_database, schema=stage_schema)
    conn = connector.connect()
    try:
        with conn.cursor() as cur:
            logger.info("Downloading Snowflake stage file for image ID %s", image_id)
            cur.execute(sql)
            results = cur.fetchall()
            if results:
                logger.info("Snowflake GET results: %s", results)
    finally:
        connector.disconnect()

    return local_target


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Download a staged image by ID using Snowflake GET."
    )
    parser.add_argument("--image-id", type=int, required=True, help="Image ID to download.")
    parser.add_argument(
        "--csv-path",
        type=Path,
        default=DEFAULT_CSV_PATH,
        help="Path to the image lookup CSV.",
    )
    parser.add_argument(
        "--download-dir",
        type=Path,
        default=DEFAULT_DOWNLOAD_DIR,
        help="Directory to save downloaded images.",
    )
    parser.add_argument(
        "--parallel",
        type=int,
        default=4,
        help="Parallelism for Snowflake GET.",
    )
    parser.add_argument(
        "--stage-database",
        type=str,
        default=None,
        help="Override database for stage resolution.",
    )
    parser.add_argument(
        "--stage-schema",
        type=str,
        default=None,
        help="Override schema for stage resolution.",
    )
    parser.add_argument(
        "--keep-existing",
        action="store_true",
        help="Do not remove an existing local file before download.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    out_path = download_image_by_id(
        image_id=args.image_id,
        csv_path=args.csv_path,
        download_dir=args.download_dir,
        parallel=args.parallel,
        remove_existing=not args.keep_existing,
        stage_database=args.stage_database,
        stage_schema=args.stage_schema,
    )
    print(f"Downloaded to: {out_path}")
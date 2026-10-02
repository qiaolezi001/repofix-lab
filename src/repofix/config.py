"""Environment configuration; credentials never enter task records."""

import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    data_dir: Path = field(default_factory=lambda: Path(".repofix").resolve())
    api_key: str = field(default="", repr=False)
    base_url: str = "https://api.openai.com/v1"
    model: str = ""
    sandbox_image: str = "repofix-sandbox:0.1"
    sandbox_timeout: int = 30

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            data_dir=Path(os.getenv("REPOFIX_DATA_DIR", ".repofix")).resolve(),
            api_key=os.getenv("REPOFIX_API_KEY", os.getenv("OPENAI_API_KEY", "")),
            base_url=os.getenv("REPOFIX_BASE_URL", "https://api.openai.com/v1").rstrip("/"),
            model=os.getenv("REPOFIX_MODEL", ""),
            sandbox_image=os.getenv("REPOFIX_SANDBOX_IMAGE", "repofix-sandbox:0.1"),
            sandbox_timeout=int(os.getenv("REPOFIX_SANDBOX_TIMEOUT", "30")),
        )


def project_root() -> Path:
    """Find a source checkout; installed wheels use packaged demo assets."""
    checkout = Path(__file__).resolve().parents[2]
    if (checkout / "examples" / "demo").is_dir():
        return checkout
    return Path(__file__).resolve().parent


def demo_source() -> Path:
    return project_root() / "examples" / "demo"


DEMO_ISSUE = (
    "The paginate function skips the first item of every page. "
    "Pages are 1-based; page 1 of [10,20,30,40] with page_size=2 must return [10,20]. "
    "Find the off-by-one bug, fix it, and run all public tests."
)

"""Put the `opdi` repository on `sys.path`.

`opdi` is pip-installable, but `benchmarks/track_truth.py` and
`benchmarks/track_score.py` live outside `src/` and are not part of the
installed package. They are the single definition of ground truth and of the
signed offset computation, and copying them here would fork exactly what
`boundary_offsets` was extracted to keep single -- a second implementation
would look entirely plausible while describing a different population, and
nothing in either output would say so.

`OPDI_REPO` overrides the location; the default is a sibling checkout.

**Nothing under `oac.aggregate`, `oac.rank` or `site/` may call this.** Those
render in GitHub Actions, which has no `opdi` checkout and no Spark.
`tests/test_imports.py` enforces it in a clean subprocess.
"""

import os
import sys
from pathlib import Path

DEFAULT_OPDI = Path(__file__).resolve().parents[3] / "opdi"


def opdi_repo() -> Path:
    """The `opdi` checkout this repo reads its shared modules from."""
    return Path(os.environ.get("OPDI_REPO", DEFAULT_OPDI)).resolve()


def bootstrap() -> None:
    """Idempotently place opdi's `src/` and `benchmarks/` on `sys.path`."""
    repo = opdi_repo()
    if not (repo / "src" / "opdi").is_dir():
        raise RuntimeError(
            f"opdi not found at {repo}. Set OPDI_REPO to the checkout that "
            "carries src/opdi and benchmarks/track_truth.py."
        )
    for sub in ("src", "benchmarks"):
        p = str(repo / sub)
        if p not in sys.path:
            sys.path.insert(0, p)

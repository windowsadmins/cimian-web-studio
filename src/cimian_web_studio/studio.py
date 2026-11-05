"""Identity of this studio.

Everything platform-specific about naming lives here, so the rest of the
package can stay identical to its copy in the sibling studio.
"""

from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError, version


@dataclass(frozen=True)
class Studio:
    name: str
    platform: str
    distribution: str
    package: str
    command: str


STUDIO = Studio(
    name="Cimian Web Studio",
    platform="Cimian",
    distribution="cimian-web-studio",
    package="cimian_web_studio",
    command="cwsctl",
)

# Packages from other projects this studio must never import.
FORBIDDEN_IMPORTS = ("fleetmate", "fleetmate_web_admin", "munki_web_studio")

try:
    __version__ = version(STUDIO.distribution)
except PackageNotFoundError:  # pragma: no cover - only when run from an uninstalled tree
    __version__ = "0.0.0"

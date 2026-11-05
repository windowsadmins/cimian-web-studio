"""What a Cimian repository looks like. The only platform-specific part of scanning."""

from pathlib import PureWindowsPath
from typing import Any, cast

from cimian_web_studio import catalogs
from cimian_web_studio.jobs.remote import RemoteSpec

# Top-level folders that hold metadata, and the kind of object each file is.
KINDS = {"pkgsinfo": "pkginfo", "manifests": "manifest", "catalogs": "catalog"}

# Cimian metadata is YAML; other files in these folders are not metadata.
SUFFIXES: frozenset[str] | None = frozenset({".yaml", ".yml"})

IGNORED_NAMES = frozenset({".DS_Store", ".gitkeep", "Thumbs.db"})


# Folders a Cimian client downloads, which publishing copies into a release.
PUBLISHED_FOLDERS = ("catalogs", "manifests", "pkgs", "icons")

# Installer files an import accepts, and the format a new pkginfo is written in.
IMPORT_SUFFIXES = (".msi", ".exe", ".nupkg")
NEW_PKGINFO_SUFFIX = ".yaml"

# Workers. A Windows worker runs these Cimian tools and nothing else, from these paths.
WORKER_PLATFORM = "Windows"
WORKER_TOOLS = {
    "makecatalogs": r"C:\Program Files\Cimian\makecatalogs.exe",
    "makepkginfo": r"C:\Program Files\Cimian\makepkginfo.exe",
}
# How each tool prints its version.
TOOL_VERSION_ARGS: dict[str, tuple[str, ...]] = {
    "makecatalogs": ("-V",),
    "makepkginfo": ("--version",),
}
# Each capability a worker can offer, and the tools it needs.
CAPABILITIES = {
    "catalog.generate": ("makecatalogs",),
    "installer.inspect": ("makepkginfo",),
}
REMOTE_OPERATIONS = (
    RemoteSpec(
        name="catalog.generate",
        title="Generate catalogs",
        capability="catalog.generate",
        tool="makecatalogs",
        # Payloads are not sent to the worker, so their existence is not checked.
        args=("--repo_path", "{staging}", "--skip_payload_check"),
        inputs=("pkgsinfo",),
        outputs="catalogs",
        applies_to="catalogs",
        check=catalogs.check_output,
        arguments=frozenset({"acknowledge_live"}),
    ),
    RemoteSpec(
        name="package.import",
        title="Import a package",
        capability="installer.inspect",
        tool="makepkginfo",
        # makepkginfo reads the installer's metadata and prints a pkginfo; it runs
        # nothing from the installer.
        args=("{upload}",),
        inputs=(),
        outputs="out",
        upload_argument="upload",
        stdout_file="out/pkginfo.yaml",
        creates_draft=True,
        arguments=frozenset({"upload", "subdirectory"}),
        max_attempts=1,
    ),
)


# Manifest sections that name packages, and sections that name other manifests.
ITEM_SECTIONS = (
    "managed_installs",
    "managed_uninstalls",
    "managed_updates",
    "optional_installs",
    "featured_items",
    "default_installs",
    "managed_profiles",
    "managed_apps",
)
INCLUDE_SECTIONS = ("included_manifests",)
# pkginfo keys that name other packages.
DEPENDENCY_KEYS = ("requires", "update_for")
# Installer and uninstaller locations are relative to this folder, as in makecatalogs.
PAYLOAD_FOLDER = "pkgs"


# pkginfo fields the editor may set, and the type each must have. Dotted names
# reach into nested dictionaries. Anything else is edited through raw changes.
PKGINFO_FIELDS: dict[str, str] = {
    "name": "string",
    "display_name": "string",
    "version": "string",
    "description": "text",
    "category": "string",
    "developer": "string",
    "catalogs": "string-list",
    "minimum_os_version": "string",
    "maximum_os_version": "string",
    "supported_architectures": "string-list",
    "unattended_install": "boolean",
    "unattended_uninstall": "boolean",
    "uninstallable": "boolean",
    "restart_action": "string",
    "blocking_applications": "string-list",
    "requires": "string-list",
    "update_for": "string-list",
    "installer.type": "string",
    "installer.location": "string",
    "installer.hash": "string",
    "installer.arguments": "string-list",
    "installcheck_script": "text",
    "uninstallcheck_script": "text",
    "preinstall_script": "text",
    "postinstall_script": "text",
    "preuninstall_script": "text",
    "postuninstall_script": "text",
}


def summarize(kind: str, data: Any) -> dict[str, Any]:
    """The searchable fields of one parsed file, plus what it refers to."""
    if kind == "catalog":
        # A Cimian catalog is a mapping whose `items` holds the entries.
        items = cast(dict[str, Any], data).get("items") if isinstance(data, dict) else None
        return {"items": len(cast(list[Any], items)) if isinstance(items, list) else 0}
    if not isinstance(data, dict):
        return {}
    mapping = cast(dict[str, Any], data)
    summary: dict[str, Any] = {
        "name": _text(mapping.get("name")),
        "version": _text(mapping.get("version")),
        "display_name": _text(mapping.get("display_name")),
        "category": _text(mapping.get("category")),
        "catalogs": _texts(mapping.get("catalogs")),
        "refs": _references(kind, mapping),
        "problems": _problems(kind, mapping),
    }
    if kind == "pkginfo":
        installer = mapping.get("installer")
        installer_map = cast(dict[str, Any], installer) if isinstance(installer, dict) else {}
        location = _text(installer_map.get("location"))
        summary["installer_type"] = _text(installer_map.get("type"))
        summary["payload"] = _payload(location)
        uninstallers = mapping.get("uninstaller")
        extra = [
            _payload(_text(cast(dict[str, Any], u).get("location")))
            for u in (cast(list[Any], uninstallers) if isinstance(uninstallers, list) else [])
            if isinstance(u, dict)
        ]
        summary["payloads"] = [p for p in extra if p]
    return summary


def _payload(location: str | None) -> str | None:
    """Cimian's rule: trim leading slashes, use forward slashes, prefix pkgs/.

    Locations that are Windows paths on the client (`%ProgramFiles%\\...`) are not
    repository payloads.
    """
    if not location or "%" in location or ":" in location:
        return None
    return f"{PAYLOAD_FOLDER}/" + location.lstrip("/\\").replace("\\", "/")


def condition_text(entry: dict[str, Any]) -> str | None:
    """The condition of one conditional item, as text."""
    condition = _text(entry.get("condition"))
    if condition:
        return condition
    fact, operator, value = entry.get("fact"), entry.get("operator"), entry.get("value")
    if isinstance(fact, str) and isinstance(operator, str):
        return (
            f"{fact} {operator} {value!r}"
            if isinstance(value, str)
            else f"{fact} {operator} {value}"
        )
    return None


def _references(
    kind: str, mapping: dict[str, Any], condition: str | None = None
) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    if kind == "pkginfo":
        for key in DEPENDENCY_KEYS:
            refs += [
                {"field": key, "target": t, "condition": None} for t in _texts(mapping.get(key))
            ]
        return refs
    for key in (*INCLUDE_SECTIONS, *ITEM_SECTIONS):
        refs += [
            {"field": key, "target": t, "condition": condition} for t in _texts(mapping.get(key))
        ]
    items = mapping.get("conditional_items")
    if isinstance(items, list):
        for item in cast(list[Any], items):
            if isinstance(item, dict):
                entry = cast(dict[str, Any], item)
                refs += _references(kind, entry, condition_text(entry) or condition)
    return refs


def _problems(kind: str, mapping: dict[str, Any]) -> list[dict[str, str]]:
    """Manifest shapes Cimian clients do not read, per the conditional items guide."""
    if kind != "manifest":
        return []
    problems: list[dict[str, str]] = []
    items = mapping.get("conditional_items")
    for item in cast(list[Any], items) if isinstance(items, list) else []:
        if not isinstance(item, dict):
            continue
        entry = cast(dict[str, Any], item)
        if "fact" in entry or isinstance(entry.get("condition"), dict):
            problems.append(
                {
                    "severity": "error",
                    "code": "unsupported-condition-form",
                    "message": "Cimian reads only `condition:` strings; rewrite the "
                    "fact/operator/value form as one, such as condition: \"department == 'IT'\"",
                }
            )
        if "conditional_items" in entry:
            problems.append(
                {
                    "severity": "error",
                    "code": "nested-conditional-items",
                    "message": "Cimian does not read conditional items nested inside another; "
                    "combine the conditions with AND instead",
                }
            )
        if "conditions" in entry:
            problems.append(
                {
                    "severity": "error",
                    "code": "unsupported-condition-form",
                    "message": "Cimian does not read a `conditions:` list; use one `condition:` "
                    "string with AND or OR",
                }
            )
    return problems


def split_item(item: str) -> tuple[str, str | None]:
    """Cimian manifest items name a package without a version."""
    return item, None


def _text(value: Any) -> str | None:
    return value if isinstance(value, str) else None


def _texts(value: Any) -> list[str]:
    return (
        [v for v in cast(list[Any], value) if isinstance(v, str)] if isinstance(value, list) else []
    )


def import_paths(name: str, version: str, filename: str, subdirectory: str) -> tuple[str, str, str]:
    """Where an imported package's pkginfo and installer go, and the
    installer.location that points from one to the other."""
    folder = f"{subdirectory}/" if subdirectory else ""
    location = f"{folder}{filename}"
    return f"pkgsinfo/{folder}{name}-{version}{NEW_PKGINFO_SUFFIX}", f"pkgs/{location}", location


def prepare_import(pkginfo: dict[str, Any], sha256: str, location: str) -> None:
    """Check that makepkginfo's pkginfo describes the uploaded file, then point
    it at the installer's place in the repository. Raises ValueError otherwise."""
    installer = pkginfo.get("installer")
    if not isinstance(installer, dict):
        raise ValueError("the pkginfo has no installer section")
    details = cast(dict[str, Any], installer)
    if str(details.get("hash", "")).lower() != sha256:
        raise ValueError("the pkginfo's installer.hash is not the upload's SHA-256")
    details["location"] = location
    # For an .exe or .nupkg, makepkginfo lists the installer itself under
    # installs, at the path it was given: the worker's staging folder. No client
    # has that file, so it would never count as installed. Drop it; the reviewer
    # adds a real installs check.
    filename = PureWindowsPath(location).name.lower()
    installs = pkginfo.get("installs")
    if isinstance(installs, list):
        kept = [
            i
            for i in cast(list[Any], installs)
            if not (
                isinstance(i, dict)
                and cast(dict[str, Any], i).get("type") == "file"
                and PureWindowsPath(str(cast(dict[str, Any], i).get("path", ""))).name.lower()
                == filename
            )
        ]
        if kept:
            pkginfo["installs"] = kept
        else:
            del pkginfo["installs"]


def dump_new_pkginfo(data: Any) -> bytes:
    """The bytes of a new pkginfo file: block-style YAML that keeps text as text."""
    from io import StringIO

    from ruamel.yaml import YAML

    writer = YAML(typ="safe", pure=True)
    writer.default_flow_style = False
    writer.sort_base_mapping_type_on_output = False  # pyright: ignore[reportAttributeAccessIssue]
    writer.width = 4096
    buffer = StringIO()
    writer.dump(data, buffer)  # pyright: ignore[reportUnknownMemberType]
    return buffer.getvalue().encode("utf-8")

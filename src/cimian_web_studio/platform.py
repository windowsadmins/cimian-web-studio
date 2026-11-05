"""What a Cimian repository looks like. The only platform-specific part of scanning."""

from typing import Any, cast

from cimian_web_studio.jobs.remote import RemoteSpec

# Top-level folders that hold metadata, and the kind of object each file is.
KINDS = {"pkgsinfo": "pkginfo", "manifests": "manifest", "catalogs": "catalog"}

# Cimian metadata is YAML; other files in these folders are not metadata.
SUFFIXES: frozenset[str] | None = frozenset({".yaml", ".yml"})

IGNORED_NAMES = frozenset({".DS_Store", ".gitkeep", "Thumbs.db"})


# Workers. A Windows worker runs these Cimian tools and nothing else, from these paths.
WORKER_PLATFORM = "Windows"
WORKER_TOOLS = {
    "makecatalogs": r"C:\Program Files\Cimian\makecatalogs.exe",
}
# How each tool prints its version.
TOOL_VERSION_ARGS: dict[str, tuple[str, ...]] = {"makecatalogs": ("-V",)}
# Each capability a worker can offer, and the tools it needs.
CAPABILITIES = {
    "catalog.generate": ("makecatalogs",),
}
REMOTE_OPERATIONS = (
    RemoteSpec(
        name="catalog.preview",
        title="Build catalogs with makecatalogs",
        capability="catalog.generate",
        tool="makecatalogs",
        # Payloads are not sent to the worker, so their existence is not checked.
        args=("--repo_path", "{staging}", "--skip_payload_check"),
        inputs=("pkgsinfo",),
        outputs="catalogs",
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
        return {"items": len(cast(list[Any], data)) if isinstance(data, list) else 0}
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

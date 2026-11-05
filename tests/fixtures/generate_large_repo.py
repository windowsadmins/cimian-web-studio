"""Generate a large synthetic Cimian repository for benchmarks.

Deterministic from the seed: the same arguments always produce the same bytes.
All names are invented.

    python3 -I tests/fixtures/generate_large_repo.py OUT_DIR --pkginfo 10000 --manifests 2000
"""

import argparse
import random
from pathlib import Path

CATEGORIES = ("Browsers", "Creative", "Media", "Utilities", "Science", "Education", "Developer")
TYPES = ("exe", "msi", "msix", "nupkg")


def generate(out: Path, *, pkginfo: int, manifests: int, seed: int = 1) -> None:
    rng = random.Random(seed)
    names = [f"ExamplePackage{i:05d}" for i in range(max(1, pkginfo // 4))]
    for i in range(pkginfo):
        name = names[i % len(names)]
        version = f"{1 + i // len(names)}.{rng.randrange(10)}.{rng.randrange(100)}"
        category = CATEGORIES[rng.randrange(len(CATEGORIES))]
        kind = TYPES[rng.randrange(len(TYPES))]
        catalogs = "[testing, production]" if rng.random() < 0.6 else "[testing]"
        text = (
            f"name: {name}\n"
            f'version: "{version}"\n'
            f"category: {category}\n"
            f"description: Invented package {i}.\n"
            f"catalogs: {catalogs}\n"
            "installer:\n"
            f"  type: {kind}\n"
            f"  location: pkgs/{category.lower()}/{name}-{version}.{kind}\n"
            f"  hash: {rng.getrandbits(256):064x}\n"
            f"installed_size: {rng.randrange(1, 4_000_000)}\n"
        )
        path = out / "pkgsinfo" / category.lower() / f"{name}-{version}-{i}.yaml"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")

    groups = max(1, manifests // 20)
    for i in range(manifests):
        is_group = i < groups
        items = rng.sample(names, k=min(len(names), rng.randrange(1, 15)))
        lines = ["catalogs: [testing, production]", "managed_installs:"]
        lines += [f"  - {item}" for item in items]
        if not is_group:
            lines += ["included_manifests:", f"  - groups/group-{rng.randrange(groups):04d}"]
        folder, stem = (
            ("groups", f"group-{i:04d}") if is_group else ("computers", f"EXAMPLE-{i:05d}")
        )
        path = out / "manifests" / folder / f"{stem}.yaml"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")

    for folder in ("catalogs", "pkgs", "icons"):
        (out / folder).mkdir(parents=True, exist_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a large synthetic Cimian repository.")
    parser.add_argument("out", type=Path)
    parser.add_argument("--pkginfo", type=int, default=10_000)
    parser.add_argument("--manifests", type=int, default=2_000)
    parser.add_argument("--seed", type=int, default=1)
    args = parser.parse_args()
    generate(args.out, pkginfo=args.pkginfo, manifests=args.manifests, seed=args.seed)


if __name__ == "__main__":
    main()

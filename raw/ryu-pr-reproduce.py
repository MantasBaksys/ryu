"""Reconstruct the tested trees from the files in the accompanying evidence gist.

Run after cloning/downloading the gist:
    python3 ryu-pr-reproduce.py /tmp/ryu-pr-reproduction
Requires git, Cargo and the Rust 1.97.1 toolchain. The default mode runs
equivalence tests, not a new performance experiment.
"""

import argparse
import os
from pathlib import Path
import shutil
import subprocess

FILES = Path(__file__).resolve().parent
RYU_REV = "22a692e0b27d9ca74231a475eb690a9446ed44af"
BENCH_REV = "cee334fd15cf6f9f7679f5cde7948ff5c306ba2c"


def run(*command, cwd=None):
    subprocess.run(command, cwd=cwd, check=True)


def snapshot(base, destination, patch=None):
    shutil.copytree(
        base, destination, ignore=shutil.ignore_patterns(".git", "target")
    )
    if patch:
        run("git", "apply", str(FILES / patch), cwd=destination)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--prepare-benchmark", action="store_true")
    args = parser.parse_args()
    root = args.directory.resolve()
    root.mkdir(parents=True, exist_ok=False)
    os.environ["CARGO_TARGET_DIR"] = str(root / "target")
    os.environ["CARGO_BUILD_JOBS"] = "2"
    base = root / "base"
    run("git", "clone", "https://github.com/dtolnay/ryu.git", str(base))
    run("git", "checkout", "--detach", RYU_REV, cwd=base)
    for directory, patch, manifest in (
        ("upstream", None, "upstream-Cargo.toml"),
        ("pr-review", "ryu-macro-reference.patch", "macro-Cargo.toml"),
        ("closure-test", "ryu-closures-upstream.patch", "candidate-Cargo.toml"),
    ):
        destination = root / directory
        snapshot(base, destination, patch)
        shutil.copyfile(FILES / manifest, destination / "Cargo.toml")
    shutil.copyfile(
        FILES / "candidate-Cargo.lock", root / "closure-test/Cargo.lock"
    )
    harness = root / "closure-agreement"
    (harness / "src").mkdir(parents=True)
    for source, destination in (
        ("equivalence-main.rs", "src/main.rs"),
        ("equivalence-Cargo.toml", "Cargo.toml"),
        ("equivalence-Cargo.lock", "Cargo.lock"),
    ):
        shutil.copyfile(FILES / source, harness / destination)
    for features in ((), ("--features", "small")):
        for action in ("test", "run"):
            run(
                "cargo", action, "--release", "--locked", "--manifest-path",
                str(harness / "Cargo.toml"), *features,
            )
        run(
            "cargo", "test", "--release", "--locked", "--manifest-path",
            str(root / "closure-test/Cargo.toml"), *features,
        )

    if args.prepare_benchmark:
        for directory, patch in (
            ("pointer-free", "ryu-pointer-free-snapshot.patch"),
            ("optimized", "ryu-optimized-snapshot.patch"),
        ):
            snapshot(base, root / directory, patch)
            shutil.copyfile(
                FILES / f"{directory}-Cargo.toml", root / directory / "Cargo.toml"
            )
        snapshot(base, root / "closure-benchmark", "ryu-closures-upstream.patch")
        shutil.copyfile(
            FILES / "benchmark-candidate-Cargo.toml",
            root / "closure-benchmark/Cargo.toml",
        )
        benchmark = root / "dtoa-benchmark"
        run("git", "clone", "https://github.com/dtolnay/dtoa-benchmark.git", str(benchmark))
        run("git", "checkout", "--detach", BENCH_REV, cwd=benchmark)
        run("git", "apply", str(FILES / "dtoa-benchmark.patch"), cwd=benchmark)
        shutil.copyfile(FILES / "benchmark-Cargo.lock", benchmark / "Cargo.lock")
        shutil.copyfile(FILES / "benchmark-ryu_agreement.rs", benchmark / "src/ryu_agreement.rs")
        shutil.copyfile(FILES / "run_closure_codespace.py", root / "run_closure_codespace.py")
        os.environ["RUSTFLAGS"] = "-Ctarget-cpu=native"
        run(
            "cargo", "build", "--release", "--locked", "--manifest-path",
            str(benchmark / "Cargo.toml"),
        )
        print(
            "Benchmark prepared, not started. Verify CPU 2/3 SMT topology, then run:",
            f"python3 {root / 'run_closure_codespace.py'}",
        )


if __name__ == "__main__":
    main()

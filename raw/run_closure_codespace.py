import hashlib
import json
import os
from pathlib import Path
from statistics import median
import subprocess
import time

ROOT = Path(__file__).resolve().parent
RESULTS = ROOT / "results"
BINARY = ROOT / "target/release/dtoa-benchmark"
PREFIX = "closure-codespace"
COUNT = 12
CPU = 2
SIBLING = 3
INTERVAL = 5
LIBRARIES = (
    "core[Display]", "core[LowerExp]", "dtoa", "ryu", "lexical",
    "teju", "zmij", "ryu-opt", "ryu-closures",
)
EXPECTED = {
    (library, width, digit)
    for library in LIBRARIES
    for width, count in (("f32", 9), ("f64", 17))
    for digit in range(1, count + 1)
}


def snapshot():
    result = {}
    for line in Path("/proc/stat").read_text().splitlines():
        fields = line.split()
        if fields and fields[0].startswith("cpu"):
            ticks = [int(value) for value in fields[1:9]]
            result[fields[0]] = (sum(ticks), ticks[3] + ticks[4], ticks[7])
    return result


def sample(before):
    after = snapshot()
    cpu, steal = {}, {}
    for name, (total, idle, stolen) in after.items():
        old_total, old_idle, old_stolen = before[name]
        delta = total - old_total
        if delta <= 0:
            raise RuntimeError(f"invalid CPU sample for {name}")
        cpu[name] = 100 * (1 - (idle - old_idle) / delta)
        steal[name] = 100 * (stolen - old_stolen) / delta
    return after, {
        "timestamp": time.time(), "cpu": cpu, "steal": steal, "load": os.getloadavg(),
    }


def quiet_window():
    stable, samples = 0, []
    before = snapshot()
    while stable < 4:
        time.sleep(INTERVAL)
        before, observation = sample(before)
        quiet = (
            observation["cpu"]["cpu"] <= 10
            and observation["cpu"][f"cpu{CPU}"] <= 5
            and observation["cpu"][f"cpu{SIBLING}"] <= 5
            and observation["steal"][f"cpu{CPU}"] <= 1
            and observation["load"][0] <= 2
        )
        stable = stable + 1 if quiet else 0
        samples.append(observation)
        if len(samples) == 1 or len(samples) % 6 == 0:
            print(
                f"quiet gate: overall {observation['cpu']['cpu']:.1f}%, "
                f"CPU {CPU} {observation['cpu'][f'cpu{CPU}']:.1f}%, "
                f"SMT sibling {observation['cpu'][f'cpu{SIBLING}']:.1f}%, "
                f"load {observation['load'][0]:.2f}; stable {stable}/4",
                flush=True,
            )
    return samples


def parse(path):
    cells = {}
    for line in path.read_text().splitlines():
        marker, library, width, digit, ns = line.split(",")
        key = (library, width, int(digit))
        if marker != "measurement" or key not in EXPECTED or key in cells:
            raise ValueError(f"unexpected or duplicate measurement: {line}")
        cells[key] = float(ns)
        if not 0 < cells[key] < float("inf"):
            raise ValueError(f"invalid duration: {line}")
    if set(cells) != EXPECTED:
        raise ValueError(f"missing measurements in {path}")
    return cells


RESULTS.mkdir(exist_ok=True)
if not {0, CPU, SIBLING}.issubset(os.sched_getaffinity(0)):
    raise RuntimeError("monitor, benchmark and SMT sibling CPUs must be available")
os.sched_setaffinity(0, {0})
metadata = {
    "machine": "benchmark Codespace; congenial-orbit-6rxjgvw99prh4pgp",
    "benchmark_revision": "cee334fd15cf6f9f7679f5cde7948ff5c306ba2c",
    "upstream_ryu_revision": "22a692e0b27d9ca74231a475eb690a9446ed44af",
    "cpu_model": subprocess.check_output(["lscpu"], text=True),
    "rustc": subprocess.check_output(["rustc", "--version"], text=True).strip(),
    "candidate_sha256": {
        name: hashlib.sha256((ROOT / "closure-benchmark/src" / name).read_bytes()).hexdigest()
        for name in ("d2s.rs", "f2s.rs")
    },
    "candidate": "approved explicitly inlined local-closure rewrite",
    "features": "default",
    "rust_flags": "-Ctarget-cpu=native",
    "cpu": CPU,
    "smt_sibling": SIBLING,
    "monitor_cpu": 0,
    "count": 100000,
    "trials": 4,
    "passes": 12,
    "rounds": COUNT,
    "sampler": "seed 1; reject values that round to infinity",
    "measurement_order": "interleaved by precision; rotate/reverse library order across rounds",
    "binary_sha256": hashlib.sha256(BINARY.read_bytes()).hexdigest(),
    "quiet_policy": {
        "before": "20 seconds: overall <=10%, CPU2 and sibling CPU3 <=5%, CPU2 steal <=1%, load <=2",
        "during": "other CPUs mean <=10%, SMT sibling <=10%, CPU2 steal <=1%; sampled every 5 seconds",
        "rejection": "competing activity only, never formatter durations",
    },
    "runs": [],
    "rejected_runs": [],
}
provenance = RESULTS / f"{PREFIX}-provenance.json"
rounds, attempt = [], 0
if provenance.exists():
    saved = json.loads(provenance.read_text())
    for key in metadata:
        if key not in ("runs", "rejected_runs") and saved[key] != metadata[key]:
            raise RuntimeError(f"cannot resume with changed provenance: {key}")
    metadata = saved
    rounds = [
        parse(RESULTS / f"{PREFIX}-round-{index}.txt")
        for index in range(len(metadata["runs"]))
    ]
    attempts = metadata["runs"] + metadata["rejected_runs"]
    attempt = max((run["attempt"] for run in attempts), default=-1) + 1
    while (RESULTS / f"{PREFIX}-attempt-{attempt}.txt").exists():
        attempt += 1
else:
    provenance.write_text(json.dumps(metadata, indent=2) + "\n")
print("Codespace monitor ready; collecting 12 accepted quiet rounds", flush=True)
while len(rounds) < COUNT:
    quiet_samples = quiet_window()
    index = len(rounds)
    offset = index % len(LIBRARIES)
    order = LIBRARIES[offset:] + LIBRARIES[:offset]
    if index % 2:
        order = tuple(reversed(order))
    command = ["taskset", "-c", str(CPU), str(BINARY), "--interleave", *order]
    output = RESULTS / f"{PREFIX}-attempt-{attempt}.txt"
    stderr_path = RESULTS / f"{PREFIX}-attempt-{attempt}.stderr.txt"
    run = {
        "command": command, "attempt": attempt, "started_at": time.time(),
        "quiet_samples": quiet_samples, "activity_samples": [],
    }
    rejection = None
    print(f"starting Codespace round {index + 1}/{COUNT}", flush=True)
    with output.open("w") as stdout, stderr_path.open("w") as stderr:
        process = subprocess.Popen(command, stdout=stdout, stderr=stderr)
        try:
            before = snapshot()
            while process.poll() is None:
                time.sleep(INTERVAL)
                before, observation = sample(before)
                run["activity_samples"].append(observation)
                others = [
                    value for name, value in observation["cpu"].items()
                    if name not in ("cpu", f"cpu{CPU}")
                ]
                if (
                    sum(others) / len(others) > 10
                    or observation["cpu"][f"cpu{SIBLING}"] > 10
                    or observation["steal"][f"cpu{CPU}"] > 1
                ):
                    rejection = "competing CPU/SMT activity or steal time"
                    if process.poll() is None:
                        process.terminate()
                    break
            returncode = process.wait(timeout=30)
        finally:
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=30)
    run.update(elapsed_seconds=time.time() - run["started_at"], output=str(output))
    if rejection is not None:
        run["reason"] = rejection
        metadata["rejected_runs"].append(run)
        print(f"rejected attempt {attempt}: {rejection}", flush=True)
    else:
        if returncode != 0:
            raise RuntimeError(f"benchmark failed with exit {returncode}; see {stderr_path}")
        cells = parse(output)
        rounds.append(cells)
        (RESULTS / f"{PREFIX}-round-{index}.txt").write_bytes(output.read_bytes())
        metadata["runs"].append(run)
        print(f"accepted Codespace round {len(rounds)}/{COUNT}", flush=True)
    attempt += 1
    provenance.write_text(json.dumps(metadata, indent=2) + "\n")

comparisons = {}
for label, width, digits in (
    ("f32_all", "f32", range(1, 10)),
    ("f64_short", "f64", range(1, 10)),
    ("f64_all", "f64", range(1, 18)),
    ("f64_long", "f64", range(13, 18)),
):
    comparisons[label] = {}
    for reference in ("ryu", "ryu-opt"):
        changes = [
            100 * (
                sum(cells[("ryu-closures", width, digit)] for digit in digits)
                / sum(cells[(reference, width, digit)] for digit in digits)
                - 1
            )
            for cells in rounds
        ]
        comparisons[label][reference] = {
            "median_percent_change": median(changes), "round_percent_changes": changes,
        }
summary = {
    "statistic": "median paired-round percentage duration change; equal precision weighting; negative is faster",
    "comparisons": comparisons,
}
(RESULTS / f"{PREFIX}-summary.json").write_text(json.dumps(summary, indent=2) + "\n")
print(json.dumps(summary, indent=2), flush=True)

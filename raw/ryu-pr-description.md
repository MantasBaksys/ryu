## WIP - not ready for review or merge

This draft is a working proposal. We intend to iterate on it ourselves before
marking it ready for review. Please do not treat it as a finished upstream
optimization or a re-verified implementation.

### Scope

This is the full previously tested candidate: a pointer-free formatting
adaptation plus chunked digit removal, with local capturing closures instead
of `macro_rules!`. The closures take only a digit count; existing state remains
local. The single-use f64 common-path chunk is an ordinary loop. The existing
single-digit fallback and rounding behavior are retained.

The diff contains **9 files, 322 insertions and 208 deletions**. It does not add
benchmark output, vendored dependencies, generated Lean, or unrelated source
changes. Base: `75f9e707e77c89717ffb9c2a01fe2c28a016cc82`.

**Compatibility warning:** this full candidate changes the public
`raw::format32` / `raw::format64` interface from a raw pointer to
`&mut [u8; 24]`. `Buffer::format` and `Buffer::format_finite` retain their
interface and are the interfaces covered by the equivalence results below.
This is not a drop-in API-compatible upstream change.

Source inspection shows that the float serialization paths in
[serde_yaml](https://github.com/dtolnay/serde-yaml/blob/master/src/ser.rs)
and the AWS SDK's
[aws-smithy-types primitive encoder](https://github.com/smithy-lang/smithy-rs/blob/main/rust-runtime/aws-smithy-types/src/primitive.rs)
use `ryu::Buffer::new()` and `format_finite`, not the changed raw API.
The AWS
[JSON writer](https://github.com/smithy-lang/smithy-rs/blob/main/rust-runtime/aws-smithy-json/src/serialize.rs)
delegates float formatting to that encoder. These inspected call sites do
not require source changes. Full downstream builds/tests have not been run;
this does not establish compatibility for every SDK version or every other
Ryu consumer.

### Performance

All chart implementations were remeasured on the same benchmark Codespace
(AMD EPYC 7763, Rust 1.97.1). The chart labels the candidate **ryu (this PR)**.
The optimized macro version was also measured as an unplotted comparator.

Median paired-round duration changes; **negative means faster**:

| Precision | vs pinned upstream | vs optimized macros |
|---|---:|---:|
| f32, 1-9 | +3.71% | -0.52% |
| f64, 1-9 | -18.93% | -0.30% |
| f64, 1-17 | -9.56% | -0.04% |
| f64, 13-17 | +8.26% | +0.62% |

These are 12 accepted interleaved rounds, with zero activity rejections.
Each precision uses 100,000 deterministic inputs, four trials and 12 passes;
the best trial within each round is retained. Library order rotates/reverses
between rounds. The full formatted output is black-boxed.

The benchmark is pinned to `cee334fd15cf6f9f7679f5cde7948ff5c306ba2c`;
upstream Ryu is pinned to `22a692e0b27d9ca74231a475eb690a9446ed44af`.
The current PR base differs from that Ryu revision only in benchmark/test
warning cleanup, not library source.

Timing is pinned to CPU 2, with CPU 3 monitored as its SMT sibling.
Before each round, four consecutive five-second samples require overall
CPU <=10%, timing CPU and sibling <=5%, steal <=1%, and load <=2.
During timing, competing CPUs' mean must remain <=10%, sibling <=10%,
and timing CPU steal <=1%. Raw monitoring samples are retained.
The sampler rejects values that round to infinity.

The main result is preservation of the macro implementation's performance,
not an across-the-board upstream speedup. f32 and long-precision f64 regress
against upstream. Sub-percent differences are not portable performance
guarantees; this experiment does not calibrate binary-layout effects.

### Equivalence evidence

A reproducible harness compares **exact formatted bytes against both pinned
upstream and the optimized macro reference**, for both default and `small`
features. For finite values it also compares `format_finite` and checks
bit-exact parse-back, including signed zero.

| Input category | f32 checks per configuration | f64 checks per configuration |
|---|---:|---:|
| Deterministic random bit patterns | 5,000,000 | 5,000,000 |
| Every exponent field, seven selected mantissas, both signs | 3,584 | 28,672 |
| Decimal powers/significands and adjacent bit patterns | 45,773 | 49,372 |
| Total | 5,049,357 | 5,078,044 |

**Zero byte mismatches or finite round-trip failures in 10,127,401 checks per
configuration**, or 20,254,802 case executions across default and `small`.
The same deterministic corpus is reused across configurations; these are
not 20 million independent inputs. The corpus includes subnormals,
exponent transitions, signed zero, infinities and NaN encodings.

Seed: `0x72797520261001`. Generator: xorshift64 with shifts 13, 7, 17;
alternating f32 high 32 bits and f64 full bits. A negative-control test
deliberately changes an output and verifies that the byte comparator fails.
Machine-readable counts, compiler version, source hashes, commands, stdout,
stderr, harness source and lockfiles are retained in the evidence bundle.

On the exact latest-base PR tree, release integration tests pass in both
configurations: **50 tests with default features and 41 with `small`**.
The exhaustive test is ignored in each configuration; it was not run.

### Work remaining

- Address the upstream raw-API compatibility change and scope.
- Decide whether the f32 and long-precision f64 regressions are acceptable.
- Test the declared Rust 1.71 minimum and the optional `no-panic` feature.
- Complete formal integration and reproof. Charon extraction, Aeneas borrow
  checking and Lean generation succeeded, but `.pow()` remains opaque in the
  quick extraction; generated Lean was not built or re-proved.

Sampled equivalence is evidence, not an exhaustive equivalence proof.
No claim is made that all f32 encodings or all f64 values were checked.

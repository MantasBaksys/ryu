use rand::rngs::SmallRng;
use rand::{Rng as _, SeedableRng as _};

fn same(expected: &str, pointer_free: &str, optimized: &str, bits: u64) {
    assert_eq!(
        pointer_free, expected,
        "pointer-free mismatch at {bits:#018x}"
    );
    assert_eq!(optimized, expected, "optimized mismatch at {bits:#018x}");
}

fn check32(bits: u32) {
    let value = f32::from_bits(bits);
    let mut upstream = ryu::Buffer::new();
    let mut pointer_free = ryu_pf::Buffer::new();
    let mut optimized = ryu_opt::Buffer::new();
    let expected = upstream.format(value);
    same(
        expected,
        pointer_free.format(value),
        optimized.format(value),
        bits as u64,
    );
    if value.is_finite() {
        assert_eq!(expected.parse::<f32>().unwrap().to_bits(), bits);
    }
}

fn check64(bits: u64) {
    let value = f64::from_bits(bits);
    let mut upstream = ryu::Buffer::new();
    let mut pointer_free = ryu_pf::Buffer::new();
    let mut optimized = ryu_opt::Buffer::new();
    let expected = upstream.format(value);
    same(
        expected,
        pointer_free.format(value),
        optimized.format(value),
        bits,
    );
    if value.is_finite() {
        assert_eq!(expected.parse::<f64>().unwrap().to_bits(), bits);
    }
}

#[test]
#[should_panic(expected = "optimized mismatch")]
fn negative_control() {
    same("1.0", "1.0", "1.1", 0);
}

#[test]
fn boundaries_and_trailing_zeros() {
    for exponent in 0..=255u32 {
        for mantissa in [
            0,
            1,
            2,
            (1 << 22) - 1,
            1 << 22,
            (1 << 23) - 2,
            (1 << 23) - 1,
        ] {
            for sign in [0, 1 << 31] {
                check32(sign | (exponent << 23) | mantissa);
            }
        }
    }
    for exponent in 0..=2047u64 {
        for mantissa in [
            0,
            1,
            2,
            (1 << 51) - 1,
            1 << 51,
            (1 << 52) - 2,
            (1 << 52) - 1,
        ] {
            for sign in [0, 1 << 63] {
                check64(sign | (exponent << 52) | mantissa);
            }
        }
    }
    for exponent in -324..=308 {
        for significand in [
            1u64, 2, 5, 10, 25, 50, 100, 125, 250, 500, 1000, 10000, 100000000,
        ] {
            let value = format!("{significand}e{exponent}").parse::<f64>().unwrap();
            for bits in [value.to_bits(), (-value).to_bits()] {
                check64(bits);
                if value.is_finite() {
                    for adjacent in [bits.checked_sub(1), bits.checked_add(1)]
                        .into_iter()
                        .flatten()
                    {
                        check64(adjacent);
                    }
                }
            }
            let value = format!("{significand}e{exponent}").parse::<f32>().unwrap();
            for bits in [value.to_bits(), (-value).to_bits()] {
                check32(bits);
                if value.is_finite() {
                    for adjacent in [bits.checked_sub(1), bits.checked_add(1)]
                        .into_iter()
                        .flatten()
                    {
                        check32(adjacent);
                    }
                }
            }
        }
    }
    println!("all exponent boundaries, signed specials, decimal powers and adjacent floats agree");
}

#[test]
fn deterministic_random_bits() {
    let mut rng = SmallRng::seed_from_u64(0x72797520261001);
    let mut finite32 = 0u64;
    let mut finite64 = 0u64;
    for _ in 0..5_000_000 {
        let bits32 = rng.next_u32();
        let bits64 = rng.next_u64();
        finite32 += u64::from(f32::from_bits(bits32).is_finite());
        finite64 += u64::from(f64::from_bits(bits64).is_finite());
        check32(bits32);
        check64(bits64);
    }
    println!(
        "random draws: f32=5000000 ({finite32} finite), f64=5000000 ({finite64} finite); all agree"
    );
}

#[test]
fn exact_benchmark_corpus() {
    let data = crate::data::Data::random(crate::COUNT, false);
    for group in &data.f32.by_precision {
        for value in group {
            assert!(value.is_finite(), "benchmark f32 input must be finite");
            check32(value.to_bits());
        }
    }
    for group in &data.f64.by_precision {
        for value in group {
            assert!(value.is_finite(), "benchmark f64 input must be finite");
            check64(value.to_bits());
        }
    }
    println!("benchmark corpus: f32=900000, f64=1700000; all agree");
}

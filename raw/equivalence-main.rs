fn equal(expected: &str, actual: &str, reference: &str, width: &str, bits: u64) {
    assert_eq!(
        actual, expected,
        "{width} byte mismatch against {reference} at {bits:#018x}"
    );
}

fn check32(bits: u32) -> bool {
    let value = f32::from_bits(bits);
    let mut upstream = ryu_upstream::Buffer::new();
    let mut before = ryu_before::Buffer::new();
    let mut after = ryu_after::Buffer::new();
    let actual = after.format(value);
    equal(
        upstream.format(value),
        actual,
        "upstream",
        "f32",
        bits.into(),
    );
    equal(before.format(value), actual, "macros", "f32", bits.into());
    if value.is_finite() {
        assert_eq!(
            actual.parse::<f32>().unwrap().to_bits(),
            bits,
            "f32 round trip at {bits:#010x}"
        );
        equal(
            actual,
            upstream.format_finite(value),
            "upstream format_finite",
            "f32",
            bits.into(),
        );
        equal(
            actual,
            before.format_finite(value),
            "macros format_finite",
            "f32",
            bits.into(),
        );
        equal(
            actual,
            ryu_after::Buffer::new().format_finite(value),
            "PR format_finite",
            "f32",
            bits.into(),
        );
    }
    value.is_finite()
}

fn check64(bits: u64) -> bool {
    let value = f64::from_bits(bits);
    let mut upstream = ryu_upstream::Buffer::new();
    let mut before = ryu_before::Buffer::new();
    let mut after = ryu_after::Buffer::new();
    let actual = after.format(value);
    equal(upstream.format(value), actual, "upstream", "f64", bits);
    equal(before.format(value), actual, "macros", "f64", bits);
    if value.is_finite() {
        assert_eq!(
            actual.parse::<f64>().unwrap().to_bits(),
            bits,
            "f64 round trip at {bits:#018x}"
        );
        equal(
            actual,
            upstream.format_finite(value),
            "upstream format_finite",
            "f64",
            bits,
        );
        equal(
            actual,
            before.format_finite(value),
            "macros format_finite",
            "f64",
            bits,
        );
        equal(
            actual,
            ryu_after::Buffer::new().format_finite(value),
            "PR format_finite",
            "f64",
            bits,
        );
    }
    value.is_finite()
}

#[derive(Default)]
struct Counts {
    f32_total: u64,
    f32_finite: u64,
    f64_total: u64,
    f64_finite: u64,
}

impl Counts {
    fn check32(&mut self, bits: u32) {
        self.f32_finite += u64::from(check32(bits));
        self.f32_total += 1;
    }

    fn check64(&mut self, bits: u64) {
        self.f64_finite += u64::from(check64(bits));
        self.f64_total += 1;
    }

    fn json(&self) -> String {
        format!(
            "{{\"f32_checks\":{},\"f32_finite\":{},\"f32_nonfinite\":{},\"f64_checks\":{},\"f64_finite\":{},\"f64_nonfinite\":{}}}",
            self.f32_total, self.f32_finite, self.f32_total - self.f32_finite,
            self.f64_total, self.f64_finite, self.f64_total - self.f64_finite,
        )
    }
}

fn next(state: &mut u64) -> u64 {
    *state ^= *state << 13;
    *state ^= *state >> 7;
    *state ^= *state << 17;
    *state
}

fn main() {
    let mut boundaries = Counts::default();
    let mut decimals = Counts::default();
    let mut random = Counts::default();
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
                boundaries.check32(sign | (exponent << 23) | mantissa);
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
                boundaries.check64(sign | (exponent << 52) | mantissa);
            }
        }
    }
    for exponent in -324..=308 {
        for significand in [
            1u64, 2, 5, 10, 25, 50, 100, 125, 250, 500, 1000, 10000, 100000000,
        ] {
            for value in [
                format!("{significand}e{exponent}").parse::<f64>().unwrap(),
                -format!("{significand}e{exponent}").parse::<f64>().unwrap(),
            ] {
                let bits = value.to_bits();
                decimals.check64(bits);
                for adjacent in [bits.checked_sub(1), bits.checked_add(1)]
                    .into_iter()
                    .flatten()
                {
                    decimals.check64(adjacent);
                }
            }
            for value in [
                format!("{significand}e{exponent}").parse::<f32>().unwrap(),
                -format!("{significand}e{exponent}").parse::<f32>().unwrap(),
            ] {
                let bits = value.to_bits();
                decimals.check32(bits);
                for adjacent in [bits.checked_sub(1), bits.checked_add(1)]
                    .into_iter()
                    .flatten()
                {
                    decimals.check32(adjacent);
                }
            }
        }
    }
    let mut state = 0x72797520261001;
    for _ in 0..5_000_000 {
        random.check32((next(&mut state) >> 32) as u32);
        random.check64(next(&mut state));
    }
    println!(
        "{{\"status\":\"passed\",\"small\":{},\"references\":[\"pinned upstream\",\"optimized macros\"],\"seed\":\"0x72797520261001\",\"rng\":\"xorshift64 shifts 13,7,17; alternating f32 high 32 bits and f64 full bits\",\"checks\":\"format bytes match both references; finite format_finite bytes match; finite round-trip bits match including signed zero\",\"exponent_boundaries\":{},\"decimal_powers_and_neighbors\":{},\"random\":{}}}",
        cfg!(feature = "small"), boundaries.json(), decimals.json(), random.json()
    );
}

#[cfg(test)]
mod tests {
    #[test]
    #[should_panic(expected = "byte mismatch")]
    fn negative_control() {
        super::equal("1.0", "1.1", "upstream", "f32", 0);
    }
}

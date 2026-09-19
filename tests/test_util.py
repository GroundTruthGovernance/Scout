from scout.core import util


def test_safe_code_uppercases_and_strips():
    assert util.safe_code("  sol rug ") == "SOL-RUG"
    assert util.safe_code("s01") == "S01"
    assert util.safe_code(None) == ""
    assert util.safe_code("a/b\\c") == "A-B-C"


def test_safe_text_handles_none():
    assert util.safe_text(None) == ""
    assert util.safe_text(0) == "0"
    assert util.safe_text("hi") == "hi"


def test_safe_number_fallback():
    assert util.safe_number("0.9") == 0.9
    assert util.safe_number(None) == -1.0
    assert util.safe_number("not a number", fallback=0.0) == 0.0
    assert util.safe_number(float("nan"), fallback=-2.0) == -2.0


def test_pad_helpers():
    assert util.pad2(3) == "03"
    assert util.pad2(11) == "11"
    assert util.pad3(7) == "007"


def test_make_uid_shape():
    uid = util.make_uid("SAMPLE")
    assert uid.startswith("SAMPLE-")
    parts = uid.split("-")
    assert len(parts) == 3


def test_simple_hash_is_stable_and_short():
    h1 = util.simple_hash("a|b|c")
    h2 = util.simple_hash("a|b|c")
    h3 = util.simple_hash("a|b|d")
    assert h1 == h2
    assert h1 != h3
    assert len(h1) == 8


def test_normalize_hex_color():
    assert util.normalize_hex_color("#ff7f00") == "FF7F00"
    assert util.normalize_hex_color("nonsense") == "FF00FF"
    assert util.normalize_hex_color("nonsense", fallback="000000") == "000000"


def test_similarity_palette_ends_on_input_color():
    palette = util.make_similarity_palette("FF7F00")
    assert len(palette) == 6
    assert palette[-1] == "FF7F00"
    # first stop should be much lighter (closer to white) than the last
    assert palette[0] != palette[-1]


def test_utc_now_iso_format():
    stamp = util.utc_now_iso()
    assert stamp.endswith("Z")


def test_build_response_fingerprint_is_deterministic_and_sensitive():
    common = dict(
        sample_id="SOL-RUG-CRK-F01-S01", reference_year="2023", target_year="2023",
        extent_name="Fylde", threshold_mode="Absolute cosine cutoff", threshold=0.9,
    )
    fp1 = util.build_response_fingerprint(**common)
    fp2 = util.build_response_fingerprint(**common)
    assert fp1 == fp2
    assert fp1.startswith("RF-")

    fp3 = util.build_response_fingerprint(**{**common, "threshold": 0.91})
    assert fp3 != fp1

    fp4 = util.build_response_fingerprint(**{**common, "sample_id": None})
    assert fp4 != fp1  # None sample_id falls back to the "NO_SAMPLE" sentinel, not a crash


def test_get_ae_vis_solid_vs_ramp():
    solid = util.get_ae_vis(0.9, "Solid colour", "#FF7F00")
    assert solid == {"min": 0.9, "max": 1, "palette": ["FF7F00"]}

    ramp = util.get_ae_vis(0.9, "Similarity ramp", "#FF7F00")
    assert ramp["min"] == 0.9
    assert len(ramp["palette"]) == 6
    assert ramp["palette"][-1] == "FF7F00"

import pandas as pd

from market_data_hub.domains.commodities.fertilizer_ams import parse_ams_3195_text


def test_parse_legacy_ams_layout() -> None:
    text = """
Report for                  9/22/2022
Product Unit Offer Average Change
Anhydrous Ammonia Per ton 1150.00-1485.00 1318.33 UP 74.44
Urea 46-0-0 Per ton 825.00-900.00 858.33 UNCH
Liquid Nitrogen 32-0-0 Per ton 575.00-630.00 608.33 UP 23.33
"""

    frame = parse_ams_3195_text(
        text,
        report_date="2022-09-22",
        source_document="legacy.pdf",
        source_url=None,
        sha256="abc",
    )

    assert list(frame["product"]) == ["anhydrous_ammonia", "urea_46", "uan_32"]
    assert frame.loc[0, "price_average"] == 1318.33
    assert frame.loc[0, "report_date"] == pd.Timestamp("2022-09-22")


def test_parse_modern_ams_layout() -> None:
    text = """
Illinois Production Cost Report (Bi-weekly)
Fri Jul 10, 2026
Anhydrous Ammonia
Ask
840.00 - 1,210.00
1,057.50
0.00
F.O.B.
Current
Liquid Nitrogen (28-0-0)
Ask
450.00 - 600.00
550.00
0.00
F.O.B.
Current
Liquid Nitrogen (32-0-0)
Ask
605.00
605.00
0.00
F.O.B.
Current
Urea (46-0-0)
Ask
595.00 - 890.00
752.50
0.00
F.O.B.
Current
"""

    frame = parse_ams_3195_text(
        text,
        report_date="2026-07-06",
        source_document="modern.pdf",
        source_url="https://example.test/modern.pdf",
        sha256="def",
    )

    assert set(frame["product"]) == {"anhydrous_ammonia", "uan_28", "uan_32", "urea_46"}
    uan32 = frame.loc[frame["product"].eq("uan_32")].iloc[0]
    assert uan32["price_low"] == 605.0
    assert uan32["price_high"] == 605.0
    assert uan32["available_time"] == pd.Timestamp("2026-07-10")


def test_parse_aligned_pdf_layout() -> None:
    text = """
Report for week ending 08/23/2024
Anhydrous Ammonia Ask 635.00 - 775.00 677.65 (64.02) F.O.B. Current
Liquid Nitrogen (28-0-0) Ask 267.00 - 440.00 352.91 (6.84) F.O.B. Current
Liquid Nitrogen (32-0-0) Ask 340.00 340.00 0.00 F.O.B. Current
Urea (46-0-0) Ask 515.00 - 554.00 535.60 (4.00) F.O.B. Current
"""

    frame = parse_ams_3195_text(
        text,
        report_date="2024-08-19",
        source_document="aligned.pdf",
        source_url=None,
        sha256="ghi",
    )

    assert len(frame) == 4
    assert set(frame["extraction_layout"]) == {"aligned_table"}
    assert frame.loc[frame["product"].eq("uan_32"), "price_average"].iloc[0] == 340.0

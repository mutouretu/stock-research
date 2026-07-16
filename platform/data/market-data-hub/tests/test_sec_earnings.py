from datetime import datetime, timezone

from market_data_hub.domains.company_operations.cf import parse_cf_earnings_exhibit


def test_parse_cf_earnings_exhibit_current_quarter_metrics() -> None:
    html = """
    <html><body>
      <p>Consolidated Results</p>
      <table>
        <tr><td></td><td>Three months ended March 31,</td></tr>
        <tr><td></td><td>2026</td><td>2025</td></tr>
        <tr><td>Cost of natural gas used for production in cost of sales</td><td>$</td><td>4.57</td><td>$</td><td>3.68</td></tr>
        <tr><td>Production volume by product tons (000s):</td></tr>
        <tr><td>Ammonia(5)</td><td>2,457</td><td>2,617</td></tr>
      </table>
      <p>Granular Urea Segment</p>
      <table>
        <tr><td></td><td>Three months ended March 31,</td></tr>
        <tr><td></td><td>2026</td><td>2025</td></tr>
        <tr><td>Sales volume by product tons (000s)</td><td>1,291</td><td>1,125</td></tr>
        <tr><td>Average selling price per product ton</td><td>$</td><td>457</td><td>$</td><td>390</td></tr>
      </table>
    </body></html>
    """
    frame = parse_cf_earnings_exhibit(
        html,
        accession="0001324404-26-000011",
        filing_date="2026-05-06",
        source_url="https://www.sec.gov/example.htm",
        retrieved_at=datetime(2026, 5, 6, tzinfo=timezone.utc),
    )

    values = {(row.product, row.metric): row.value for row in frame.itertuples()}
    assert values[("all_products", "realized_natural_gas_cost")] == 4.57
    assert values[("all_products", "production_volume_ammonia")] == 2457
    assert values[("granular_urea", "sales_volume")] == 1291
    assert values[("granular_urea", "average_selling_price")] == 457
    assert set(frame["period_end"].dt.strftime("%Y-%m-%d")) == {"2026-03-31"}

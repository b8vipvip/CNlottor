import unittest

from cnlottor.core import DEFAULT_REGISTRY
from cnlottor.data_engine.parsers import parse_datachart_html


class DataChartParserTests(unittest.TestCase):
    def test_parse_ssq_multiple_pools(self):
        html = """
        <tbody id='tdata'><tr>
          <td>2026001</td><td>01</td><td>02</td><td>03</td><td>04</td><td>05</td><td>06</td><td>16</td>
        </tr></tbody>
        """
        draw = parse_datachart_html(DEFAULT_REGISTRY.get("ssq"), html)[0]
        self.assertEqual(draw.pools["main"], [1, 2, 3, 4, 5, 6])
        self.assertEqual(draw.pools["bonus"], [16])

    def test_parse_compact_ordered_digits(self):
        html = "<table id='tablelist'><tr><td>2026001</td><td>383</td></tr></table>"
        draw = parse_datachart_html(DEFAULT_REGISTRY.get("pls"), html)[0]
        self.assertEqual(draw.pools["digits"], [3, 8, 3])

    def test_parse_kl8_skips_issue_cell(self):
        cells = "".join(f"<td>{number:02d}</td>" for number in range(1, 21))
        html = f"<tbody id='tdata'><tr><td>2026001</td>{cells}</tr></tbody>"
        draw = parse_datachart_html(DEFAULT_REGISTRY.get("kl8"), html)[0]
        self.assertEqual(draw.pools["main"], list(range(1, 21)))


if __name__ == "__main__":
    unittest.main()

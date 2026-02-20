import logging
from pathlib import Path

import polars as pl

logger = logging.getLogger(__name__)


class CreditGenerator:
    def __init__(self, xlsx_path: Path):
        self.xlsx_path = xlsx_path

    def generate(self, output_path: Path | None = None) -> Path:
        """Read 'credit' column from Excel and write a 2-column HTML table."""
        df = pl.read_excel(self.xlsx_path)
        seen: set[str] = set()
        credits = []
        for c in df["credit"].to_list():
            if c is None or not str(c).strip():
                continue
            text = self._strip_prefix(c)
            if text not in seen:
                seen.add(text)
                credits.append(text)

        credits.sort(key=self._sort_key)

        rows = []
        for i in range(0, len(credits), 2):
            left = str(credits[i])
            right = str(credits[i + 1]) if i + 1 < len(credits) else ""
            rows.append((left, right))

        html = self._build_html(rows)

        if output_path is None:
            output_path = self.xlsx_path.with_name("credit.html")

        output_path.write_text(html, encoding="utf-8")
        logger.info(f"Wrote {len(rows)} rows to {output_path}")
        return output_path

    ROWS_PER_TABLE = 18

    def _build_html(self, rows: list[tuple[str, str]]) -> str:
        chunks = [rows[i:i + self.ROWS_PER_TABLE] for i in range(0, len(rows), self.ROWS_PER_TABLE)]

        tables_html = []
        for n, chunk in enumerate(chunks, start=1):
            tr_lines = []
            for left, right in chunk:
                left_esc = self._esc(left)
                right_esc = self._esc(right)
                tr_lines.append(f"    <tr><td>{left_esc}</td><td>{right_esc}</td></tr>")
            tables_html.append(f'  <table id="table-{n}">\n' + "\n".join(tr_lines) + "\n  </table>")

        body = "\n".join(tables_html)
        return f"""\
<!DOCTYPE html>
<html lang="ja">
<head>
  <meta charset="UTF-8">
  <title>Credits</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link
     href="https://fonts.googleapis.com/css2?family=Barlow+Condensed:ital,wght@1,200;1,300;1,400&family=M+PLUS+Rounded+1c&family=Noto+Sans+TC:wght@100..900&display=swap"
     rel="stylesheet">
  <style>
    body {{ font-family: "M PLUS Rounded 1c", sans-serif; padding: 0; margin: 0; background: #000; color: #fff; font-size: calc(5vh * 0.5) }}
    table {{ border-collapse: collapse; width: 100%; margin: 2.5rem 0; display: none; }}
    td {{ padding: 0.5em 1em; vertical-align: top; text-align: center; width: 50%; }}
  </style>
</head>
<body>
{body}
<script>
(() => {{
        const hosturl = new URL(window.location.href);
        const interval = parseInt(hosturl.searchParams.get("interval") || 3000)
        let count = 0;
        setInterval(() => {{
        document.querySelectorAll("table").forEach((el, i) => {{ if (i == count) {{ el.style.display="table" }} else {{ el.style.display = "none" }} }})
        count ++;
        }}, interval);
}})()
</script>
</body>
</html>
"""

    @staticmethod
    def _sort_key(text: str) -> tuple:
        first = text[0] if text else ""
        if first.isdigit():
            group = 0
        elif first.isascii() and first.isalpha():
            group = 1
        else:
            group = 2
        return (group, text.lower())

    @staticmethod
    def _strip_prefix(text: str) -> str:
        t = str(text).strip()
        if t.lower().startswith("credit:"):
            t = t[len("credit:"):].lstrip()
        return t

    @staticmethod
    def _esc(text: str) -> str:
        return (
            text.replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
                .replace('"', "&quot;")
        )


if __name__ == "__main__":
    import argparse

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    parser = argparse.ArgumentParser(description="Generate credit HTML from Excel")
    parser.add_argument("xlsx", type=Path, help="Excel file path")
    parser.add_argument("-o", "--output", type=Path, default=None, help="Output HTML path (default: <xlsx>.html)")
    args = parser.parse_args()

    gen = CreditGenerator(args.xlsx)
    out = gen.generate(args.output)
    print(f"Generated: {out}")

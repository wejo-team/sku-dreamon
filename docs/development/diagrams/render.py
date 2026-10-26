"""Mermaid 원본을 SVG로 생성하고 원본 크기로 확대할 수 있게 저장한다."""

import argparse
import re
import subprocess
from pathlib import Path
from xml.etree import ElementTree

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--puppeteer-config", type=Path)
args = parser.parse_args()
directory = Path(__file__).resolve().parent
for name in ("ai-flow", "ai-tools", "ai-lifecycle"):
    target = directory / f"{name}.svg"
    command = [
        "npx",
        "--yes",
        "--package=@mermaid-js/mermaid-cli@11.12.0",
        "mmdc",
        "-i",
        str(directory / f"{name}.mmd"),
        "-o",
        str(target),
        "-c",
        str(directory / "mermaid-config.json"),
        "-b",
        "#ffffff",
    ]
    if args.puppeteer_config:
        command.extend(["-p", str(args.puppeteer_config.resolve())])
    subprocess.run(command, check=True)
    source = target.read_text()
    svg = ElementTree.fromstring(source)
    _, _, width, height = svg.attrib["viewBox"].split()
    # 기본 SVG는 단독으로 열 때 뷰포트 높이에 맞춰 축소될 수 있다.
    # 고유 크기를 명시하고 문서의 img는 기존 반응형 CSS에 맡긴다.
    root, rest = source.split(">", 1)
    root = re.sub(r'\bwidth="[^"]*"', f'width="{width}"', root, count=1)
    if re.search(r'\bheight="[^"]*"', root):
        root = re.sub(r'\bheight="[^"]*"', f'height="{height}"', root, count=1)
    else:
        root += f' height="{height}"'
    target.write_text(root + ">" + rest)

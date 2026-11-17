"""Explicit application/test selection shared by host-side Compose tools."""
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
TEST='--test' in sys.argv
PRIVATE=ROOT/('.local/compose-test' if TEST else '.local/s7')
URL='http://127.0.0.1:'+('5188' if TEST else '5187')
COMPOSE=['docker','compose','-f',str(ROOT/'compose.yaml')]
if TEST: COMPOSE += ['-f',str(ROOT/'compose.test.yaml')]

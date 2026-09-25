#!/usr/bin/env python3
"""Run the explicit upstream compatibility gate; no provider/production access."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from trace_gc.cli import main
if __name__=="__main__":raise SystemExit(main(["check-legacy",*sys.argv[1:]]))

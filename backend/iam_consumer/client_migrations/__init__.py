from pathlib import Path

# Reuse immutable historical migration modules; add only the S5 boundary step.
__path__.append(str(Path(__file__).resolve().parents[2] / "clients" / "migrations"))

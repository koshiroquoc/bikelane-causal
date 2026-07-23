PYTHON := .venv/bin/python
export PYTHONPATH := src
export MPLCONFIGDIR := .scratch/matplotlib

.PHONY: setup phase1 panel test phase2

setup:
	python3 -m venv .venv
	$(PYTHON) -m pip install -r requirements.txt

phase1:
	$(PYTHON) scripts/build_phase1_audit.py

panel:
	$(PYTHON) -m bikelane_causal.pipeline

test:
	$(PYTHON) -m pytest

phase2: phase1 panel test

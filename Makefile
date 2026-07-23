PYTHON := .venv/bin/python
export PYTHONPATH := src
export MPLCONFIGDIR := .scratch/matplotlib

.PHONY: setup phase1 panel test test-phase2 diagnostics test-phase3a pretrend-leads gate test-phase3b phase2 phase3a phase3b phase3

setup:
	python3 -m venv .venv
	$(PYTHON) -m pip install -r requirements.txt

phase1:
	$(PYTHON) scripts/build_phase1_audit.py

panel:
	$(PYTHON) -m bikelane_causal.pipeline

test:
	$(PYTHON) -m pytest

test-phase2:
	$(PYTHON) -m pytest tests/test_analysis_panel.py

diagnostics:
	$(PYTHON) -m bikelane_causal.diagnostics

test-phase3a:
	$(PYTHON) -m pytest tests/test_phase3_diagnostics.py

gate:
	$(PYTHON) -m bikelane_causal.identification_gate

pretrend-leads:
	$(PYTHON) -m bikelane_causal.pretrend_leads

test-phase3b:
	$(PYTHON) -m pytest tests/test_phase3_gate.py

phase2: phase1 panel test-phase2

phase3a: panel test-phase2 diagnostics test-phase3a

phase3b: phase3a pretrend-leads gate test-phase3b

phase3: phase3b

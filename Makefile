PYTHON := .venv/bin/python
export PYTHONPATH := src
export MPLCONFIGDIR := .scratch/matplotlib

.PHONY: setup phase1 panel test test-phase2 diagnostics test-phase3a pretrend-leads gate test-phase3b estimate test-phase4 robustness test-phase5 release-assets test-phase6 phase2 phase3a phase3b phase3 phase4 phase5 release phase6 reproduce

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

estimate:
	$(PYTHON) -m bikelane_causal.estimation

test-phase4:
	$(PYTHON) -m pytest tests/test_phase4_estimation.py

robustness:
	$(PYTHON) -m bikelane_causal.robustness

test-phase5:
	$(PYTHON) -m pytest tests/test_phase5_robustness.py

release-assets:
	$(PYTHON) -m bikelane_causal.release

test-phase6:
	$(PYTHON) -m pytest tests/test_phase6_release.py

phase2: phase1 panel test-phase2

phase3a: panel test-phase2 diagnostics test-phase3a

phase3b: phase3a pretrend-leads gate test-phase3b

phase3: phase3b

phase4: phase3b estimate test-phase4

phase5: phase4 robustness test-phase5

release: release-assets test-phase6

phase6: phase5 release

reproduce: phase6

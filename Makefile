SHELL := /bin/bash
.SHELLFLAGS := -eu -o pipefail -c
.DEFAULT_GOAL := all

ROOT := $(abspath .)
VENV := $(ROOT)/.venv
PY := $(VENV)/bin/python
PYTHON_BOOT ?= $(shell command -v python3.11 || command -v python3.12 || command -v python3.13 || command -v python3)
PROJECTS := p1-fulfilment-ops p2-experimentation p3-customer-product

# build -> test data and metrics -> report -> test rendered outputs: reports are only rendered from
# data that passed the tests, and the rendered Excel, dashboard and markdown are then checked themselves
define run_project
	@echo "==> $(1): build"
	cd $(1) && PYTHONPATH=$(ROOT) $(PY) pipeline.py build
	@echo "==> $(1): test data and metrics"
	cd $(1) && PYTHONPATH=$(ROOT) $(PY) -m pytest -q -p no:cacheprovider -m "not outputs" tests
	@echo "==> $(1): report"
	cd $(1) && PYTHONPATH=$(ROOT) $(PY) pipeline.py report
	@echo "==> $(1): test outputs"
	cd $(1) && PYTHONPATH=$(ROOT) $(PY) -m pytest -q -p no:cacheprovider -m outputs tests
endef

.PHONY: all setup p1 p2 p3 test readme site clean

all: p1 p2 p3 readme site

$(VENV)/.installed: requirements.txt
	$(PYTHON_BOOT) -c 'import sys; assert sys.version_info >= (3, 11), "python 3.11+ is required"'
	$(PYTHON_BOOT) -m venv $(VENV)
	$(PY) -m pip install -q --upgrade pip
	$(PY) -m pip install -q -r requirements.txt
	touch $@

setup: $(VENV)/.installed

p1: setup
	$(call run_project,p1-fulfilment-ops)

p2: setup
	$(call run_project,p2-experimentation)

p3: setup
	$(call run_project,p3-customer-product)

test: setup
	for p in $(PROJECTS); do (cd $$p && PYTHONPATH=$(ROOT) $(PY) -m pytest -q -p no:cacheprovider tests); done

readme: setup
	PYTHONPATH=$(ROOT) $(PY) -m shared.landing

site: setup
	PYTHONPATH=$(ROOT) $(PY) -m shared.site

clean:
	rm -rf site $(addsuffix /data,$(PROJECTS))

PYTHON	?= python3
MAP	?= maps/easy/01_linear_path.txt
ARGS	?=

.PHONY: install run debug clean lint lint-strict test

install:
	$(PYTHON) -m pip install -r requirements.txt

run:
	$(PYTHON) main.py $(MAP) $(ARGS)

debug:
	$(PYTHON) -m pdb main.py $(MAP) $(ARGS)

clean:
	rm -rf .mypy_cache .pytest_cache
	find . -type d -name "__pycache__" -prune -exec rm -rf {} +

lint:
	$(PYTHON) -m flake8 .
	$(PYTHON) -m mypy . --warn-return-any --warn-unused-ignores --ignore-missing-imports \
		--disallow-untyped-defs --check-untyped-defs

lint-strict:
	$(PYTHON) -m flake8 .
	$(PYTHON) -m mypy . --strict

test:
	$(PYTHON) -m pytest -q

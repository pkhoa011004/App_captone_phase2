.PHONY: install run test test-cov lint

# Cài dependencies
install:
	python -m pip install -r requirements-dev.txt

# Chạy server local
run:
	uvicorn main:app --host 0.0.0.0 --port 8080 --reload

# Chạy tất cả tests
test:
	pytest -v

# Chạy tests kèm báo cáo coverage
test-cov:
	pytest -v --cov=. --cov-report=term-missing --cov-omit="tests/*"

# Lint code
lint:
	ruff check .
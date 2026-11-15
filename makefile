.PHONY: help init git test commit

ifeq ($(OS),Windows_NT)
DETECTED_OS := windows
PRE_COMMIT_INSTALL := py -m pip install pre-commit
else
UNAME_S := $(shell uname -s)
ifeq ($(UNAME_S),Darwin)
DETECTED_OS := macos
PRE_COMMIT_INSTALL := brew install pre-commit
else ifeq ($(UNAME_S),Linux)
DETECTED_OS := linux
PRE_COMMIT_INSTALL := pip install pre-commit
else
DETECTED_OS := unknown
endif
endif

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

init: ## Check OS and install the pre-commit hook
ifeq ($(DETECTED_OS),unknown)
	$(error unsupported os: $(UNAME_S))
endif
	@echo os: $(DETECTED_OS)
ifeq ($(DETECTED_OS),windows)
	@where pre-commit >NUL 2>&1 || (echo pre-commit not installed. install: $(PRE_COMMIT_INSTALL) & exit /b 1)
else
	@command -v pre-commit >/dev/null 2>&1 || { echo "pre-commit not installed. install: $(PRE_COMMIT_INSTALL)"; exit 1; }
endif
	@pre-commit --version
	@pre-commit install --config .pre-commit/config.yaml

test: ## Unit tests for services with changed files
	@fail=0; \
	services=$$({ git diff --name-only HEAD; git ls-files --others --exclude-standard; } | awk -F/ '$$1=="services" && $$2!="" {print $$2}' | sort -u); \
	for service in $$services; do \
		dir="services/$$service"; \
		test -f "$$dir/requirements.txt" || continue; \
		compgen -G "$$dir/tests/test_*.py" > /dev/null || continue; \
		test -x .venv/bin/python || { echo "missing .venv"; exit 1; }; \
		echo "test $$dir"; \
		PYTHONPATH="$$dir" .venv/bin/python -m unittest discover -s "$$dir/tests" || fail=1; \
	done; \
	test "$$fail" = 0

commit: ## Status, stage all, test changed services, then commit as "(emoji) type - message"
	@git status
	@if git diff --cached --quiet; then git add -A; else echo "staged files found, skipping git add"; fi
	@git status
	@$(MAKE) --no-print-directory test
	@COLUMNS=20; PS3="type: "; \
	select label in "feat      new feature ✨" "fix       bug fix 🐛" "doc       documentation changes 📝" "core      core logic changes 🔧" "test      add or update tests ✅" "chore     maintenance and cleanup 🧹" "refactor  restructure, same behavior ♻️" "infra     infrastructure and deploy 🏗️" "ci        pipeline changes 👷"; do \
		if [ -z "$$label" ]; then \
			case "$$REPLY" in \
			feat) label="feat ✨";; fix) label="fix 🐛";; doc) label="doc 📝";; core) label="core 🔧";; \
			test) label="test ✅";; chore) label="chore 🧹";; refactor) label="refactor ♻️";; \
			infra) label="infra 🏗️";; ci) label="ci 👷";; \
			*) echo "pick 1-9 or a type name" >&2; continue;; \
			esac; \
		fi; \
		break; \
	done; \
	[ -n "$$label" ] || exit 1; \
	type=$${label%% *}; e=$${label##* }; \
	read -r -p "message: " msg; \
	git commit -m "$$e $$type - $$msg"

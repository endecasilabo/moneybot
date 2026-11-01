PROJECT_ID ?=
REGION ?= us-central1
GITHUB_REPOSITORY ?=
IMAGE := $(REGION)-docker.pkg.dev/$(PROJECT_ID)/moneybot/bot:latest
PYTHON := $(shell if [ -x .venv/bin/python ]; then echo .venv/bin/python; else echo python3; fi)
TF := terraform -chdir=infra
TF_VARS := -var="project_id=$(PROJECT_ID)" -var="region=$(REGION)" -var="github_repository=$(GITHUB_REPOSITORY)"

.PHONY: test release deploy infra jobs secrets init require-project

test:
	$(PYTHON) -m pip install -q -r requirements.txt
	$(PYTHON) -m unittest discover -s tests

release: test deploy

deploy: require-project
	gcloud builds submit --project "$(PROJECT_ID)" --config cloudbuild.yaml --substitutions "_REGION=$(REGION)"

init: require-project
	$(TF) init

infra: init
	$(TF) apply $(TF_VARS)

jobs: init
	$(TF) apply $(TF_VARS) -var="image=$(IMAGE)"

secrets: require-project
	@test -n "$$ALPACA_KEY" && test -n "$$ALPACA_SECRET" || { echo "ALPACA_KEY and ALPACA_SECRET must be set"; exit 1; }
	printf '%s' "$$ALPACA_KEY" | gcloud secrets versions add moneybot-alpaca-key --project "$(PROJECT_ID)" --data-file=-
	printf '%s' "$$ALPACA_SECRET" | gcloud secrets versions add moneybot-alpaca-secret --project "$(PROJECT_ID)" --data-file=-

require-project:
	@test -n "$(PROJECT_ID)" || { echo "PROJECT_ID is required"; exit 1; }

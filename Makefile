PROJECT_ID ?=
REGION ?= us-central1
IMAGE := $(REGION)-docker.pkg.dev/$(PROJECT_ID)/moneybot/bot:latest
STATE_BUCKET := $(PROJECT_ID)-moneybot-tfstate
PYTHON := $(shell if [ -x .venv/bin/python ]; then echo .venv/bin/python; else echo python3; fi)
TF := terraform -chdir=infra
TF_VARS := -var="project_id=$(PROJECT_ID)" -var="region=$(REGION)"

.PHONY: test deploy infra jobs secrets init require-project

test:
	$(PYTHON) -m pip install -q -r requirements.txt
	$(PYTHON) -m unittest discover -s tests

deploy: require-project
	gcloud builds submit --project "$(PROJECT_ID)" --config cloudbuild.yaml --substitutions "_REGION=$(REGION)"

init: require-project
	gcloud storage buckets describe "gs://$(STATE_BUCKET)" --project "$(PROJECT_ID)" >/dev/null 2>&1 || \
	  gcloud storage buckets create "gs://$(STATE_BUCKET)" --project "$(PROJECT_ID)" --location "$(REGION)" --uniform-bucket-level-access
	$(TF) init -input=false -reconfigure -backend-config="bucket=$(STATE_BUCKET)" -backend-config="prefix=moneybot"

infra: init
	$(TF) apply -input=false -auto-approve $(TF_VARS)

jobs: init
	$(TF) apply -input=false -auto-approve $(TF_VARS) -var="image=$(IMAGE)"

secrets: require-project
	@test -n "$$ALPACA_KEY" && test -n "$$ALPACA_SECRET" || { echo "ALPACA_KEY and ALPACA_SECRET must be set"; exit 1; }
	@printf '%s' "$$ALPACA_KEY" | gcloud secrets versions add moneybot-alpaca-key --project "$(PROJECT_ID)" --data-file=-
	@printf '%s' "$$ALPACA_SECRET" | gcloud secrets versions add moneybot-alpaca-secret --project "$(PROJECT_ID)" --data-file=-

require-project:
	@test -n "$(PROJECT_ID)" || { echo "PROJECT_ID is required"; exit 1; }

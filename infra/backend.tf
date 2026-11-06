# Partial backend. The Infra workflow passes bucket PROJECT_ID-moneybot-tfstate and prefix moneybot.
# That workflow creates the bucket when it does not exist yet.

terraform {
  backend "gcs" {}
}

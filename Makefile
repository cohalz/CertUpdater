BASE := $(shell /bin/pwd)
PIPENV ?= pipenv

SERVICE := src

AWS_PROFILE=default
SERVICE_NAME=certupdater
BUCKET_NAME=example-$(SERVICE_NAME)-artifacts
CFN_CMD=aws --profile $(AWS_PROFILE) $$(if [ -n "$(AWS_REGION)" ]; then echo "--region $(AWS_REGION)"; fi) cloudformation
TMP_TEMPLATE=tmp_template.yml
STACK_NAME=$(SERVICE_NAME)-stack

build:
	sam build --use-container

deploy:
	$(CFN_CMD) package \
		--template-file .aws-sam/build/template.yaml \
		--output-template-file tmp_template.yml \
		--s3-bucket $(BUCKET_NAME) 
	$(CFN_CMD) deploy \
		--template-file tmp_template.yml \
		--stack-name $(STACK_NAME) \
		--capabilities CAPABILITY_NAMED_IAM
	rm tmp_template.yml

invoke:
	sam local invoke --event event.json

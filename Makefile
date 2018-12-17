BASE := $(shell /bin/pwd)
PIPENV ?= pipenv

SERVICE := src

AWS_PROFILE=default
SERVICE_NAME=certupdater
BUCKET_NAME=example-$(SERVICE_NAME)-artifacts
CFN_CMD=aws --profile $(AWS_PROFILE) cloudformation
TMP_TEMPLATE=tmp_template.yml
STACK_NAME=$(SERVICE_NAME)-stack

clean: ##=> Deletes current build environment and latest build
	$(info [*] Who needs all that anyway? Destroying environment....)
	rm -rf ./${SERVICE}/build
	
install:
	$(info [+] Packaging service '$(SERVICE)' using Docker Lambda -- This may take a while...)
	docker run -v $$PWD:/var/task -it lambci/lambda:build-python3.6 /bin/bash -c 'make _install SERVICE="${SERVICE}"'

build:
	docker run -v $$PWD:/var/task -it lambci/lambda:build-python3.6 /bin/bash -c 'make _build SERVICE="${SERVICE}"'

deploy:
	$(CFN_CMD) package \
		--template-file template.yml \
		--output-template-file tmp_template.yml \
		--s3-bucket $(BUCKET_NAME) 
	$(CFN_CMD) deploy \
		--template-file tmp_template.yml \
		--stack-name $(STACK_NAME) \
		--capabilities CAPABILITY_NAMED_IAM
	rm tmp_template.yml

delete:
	$(CFN_CMD) delete-stack \
		--stack-name $(STACK_NAME)

invoke:
	sam local invoke --event event.json

############# 
#  Helpers  #
############# 

_install:
	$(info [+] Installing '$(SERVICE)' dependencies...")
	@pip install pipenv
	@$(PIPENV) lock -r > requirements.txt
	@$(PIPENV) run pip install \
		--isolated \
		--disable-pip-version-check \
		-Ur requirements.txt -t ${SERVICE}/build/
	@rm -f requirements.txt
	@cp ${SERVICE}/main.py ${SERVICE}/build/

_build:
	$(info [+] Building main.py...")
	@cp ${SERVICE}/main.py ${SERVICE}/build/
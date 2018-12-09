BASE := $(shell /bin/pwd)
PIPENV ?= pipenv

SERVICE := src

AWS_PROFILE=default
SERVICE_NAME=certupdater
BUCKET_NAME=$(SERVICE_NAME)-artifacts
CFN_CMD=aws --profile $(AWS_PROFILE) cloudformation
TMP_TEMPLATE=tmp_template.yml
STACK_NAME=$(SERVICE_NAME)-stack

clean: ##=> Deletes current build environment and latest build
	$(info [*] Who needs all that anyway? Destroying environment....)
	rm -rf ./${SERVICE}/build
	rm -rf ./${SERVICE}.zip
	
build:
	$(info [+] Packaging service '$(SERVICE)' using Docker Lambda -- This may take a while...)
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

_build: _clone_service_to_build _install_deps

_clone_service_to_build:
ifeq ($(wildcard $(SERVICE)/build/.),)
	$(info [+] Setting permissions for files under ${SERVICE}/)
	find ${SERVICE}/ -type f -exec chmod go+r {} \;
	$(info [+] Setting permissions for directories under ${SERVICE}/)
	find ${SERVICE}/ -type d -exec chmod go+rx {} \;
	$(info [+] Cloning ${SERVICE} directory structure to ${SERVICE}/build)
	rsync -a -f "+ */" -f "- *" ${SERVICE}/ ${SERVICE}/build/
	$(info [+] Cloning source files from ${SERVICE} to ${SERVICE}/build)
	@find ${SERVICE} -type f \
			-not -name "*.pyc" \
			-not -name "*__pycache__" \
			-not -name "requirements.txt" \
			-not -name "event.json" \
			-not -name "build" | cut -d '/' -f2- > .results.txt
	@while read line; do \
		ln -f ${SERVICE}/$$line ${SERVICE}/build/$$line; \
	done < .results.txt
	rm -f .results.txt
else
	$(info [-] '$(SERVICE)' already has a development build - Ignoring cloning task...)
endif

_install_deps:
	$(info [+] Installing '$(SERVICE)' dependencies...")
	@pip install pipenv
	@$(PIPENV) run pip install pip==18.0	
	@$(PIPENV) lock -r > requirements.txt
	@$(PIPENV) run pip install \
		--isolated \
		--disable-pip-version-check \
		-Ur requirements.txt -t ${SERVICE}/build/
	@rm -f requirements.txt
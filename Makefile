.PHONY: bootstrap check healthcheck contracts m-components m-acceptance
bootstrap:
	bash scripts/install-m.sh
	npm ci --ignore-scripts
contracts:
	.venv-m/bin/python scripts/generate_m_contracts.py --check
m-components:
	.venv-m/bin/python scripts/check_m.py --profile components
m-acceptance:
	.venv-m/bin/python scripts/check_m.py --profile acceptance
check: contracts m-components
healthcheck:
	.venv-m/bin/python scripts/check_m_environment.py --docker --sdk

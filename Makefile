.PHONY: test

# Docker-only offline checks. Same command as the CI compose job.
test:
	bash scripts/docker-test.sh

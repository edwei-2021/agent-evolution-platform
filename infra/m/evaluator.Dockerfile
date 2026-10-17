ARG PYTHON_IMAGE=python:3.12-slim
FROM ${PYTHON_IMAGE}
COPY scripts/repair_fixture.py scripts/challenge_policy.py scripts/repair_evaluator.py /evaluator/
USER 65534:65534
WORKDIR /evaluator
ENTRYPOINT ["python", "-I", "-S", "/evaluator/repair_evaluator.py"]

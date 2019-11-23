# An image to expedite CI/CD builds, especially related to:
#  - Python linting and unit tests
#  - Docker builds

FROM python:3.7

ENV ARTIFACTS_ROOT /tmp/output
ENV TESTS_OUTPUT $ARTIFACTS_ROOT/test-reports

RUN apt-get update && \
    apt-get install -y \
    docker.io \
    jq

RUN pip3 install --upgrade \
    awscli \
    docker \
    fire \
    junit-xml \
    psutil \
    xmlrunner
# # azure \
# boto3 \
# s3fs \

RUN mkdir -p $ARTIFACTS_ROOT
RUN mkdir -p $TESTS_OUTPUT

RUN touch $ARTIFACTS_ROOT/_BUILD_ARTIFACTS_GO_HERE_ && \
    touch $TESTS_OUTPUT/_SAVED_OUTPUT_GOES_HERE_

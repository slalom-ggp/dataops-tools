ARG core_image=python:3.7
ARG git_commit_url=https://github.com/slalom-ggp/dataops-tools

FROM {core_image}

RUN git clone {git_commit_url}.git .

CMD ["python3", "-m", "slalom.dataops.infra", "apply"]

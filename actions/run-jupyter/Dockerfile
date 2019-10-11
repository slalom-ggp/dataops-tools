ARG core_image=python:3.7
FROM ${core_image}

ARG git_clone_url=https://github.com/slalom-ggp/dataops-tools
ARG git_commit_sha=49e2643d24b3ad973b6cfa468deea08714a11ef8

RUN echo ${git_commit_url}

ENV REPO_ROOT = ~/workspace/
RUN mkdir -p $REPO_ROOT
WORKDIR ${REPO_ROOT}

RUN git clone ${git_clone_url}.git .
RUN if ( ! -z "$git_commit_sha" ) then { git checkout $git_commit_sha; } fi

CMD ["echo", "Hey"]

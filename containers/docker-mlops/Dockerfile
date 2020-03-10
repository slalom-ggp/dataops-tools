FROM python:3.8

RUN pip install shap
RUN pip install fire

WORKDIR /usr/local

COPY shap-run.py shap-run.py

ENTRYPOINT [ "python", "./shap-run.py" ]
CMD [ "--infile=test" ]

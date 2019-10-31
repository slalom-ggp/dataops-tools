# dataops-tools ![CI/CD Badge (master)](https://github.com/slalom-ggp/dataops-tools/workflows/CI/CD%20Pipeline/badge.svg) ![PyPi Badge (master)](https://github.com/slalom-ggp/dataops-tools/workflows/Publish%20to%20PyPi/badge.svg)

Reusable tools, utilities, and containers that accelerate data processing and DevOps.

## Testing

```bash
> python
```

```python
from slalom.dataops import dockerutils, sparkutils; dockerutils.smart_build("containers/docker-spark/Dockerfile", "local-spark", push_core=False); dockerutils.smart_build("Dockerfile", "local-dataops", push_core=False); spark = sparkutils.get_spark(dockerized=True)
```

## Notes

- It is possible for environments to become stuck due to failures in printing output variables, for instance if SSH keys are accidentally deleted or rotated incorrectly. To ignore errors from outputs which cannot be parsed, first set the environment variable: `TF_WARN_OUTPUT_ERRORS=1` and then re-run `terraform apply` or `terrafom destroy`. This will warn on output errors instead of failing the process.

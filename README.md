# dataops-tools ![CI/CD Badge (master)](https://github.com/slalom-ggp/dataops-tools/workflows/CI/CD%20Pipeline/badge.svg) ![PyPi Badge (master)](https://github.com/slalom-ggp/dataops-tools/workflows/Publish%20to%20PyPi/badge.svg)

Reusable tools, utilities, and containers that accelerate data processing and DevOps.

## Testing

```bash
> python
```

```python
from slalom.dataops import dockerutils, sparkutils; dockerutils.smart_build("containers/docker-spark/Dockerfile", "local-spark", push_core=False); dockerutils.smart_build("Dockerfile", "local-dataops", push_core=False); spark = sparkutils.get_spark(dockerized=True)
```

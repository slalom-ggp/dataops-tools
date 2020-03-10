# SHAP Docker image for ML Projects

_An image for leveraging SHAP in Docker containers._

## Getting the default image name

Windows:

```cmd
type Dockerimage
```

Linux/Mac:

```bash
cat Dockerimage
```

## Building the image

```bash
docker build -t slalomggp/shap .
```

## Testing the image

```bash
docker run -it --rm slalomggp/shap --infile=s3://my-test/path/to/file --outfile=s3://my-test/path/to/out
```

## Pushing the image

docker push slalomggp/shap

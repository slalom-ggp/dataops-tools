# Singer images

This folder contains definitions to build the docker images as `slalomggp/singer`.

## Usage examples

Install the helper library:

```bash
pip3 install slalom.dataops
```

Build one or more docker images:

```bash
s-tap build_image tap-csv        # Builds `slalomggp/singer:tap-csv`
s-tap build_image tap-csv --push # Builds and pushes `slalomggp/singer:tap-csv`
s-tap build_image pardot s3-csv  # Builds `slalomggp/singer:pardot-to-s3-csv`
s-tap build_all_images --push    # Builds and pushes everything in the index
```

Build and push a 'pre-release' docker image:

```bash
s-tap build_image pardot s3-csv --pre --push # Builds `slalomggp/singer:pardot-to-s3-csv--pre`
```

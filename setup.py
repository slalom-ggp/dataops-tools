from setuptools import setup
import os
from pathlib import Path

detected_version = None
version_filepath = "VERSION"

if "VERSION" in os.environ:
    detected_version = os.environ["VERSION"]
    if "/" in detected_version:
        detected_version = detected_version.split("/")[-1]
if not detected_version and os.path.exists(version_filepath):
    detected_version = Path(version_filepath).read_text()
    if len(detected_version.split(".")) <= 2:
        if "BUILD_NUMBER" in os.environ:
            detected_version = f"{detected_version}.{os.environ['BUILD_NUMBER']}"
if not detected_version:
    raise RuntimeError("Error. Could not detect version.")

detected_version = detected_version.lstrip("v")
print(f"Detected version: {detected_version}")
Path(version_filepath).write_text(f"v{detected_version}")

setup(
    name="slalom.dataops",
    packages=["slalom.dataops"],
    version=detected_version,
    license="MIT",
    description="Slalom GGP libary for DataOps automation",
    author="AJ Steers",
    author_email="aj.steers@slalom.com",
    url="https://bitbucket.org/slalom-consulting/dataops-tools/",
    download_url="https://github.com/slalom-ggp/dataops-tools/archive/v_0.1.tar.gz",
    keywords=["DATAOPS", "SLALOM", "DATA", "AUTOMATION", "CI/CD", "DEVOPS"],
    package_data={"": [version_filepath]},
    entry_points={
        "console_scripts": [  # Register CLI commands: s-spark, s-docker
            "s-docker = slalom.dataops.dockerutils:main",
            "s-infra = slalom.dataops.infra:main",
            "s-spark = slalom.dataops.sparkutils:main",
            "s-io = slalom.dataops.io:main",
        ]
    },
    include_package_data=True,
    install_requires=[
        "fire",
        "joblib",
        "junit-xml",
        "matplotlib",
        "psutil",
        "tqdm",
        "xmlrunner",
    ],
    extras_require={
        "Azure": ["azure"],
        "AWS": ["awscli", "s3fs"],
        "Pandas": ["pandas"],
        "Spark": ["pyspark"],
        "Docker": ["docker"],
    },
    classifiers=[
        "Development Status :: 3 - Alpha",  # Chose either "3 - Alpha", "4 - Beta" or "5 - Production/Stable" as the current state of your package
        "Intended Audience :: Developers",
        "Topic :: Software Development :: Build Tools",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3.7",
    ],
)

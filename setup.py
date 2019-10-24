from distutils.core import setup
from pathlib import Path

if "VERSION" in os.environ:
    detected_version = os.environ["VERSION"]
else:
    detected_version = Path('slalom/dataops/VERSION').read_text()
    if len(ver.split(".")) <= 2:
        if "BUILD_NUMBER" not in os.environ:
            raise RuntimeError("Missing environment variable 'BUILD_NUMBER'")
        detected_version = f"{ver}.{os.environ['BUILD_NUMBER']}"

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
    install_requires=[
        "fire",
        "joblib",
        "junit-xml",
        "matplotlib",
        "psutil",
        "xmlrunner",
    ],
    extras_require={
        "adl": ["azure"],
        "aws": ["awscli", "s3fs"],
        "pandas": ["pandas"],
        "spark": ["pyspark"],
        "docker": ["docker"],
    },
    classifiers=[
        "Development Status :: 3 - Alpha",  # Chose either "3 - Alpha", "4 - Beta" or "5 - Production/Stable" as the current state of your package
        "Intended Audience :: Developers",
        "Topic :: Software Development :: Build Tools",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3.7",
    ],
)

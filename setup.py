from distutils.core import setup

setup(
    name="slalom.dataops",
    packages=["slalom.dataops"],
    version="0.1",
    license="MIT",
    description="Slalom GGP libary for DataOps automation",
    author="AJ Steers",
    author_email="aj.steers@slalom.com",
    url="https://bitbucket.org/slalom-consulting/dataops-tools/",
    download_url="https://github.com/slalom-ggp/dataops-tools/archive/v_0.1.tar.gz",
    keywords=["DATAOPS", "SLALOM", "DATA", "AUTOMATION", "CI/CD", "DEVOPS"],
    install_requires=[
        "dataclasses",
        "fire",
        "joblib",
        "junit-xml",
        "matplotlib",
        "psutil",
        "xmlrunner",
    ],
    extras_require={
        "aws": ["awscli", "s3fs"],
        "adl": ["azure"],
        "spark": ["pyspark"],
        "pandas": ["pandas"],
    },
    classifiers=[
        "Development Status :: 3 - Alpha",  # Chose either "3 - Alpha", "4 - Beta" or "5 - Production/Stable" as the current state of your package
        "Intended Audience :: Developers",
        "Topic :: Software Development :: Build Tools",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3.7",
    ],
)

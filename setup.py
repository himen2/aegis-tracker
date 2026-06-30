from setuptools import setup, find_packages

setup(
    name="aegis-tracker",
    version="0.1.0",
    author="Aegis",
    description="Aegis ML Tracking Library (Protected Client)",
    packages=find_packages(),
    include_package_data=True,
    package_data={'': ['*.pyd', '*.so', '*.dylib', '*.dll']},
    install_requires=[
        "psutil"
    ],
    classifiers=[
        "Programming Language :: Python :: 3",
        "Operating System :: OS Independent",
    ],
    python_requires='>=3.8',
)

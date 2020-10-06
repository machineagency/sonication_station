import setuptools

with open("README.md", "r", newline="", encoding="utf-8") as fh:
    long_description = fh.read()

setuptools.setup(
    name="sonication_station",
    version="0.0.1",
    author="Joshua Vasquez",
    author_email="joshua@doublejumpelectric.com",
    description="Jubilee masquerading as a science robot",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/machineagency/sonication_station",
    license="MIT",
    keywords= ['jubilee'],
    packages=setuptools.find_packages(),
    classifiers=[
        "Development Status :: 4 - Beta",
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: POSIX :: Linux",
    ],
    python_requires='>=3.6',
    install_requires=[]
)

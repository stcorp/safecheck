from setuptools import setup

setup(
    name='safecheck',
    version='3.0',
    description='SAFE Internal Consistency Checker',
    author='S[&]T',
    license='BSD',
    packages=['safecheck'],
    entry_points={'console_scripts': ['safecheck = safecheck.safecheck:main']},
    install_requires=['lxml', "importlib_resources>=1.3.0; python_version < '3.9'"],
    package_data={"safecheck": ["xsd/*.xsd"]}
)

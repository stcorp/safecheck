from setuptools import setup

setup(
    name='safecheck',
    version='3.0',
    description='SAFE Internal Consistency Checker',
    author='S[&]T',
    license='BSD',
    py_modules=['safecheck'],
    entry_points={'console_scripts': ['safecheck = safecheck:main']},
    install_requires=['lxml'],
)

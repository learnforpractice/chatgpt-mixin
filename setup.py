
import os
from distutils.core import setup

setup(
    name="chatgpt-mixin",
    version="0.1.4",
    description="ChatGPT Bot For Mixin",
    author='learnforpractice',
    license="Apache 2.0",
    url="https://github.com/learnforpractice/chatgpt-mixin",
    packages=['chatgpt_mixin'],
    package_dir={'chatgpt_mixin': 'src'},
    package_data={},
    setup_requires=['wheel'],
)

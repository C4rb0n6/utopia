from setuptools import setup, find_packages

setup(
    name='utopia',
    version='0.1',
    packages=find_packages(),
    install_requires=[
        'aiohttp==3.9.2',
        'discord==2.3.2',
        'python-dotenv==1.0.0',
        'requests==2.31.0',
        'google-ai-generativelanguage==0.4.0',
        'google-generativeai==0.4.0',
        'pillow==10.2.0',
    ],
)

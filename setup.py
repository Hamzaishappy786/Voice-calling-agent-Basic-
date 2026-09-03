from setuptools import setup, find_packages

setup(
    name="voice-calling-agent",
    version="0.1.0",
    packages=find_packages(),
    include_package_data=True,
    package_data={
        "webagent": ["static/*", "static/**/*"],
    },
    install_requires=[
        "fastapi",
        "uvicorn[standard]",
        "httpx",
        "numpy",
        "python-multipart",
        "piper-tts",
    ],
    entry_points={
        "console_scripts": [
            "voice-agent=webagent.cli:main",
            "webagent=webagent.cli:main",
        ],
    },
)

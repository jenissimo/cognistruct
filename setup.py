from setuptools import setup, find_packages

setup(
    name="cognistruct",
    version="0.1.0",
    description="Модульный фреймворк для создания AI-ассистентов с поддержкой плагинов",
    long_description=open("README.md", encoding="utf-8").read(),
    long_description_content_type="text/markdown",
    author="Evgeniy Smirnov",
    url="https://github.com/jenissimo/cognistruct",
    packages=find_packages(where="src"),
    package_dir={"": "src"},
    python_requires=">=3.8",
    install_requires=[
        "pydantic",
        "fastapi",
        "python-jose",  # для JWT
        "uvicorn",
        "aiohttp",
        "sqlalchemy",
        "aiosqlite",
        "tzlocal",
        "tzdata",
        "python-telegram-bot[callback-data]",
        "telegramify-markdown",
        "openai",
        "rich",
        "scikit-learn",
        "numpy",
        "passlib",
        # Internet Plugin
        "crawl4ai",
        "duckduckgo-search>=4.1.1",
    ],
    extras_require={
        "dev": [
            "pytest",
            "pytest-asyncio",
            "black",
            "isort",
            "mypy",
        ],
    },
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
    ],
    include_package_data=True,  # Для включения не-Python файлов (например, промптов)
    package_data={
        "cognistruct": ["py.typed"],  # Для поддержки типов
    },
) 
"""
Setup script for the Chat Application.
"""

from setuptools import setup, find_packages
import os

# Read the README file for long description
def read_readme():
    """Read README.md file."""
    readme_path = os.path.join(os.path.dirname(__file__), 'README.md')
    if os.path.exists(readme_path):
        with open(readme_path, 'r', encoding='utf-8') as f:
            return f.read()
    return "A real-time TCP-based chat application with rich terminal UI."

# Read requirements from requirements.txt
def read_requirements():
    """Read requirements from requirements.txt."""
    requirements_path = os.path.join(os.path.dirname(__file__), 'requirements.txt')
    requirements = []
    if os.path.exists(requirements_path):
        with open(requirements_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    requirements.append(line)
    return requirements

# Read optional requirements
def read_optional_requirements():
    """Read optional requirements from requirements-optional.txt."""
    requirements_path = os.path.join(os.path.dirname(__file__), 'requirements-optional.txt')
    requirements = []
    if os.path.exists(requirements_path):
        with open(requirements_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    requirements.append(line)
    return requirements

setup(
    name="chat-app",
    version="1.0.0",
    author="Chat App Development Team",
    author_email="dev@chatapp.example.com",
    description="A real-time TCP-based chat application with rich terminal UI",
    long_description=read_readme(),
    long_description_content_type="text/markdown",
    url="https://github.com/example/chat-app",
    packages=find_packages(exclude=['tests*']),
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "Intended Audience :: End Users/Desktop",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Programming Language :: Python :: 3.13",
        "Topic :: Communications :: Chat",
        "Topic :: Internet",
        "Topic :: System :: Networking",
        "Topic :: Terminals",
    ],
    python_requires=">=3.8",
    install_requires=read_requirements(),
    extras_require={
        "yaml": ["PyYAML>=6.0,<7.0"],
        "monitoring": ["psutil>=5.9.0,<6.0"],
        "full": read_optional_requirements(),
        "dev": [
            "pytest>=7.0.0",
            "pytest-cov>=4.0.0",
            "mypy>=1.0.0",
            "hypothesis>=6.0.0",
        ],
    },
    entry_points={
        "console_scripts": [
            "chat-server=chat_app.server.main:main",
            "chat-client=chat_app.client.main:main",
        ],
    },
    include_package_data=True,
    package_data={
        "chat_app": [
            "*.md",
            "*.txt",
            "*.json",
            "*.yaml",
            "*.yml",
        ],
    },
    project_urls={
        "Bug Reports": "https://github.com/example/chat-app/issues",
        "Source": "https://github.com/example/chat-app",
        "Documentation": "https://github.com/example/chat-app/wiki",
    },
    keywords="chat, networking, terminal, real-time, tcp, rich, ui",
    zip_safe=False,
)